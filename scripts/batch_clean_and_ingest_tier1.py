import os
import sys
import re
import uuid
import time
import pickle
import asyncio
import argparse
from typing import List, Dict, Any, Set, Tuple
import pandas as pd
import httpx
from dotenv import dotenv_values
from supabase import create_client
from pinecone import Pinecone
from rank_bm25 import BM25Okapi

REPO_DIR = r"c:\Users\kabeer\Documents\lawyer-Backend-master\lawyer-Backend-master"
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR)

from hybrid_search import tokenize_legal_text

env = dotenv_values(os.path.join(REPO_DIR, ".env"))
SUPABASE_URL = env.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = env.get("SUPABASE_SERVICE_KEY")
PINECONE_API_KEY = env.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME = env.get("PINECONE_INDEX_NAME", "legal-kb-pk-local")
PINECONE_HOST = env.get("PINECONE_HOST")
VOYAGE_API_KEY = env.get("VOYAGE_API_KEY")

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# STANDING SAFETY GUARD: Prevent accidental direct mutations to production full_judgments
if os.environ.get("ALLOW_DIRECT_PROD_MUTATION") != "TRUE":
    raise RuntimeError(
        "SAFETY GUARD: Direct script writes to full_judgments are blocked to prevent accidental data contamination. "
        "Set ALLOW_DIRECT_PROD_MUTATION=TRUE explicitly if you genuinely intend to run this offline migration."
    )

pc = Pinecone(api_key=PINECONE_API_KEY)
pinecone_index = pc.Index(PINECONE_INDEX_NAME, host=PINECONE_HOST)

def clean_portal_artifacts(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'Citation Name:\s*[^\n]+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Bookmark this [Cc]ase\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Copyrights?\s*©?[^\n]*Oratier Technologies[^\n]*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'This site is developed\s*&?\s*maintained[^\n]*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Help\s+FAQ\'?s\s+Sitemap', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Print this Judgment', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Download PDF', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b[A-Z\-]+-(?:HIGH-COURT|COURT)\b', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def parse_citation_title_court(raw_field: str, journal: str, default_year: int) -> Tuple[str, str, str, int]:
    parts = str(raw_field).split('\t')
    citation = ""
    title = ""
    court_raw = ""
    
    if len(parts) >= 4:
        citation = parts[1].strip()
        title = parts[2].strip()
        court_raw = parts[3].strip()
    elif len(parts) == 3:
        citation = parts[1].strip()
        title = parts[2].strip()
    elif len(parts) == 2:
        citation = parts[0].strip()
        title = parts[1].strip()
    else:
        title = str(raw_field).strip()

    if not citation:
        m = re.search(r'\b(\d{4}\s+(?:SCMR|PLD|PTD|CLD)\s+\d+)\b', str(raw_field), re.IGNORECASE)
        if m:
            citation = m.group(1).upper()
        else:
            citation = f"{default_year} {journal}"

    # Year extraction
    year = default_year
    ym = re.search(r'\b(19\d\d|20\d\d)\b', citation)
    if ym:
        year = int(ym.group(1))

    # Standardize court name
    c_up = (court_raw + " " + title).upper()
    if journal == "SCMR" or "SUPREME-COURT" in c_up or "SUPREME COURT" in c_up or " SC " in c_up:
        court_name = "Supreme Court of Pakistan"
    elif "LAHORE" in c_up:
        court_name = "Lahore High Court"
    elif "SINDH" in c_up or "KARACHI" in c_up:
        court_name = "High Court of Sindh"
    elif "PESHAWAR" in c_up:
        court_name = "Peshawar High Court"
    elif "BALOCHISTAN" in c_up or "QUETTA" in c_up:
        court_name = "High Court of Balochistan"
    elif "ISLAMABAD" in c_up:
        court_name = "Islamabad High Court"
    elif "TRIBUNAL" in c_up or "ATIR" in c_up:
        court_name = "Appellate Tribunal"
    else:
        court_name = "Supreme Court of Pakistan" if journal == "SCMR" else "High Court"

    return citation, title, court_name, year

def generate_canonical_case_id(citation: str, journal: str, year: int, court_name: str, index: int) -> str:
    m = re.search(r'(\d{4})\s+([A-Z]+)\s+(\d+)', citation, re.IGNORECASE)
    if m:
        c_year, c_jour, c_page = m.group(1), m.group(2).upper(), m.group(3)
        if c_jour == "PLD" and "Supreme Court" in court_name:
            return f"{c_year}_PLD_SC_{c_page}"
        return f"{c_year}_{c_jour}_{c_page}"
    
    # Fallback to normalized citation
    clean = re.sub(r'[^a-zA-Z0-9]+', '_', citation.strip()).strip('_')
    return f"{year}_{journal}_{clean}_{index}"

async def get_voyage_embeddings_batch(texts: List[str], max_retries: int = 5) -> List[List[float]]:
    headers = {
        "Authorization": f"Bearer {VOYAGE_API_KEY}",
        "Content-Type": "application/json"
    }
    clean_inputs = [t[:4000] for t in texts]
    payload = {
        "input": clean_inputs,
        "model": "voyage-law-2"
    }
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post("https://api.voyageai.com/v1/embeddings", headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return [item["embedding"] for item in data["data"]]
                elif res.status_code == 429:
                    wait_time = (2 ** attempt) * 2
                    print(f"[RateLimit 429] Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"[Voyage Error] {res.status_code}: {res.text}. Retrying...")
                    await asyncio.sleep(2)
        except Exception as e:
            print(f"[Voyage Exception] {e}. Retrying in 2s...")
            await asyncio.sleep(2)
            
    raise RuntimeError(f"Failed to generate Voyage embeddings after {max_retries} attempts.")

def chunk_text(text: str, chunk_size: int = 1400, overlap: int = 300) -> List[str]:
    chunks = []
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    step = chunk_size - overlap
    for i in range(0, len(text), step):
        chunk = text[i:i + chunk_size]
        if chunk.strip():
            chunks.append(chunk.strip())
        if i + chunk_size >= len(text):
            break
    return chunks

async def process_tier1_corpus(
    raw_dir: str = r"D:\rerun\05_Raw_CSVs",
    target_journals: List[str] = None,
    max_cases_per_journal: int = None,
    batch_embed_size: int = 32
):
    print("=" * 60)
    print("PHASE 1 PRODUCTION SYNC: TIER 1 APEX PRECEDENTS")
    print("=" * 60)

    # Step 1: Load Existing State from BM25 & Pinecone
    bm25_path = os.path.join(REPO_DIR, "bm25_index.pkl")
    print(f"Loading existing BM25 index from {bm25_path}...")
    with open(bm25_path, "rb") as f:
        bm25_data = pickle.load(f)

    existing_vector_ids: Set[str] = set(bm25_data.get("doc_ids", []))
    doc_ids: List[str] = list(bm25_data.get("doc_ids", []))
    doc_metadata: List[Dict[str, Any]] = list(bm25_data.get("doc_metadata", []))
    
    print(f"Loaded {len(existing_vector_ids)} existing vector IDs from BM25 index.")

    # Reconstruct tokenized docs for incremental BM25 re-fitting
    print("Preparing existing tokenized corpus for incremental update...")
    all_tokens_for_bm25 = []
    for d_meta in doc_metadata:
        txt = d_meta.get("text") or ""
        toks = tokenize_legal_text(txt)
        all_tokens_for_bm25.append(toks if toks else ["law"])

    journal_configs = [
        {"journal": "SCMR", "file": "SCMR_cases.csv", "min_year": 2011, "filter_sc": True},
        {"journal": "PLD", "file": "PLD_cases.csv", "min_year": 1947, "filter_sc": True},
        {"journal": "PTD", "file": "PTD_cases.csv", "min_year": 1947, "filter_sc": False},
        {"journal": "CLD", "file": "CLD_cases.csv", "min_year": 1947, "filter_sc": False},
    ]

    if target_journals:
        journal_configs = [c for c in journal_configs if c["journal"] in target_journals]

    total_new_vectors = 0
    total_new_supabase = 0

    for cfg in journal_configs:
        j_name = cfg["journal"]
        file_path = os.path.join(raw_dir, cfg["file"])
        if not os.path.exists(file_path):
            print(f"Warning: File {file_path} not found. Skipping.")
            continue

        print(f"\n--- Processing Journal: {j_name} ({cfg['file']}) ---")
        df = pd.read_csv(file_path, on_bad_lines="skip")
        print(f"Total rows in CSV: {len(df)}")

        # Filter criteria
        if j_name == "SCMR":
            df = df[df["Year"] >= cfg["min_year"]]
            print(f"Filtered for post-2010 SCMR: {len(df)} rows")
        elif j_name == "PLD":
            df = df[df["Citation / Title"].str.contains("SUPREME-COURT|Supreme Court| SC ", case=False, na=False)]
            print(f"Filtered for PLD Supreme Court: {len(df)} rows")

        # Sort descending by Year to ingest most recent cases first
        if "Year" in df.columns:
            df = df.sort_values(by="Year", ascending=False)

        if max_cases_per_journal:
            df = df.head(max_cases_per_journal)
            print(f"Capped at {max_cases_per_journal} cases for this run.")

        pending_supabase_cases: List[Dict[str, Any]] = []
        pending_chunks: List[Dict[str, Any]] = []

        for idx, row in df.iterrows():
            citation_raw = row.get("Citation / Title", "")
            def_year = int(row.get("Year", 2020))
            case_index = int(row.get("Case Index", idx))

            citation, title, court_name, year = parse_citation_title_court(citation_raw, j_name, def_year)

            # SC check for PLD/SCMR
            if cfg["filter_sc"] and "Supreme Court" not in court_name:
                continue

            case_id = generate_canonical_case_id(citation, j_name, year, court_name, case_index)

            # Determine best text
            if "Judgment Content" in row and pd.notna(row["Judgment Content"]):
                raw_text = str(row["Judgment Content"])
            else:
                head = str(row.get("Headnotes / Case Description", "")) if pd.notna(row.get("Headnotes / Case Description")) else ""
                body = str(row.get("Full Judgment Body", "")) if pd.notna(row.get("Full Judgment Body")) else ""
                raw_text = head if len(head) > len(body) else body

            cleaned_text = clean_portal_artifacts(raw_text)
            if len(cleaned_text) < 100:
                continue

            # Queue for Supabase check
            pending_supabase_cases.append({
                "case_id": case_id,
                "neutral_citation": citation,
                "case_title": title,
                "court_name": court_name,
                "decision_date": str(year),
                "full_text": cleaned_text
            })

            # Chunk text
            chunks = chunk_text(cleaned_text, chunk_size=1400, overlap=300)
            for c_idx, c_text in enumerate(chunks):
                v_id = f"{case_id}_chk_{c_idx}"
                if v_id in existing_vector_ids:
                    continue  # Already indexed in Pinecone

                pending_chunks.append({
                    "id": v_id,
                    "case_id": case_id,
                    "citation": citation,
                    "neutral_citation": citation,
                    "case_title": title,
                    "court_name": court_name,
                    "year": year,
                    "text": c_text,
                    "chunk_index": c_idx
                })

        print(f"Found {len(pending_supabase_cases)} candidate cases, {len(pending_chunks)} new chunks to index.")

        # Batch check and insert into Supabase
        print(f"Checking existing cases in Supabase...")
        new_supabase_records = []
        batch_size_sb = 50
        for i in range(0, len(pending_supabase_cases), batch_size_sb):
            sb_batch = pending_supabase_cases[i:i + batch_size_sb]
            cids = [c["case_id"] for c in sb_batch]
            try:
                check_res = sb.table("full_judgments").select("case_id").in_("case_id", cids).execute()
                existing_cids = {r["case_id"] for r in check_res.data}
            except Exception as e:
                print(f"Warning on Supabase batch check: {e}")
                existing_cids = set()

            for c in sb_batch:
                if c["case_id"] not in existing_cids:
                    c_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, c["case_id"]))
                    new_supabase_records.append({
                        "id": c_uuid,
                        "case_id": c["case_id"],
                        "neutral_citation": c["neutral_citation"],
                        "case_title": c["case_title"],
                        "court_name": c["court_name"],
                        "decision_date": c["decision_date"],
                        "full_text": c["full_text"]
                    })

        if new_supabase_records:
            print(f"Inserting {len(new_supabase_records)} new cases into Supabase full_judgments...")
            for i in range(0, len(new_supabase_records), 50):
                insert_chunk = new_supabase_records[i:i + 50]
                try:
                    sb.table("full_judgments").upsert(insert_chunk, on_conflict="id").execute()
                    total_new_supabase += len(insert_chunk)
                except Exception as e:
                    print(f"Error upserting batch into Supabase: {e}")

        # Batch embed and upsert into Pinecone
        if pending_chunks:
            print(f"Embedding and upserting {len(pending_chunks)} chunks into Pinecone (namespace='judgments')...")
            for i in range(0, len(pending_chunks), batch_embed_size):
                chunk_batch = pending_chunks[i:i + batch_embed_size]
                texts = [c["text"] for c in chunk_batch]
                
                try:
                    embs = await get_voyage_embeddings_batch(texts)
                except Exception as e:
                    print(f"Failed to embed batch {i} to {i+batch_embed_size}: {e}")
                    continue

                vectors_to_upsert = []
                for c_item, emb in zip(chunk_batch, embs):
                    meta = {
                        "case_id": c_item["case_id"],
                        "citation": c_item["citation"],
                        "neutral_citation": c_item["neutral_citation"],
                        "case_title": c_item["case_title"],
                        "title": c_item["case_title"],
                        "court": c_item["court_name"],
                        "court_name": c_item["court_name"],
                        "year": c_item["year"],
                        "text": c_item["text"],
                        "chunk_index": c_item["chunk_index"]
                    }
                    vectors_to_upsert.append({
                        "id": c_item["id"],
                        "values": emb,
                        "metadata": meta
                    })

                    # Track for BM25
                    existing_vector_ids.add(c_item["id"])
                    doc_ids.append(c_item["id"])
                    doc_metadata.append(meta)
                    all_tokens_for_bm25.append(tokenize_legal_text(c_item["text"]))

                pinecone_index.upsert(vectors=vectors_to_upsert, namespace="judgments")
                total_new_vectors += len(vectors_to_upsert)
                print(f"   [{j_name}] Upserted {total_new_vectors} total new vectors so far...")
                await asyncio.sleep(0.5)

    # Step 3: Re-fit and Save BM25 Index
    if total_new_vectors > 0:
        print(f"\n=== Re-fitting BM25 Index with {len(doc_ids)} Total Chunks ({total_new_vectors} New) ===")
        t0 = time.time()
        new_bm25_model = BM25Okapi(all_tokens_for_bm25)
        new_bm25_data = {
            "bm25": new_bm25_model,
            "doc_ids": doc_ids,
            "doc_metadata": doc_metadata,
            "corpus_size": len(doc_ids)
        }
        with open(bm25_path, "wb") as f:
            pickle.dump(new_bm25_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"Saved updated BM25 index in {time.time()-t0:.2f}s! Total corpus size: {len(doc_ids)} chunks.")
    else:
        print("\nNo new vectors added to Pinecone. BM25 index is already up to date.")

    print("\n" + "=" * 60)
    print(f"PHASE 1 BATCH SYNC COMPLETE:")
    print(f"- New Cases Inserted into Supabase: {total_new_supabase}")
    print(f"- New Vectors Upserted to Pinecone:  {total_new_vectors}")
    print(f"- Total BM25 Corpus Size:            {len(doc_ids)} chunks")
    print("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean and ingest Tier 1 precedents into Supabase, Pinecone, and BM25.")
    parser.add_argument("--journal", nargs="+", default=["SCMR", "PLD", "PTD", "CLD"], help="Target journals (e.g. SCMR PLD PTD CLD)")
    parser.add_argument("--max-cases", type=int, default=None, help="Max cases per journal for this run")
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size")
    args = parser.parse_args()

    asyncio.run(process_tier1_corpus(
        target_journals=args.journal,
        max_cases_per_journal=args.max_cases,
        batch_embed_size=args.batch_size
    ))
