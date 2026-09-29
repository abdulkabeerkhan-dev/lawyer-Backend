import os
import sys
import re
import csv
import glob
import time
import json
import hashlib
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import tiktoken
import voyageai
from pinecone import Pinecone

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

csv.field_size_limit(100 * 1024 * 1024)

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "legal-kb-pk-local")
NAMESPACE = os.getenv("PINECONE_NAMESPACE", "judgments")

VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-law-2")

SUPABASE_URL = os.getenv("SUPABASE_URL")
BUCKET_NAME = "judgments-pdf"

if not PINECONE_API_KEY or not VOYAGE_API_KEY:
    print("[ERROR] PINECONE_API_KEY or VOYAGE_API_KEY missing from environment.")
    sys.exit(1)

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)
voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)

_encoder = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(_encoder.encode(text))

TARGET_CHUNK_TOKENS = 500
MIN_CHUNK_TOKENS = 150
OVERLAP_TOKENS = 50
EMBED_BATCH_SIZE = 128
PINECONE_BATCH_SIZE = 100

CSV_DIR = r"D:\missing_gaps_verified\cleaned_CSVs"
STATE_FILE = "ingestion_state_pinecone.json"

def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"ingested_cases": {}}

def save_state(state: Dict[str, Any]):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Notice saving state: {e}")

def sanitize_filename(name):
    name = str(name).strip()
    name = re.sub(r'[\\/*?:"<>|\r\n\t]', '_', name)
    name = re.sub(r'[\s\.\(\)\-]+', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name[:60]

def chunk_by_paragraph(text: str, target_tokens: int = TARGET_CHUNK_TOKENS, overlap: int = OVERLAP_TOKENS) -> List[str]:
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [l.strip() for l in text.split("\n") if l.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    chunks = []
    current_paras = []
    current_tokens = 0

    def flush():
        nonlocal current_paras, current_tokens
        if not current_paras:
            return [], 0
        chunk_text = "\n\n".join(current_paras)
        chunks.append(chunk_text)
        
        # Calculate overlap
        overlap_paras = []
        overlap_tok = 0
        for p in reversed(current_paras):
            p_tok = count_tokens(p)
            if overlap_tok + p_tok <= overlap:
                overlap_paras.insert(0, p)
                overlap_tok += p_tok
            else:
                break
        return overlap_paras, overlap_tok

    for para in paragraphs:
        para_tokens = count_tokens(para)
        # If single paragraph exceeds target tokens, break it into sentences/lines
        if para_tokens > target_tokens:
            sub_lines = [l.strip() for l in re.split(r'(?<=[.!?])\s+', para) if l.strip()]
            for sl in sub_lines:
                sl_tok = count_tokens(sl)
                if current_tokens + sl_tok > target_tokens and current_paras:
                    overlap_paras, _ = flush()
                    current_paras = overlap_paras[:]
                    current_tokens = sum(count_tokens(p) for p in current_paras)
                current_paras.append(sl)
                current_tokens += sl_tok
            continue

        if current_tokens + para_tokens > target_tokens and current_paras:
            overlap_paras, _ = flush()
            current_paras = overlap_paras[:]
            current_tokens = sum(count_tokens(p) for p in current_paras)

        current_paras.append(para)
        current_tokens += para_tokens

    if current_paras:
        chunks.append("\n\n".join(current_paras))

    if len(chunks) > 1:
        chunks = [c for c in chunks if count_tokens(c) >= MIN_CHUNK_TOKENS]

    return chunks or [text[:3000]]

def generate_canonical_id(court: str, journal: str, case_idx: str, year: str) -> str:
    norm_court = str(court or "").strip().upper()
    if "SUPREME" in norm_court or "SC" in norm_court:
        c_code = "SC"
    elif "LAHORE" in norm_court or "LHC" in norm_court:
        c_code = "LHC"
    elif "SINDH" in norm_court or "SHC" in norm_court:
        c_code = "SHC"
    elif "PESHAWAR" in norm_court or "PHC" in norm_court:
        c_code = "PHC"
    elif "BALOCHISTAN" in norm_court or "BHC" in norm_court:
        c_code = "BHC"
    elif "ISLAMABAD" in norm_court or "IHC" in norm_court:
        c_code = "IHC"
    elif "DACCA" in norm_court or "DHAKA" in norm_court:
        c_code = "DHC"
    elif "TRIBUNAL" in norm_court:
        c_code = "TRB"
    else:
        c_code = "CT"

    j_code = re.sub(r'[^A-Z0-9]', '', str(journal or "").upper()) or "GEN"
    idx_code = str(case_idx or "0").strip()
    yr_code = str(year or "2026").strip()
    return f"{c_code}_{j_code}_{idx_code}_{yr_code}"

def embed_texts_with_retry(texts: List[str], retries: int = 5, base_delay: float = 3.0) -> Optional[List[List[float]]]:
    for attempt in range(retries):
        try:
            res = voyage_client.embed(texts, model=VOYAGE_MODEL, input_type="document")
            return res.embeddings
        except Exception as e:
            err = str(e)
            is_transient = any(c in err for c in ["429", "500", "502", "503", "timeout", "connection", "rate"])
            if is_transient and attempt < retries - 1:
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)
                continue
            print(f"Permanent Voyage embed failure: {err}")
            return None
    return None

def upsert_vectors_to_pinecone(vectors: List[Dict[str, Any]], retries: int = 4) -> bool:
    for attempt in range(retries):
        try:
            index.upsert(vectors=vectors, namespace=NAMESPACE)
            return True
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
            else:
                print(f"Pinecone upsert error: {e}")
                return False
    return False

def process_journal_pinecone(csv_file: str, state: Dict[str, Any]):
    filename = os.path.basename(csv_file)
    print(f"\n{'='*70}\nSTARTING PINECONE INGESTION FOR: {filename}\n{'='*70}")

    rows = []
    with open(csv_file, 'r', encoding='utf-8-sig', errors='replace') as fp:
        reader = csv.DictReader(fp)
        for r in reader:
            rows.append(r)

    print(f"Loaded {len(rows):,} records from {filename}")

    pending_items = []
    for r in rows:
        case_id = f"{r.get('year')}_{r.get('journal')}_{r.get('case_index')}"
        if case_id not in state["ingested_cases"]:
            pending_items.append(r)

    print(f"Pending records to embed & index: {len(pending_items):,} (already indexed: {len(rows) - len(pending_items):,})")
    if not pending_items:
        return

    # Process pending in batches of cases
    batch_chunks = []
    batch_meta = []
    batch_case_ids = set()

    total_chunks_indexed = 0
    t0_pine = time.time()

    for idx, r in enumerate(pending_items):
        jn = r.get("journal", "").strip().upper()
        yr = r.get("year", "").strip()
        case_idx = r.get("case_index", "").strip()
        cit = r.get("citation", "").strip()
        title = r.get("title", "").strip()
        court = r.get("court", "").strip()
        bench = r.get("bench", "").strip()
        docket = r.get("docket_number", "").strip()
        date_str = r.get("decision_date", "").strip()
        hn = r.get("headnotes", "").strip()
        jd = r.get("judgment_body", "").strip()

        case_id = f"{yr}_{jn}_{case_idx}"
        canonical_id = generate_canonical_id(court, jn, case_idx, yr)

        cit_slug = sanitize_filename(cit)
        court_short = sanitize_filename(court.split()[0]) if court else ""
        if court_short and court_short.lower() not in cit_slug.lower():
            pdf_name = f"{cit_slug}_{court_short}_{case_idx}.pdf"
        else:
            pdf_name = f"{cit_slug}_Case_{case_idx}.pdf"

        remote_storage_path = f"{jn}/{yr}/{pdf_name}"
        pdf_public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_NAME}/{remote_storage_path}"

        if hn and jd and hn != jd:
            full_text = f"CITATION: {cit}\nTITLE: {title}\nCOURT: {court}\nBENCH: {bench}\nDOCKET: {docket}\nDATE: {date_str}\n\nHEADNOTES:\n{hn}\n\nJUDGMENT / ORDER:\n{jd}"
        else:
            full_text = f"CITATION: {cit}\nTITLE: {title}\nCOURT: {court}\nBENCH: {bench}\nDOCKET: {docket}\nDATE: {date_str}\n\n{jd or hn}"

        chunks = chunk_by_paragraph(full_text)
        for c_idx, chunk_text in enumerate(chunks):
            vec_id = f"{canonical_id}_chunk_{c_idx}"
            if len(vec_id) > 500:
                h = hashlib.md5(canonical_id.encode('utf-8')).hexdigest()
                vec_id = f"{canonical_id[:400]}_{h}_chunk_{c_idx}"

            meta = {
                "judgment_id": case_id,
                "canonical_id": canonical_id,
                "case_id": case_id,
                "citation": cit,
                "title": title[:250],
                "case_title": title[:250],
                "court": court or "Superior Courts of Pakistan",
                "bench": bench[:250] if bench else "",
                "docket_number": docket[:150] if docket else "",
                "decision_date": date_str,
                "year": int(yr) if yr.isdigit() else 2026,
                "chunk_index": c_idx,
                "pdf_url": pdf_public_url,
                "text_preview": chunk_text[:200],
                "text": chunk_text
            }
            batch_chunks.append(chunk_text)
            batch_meta.append((vec_id, meta))

        batch_case_ids.add(case_id)

        # When batch size reached or end of records, embed and upsert
        if len(batch_chunks) >= EMBED_BATCH_SIZE or idx == len(pending_items) - 1:
            embeddings = embed_texts_with_retry(batch_chunks)
            if embeddings:
                pinecone_vectors = []
                for emb, (v_id, meta) in zip(embeddings, batch_meta):
                    pinecone_vectors.append({
                        "id": v_id,
                        "values": emb,
                        "metadata": meta
                    })

                # Upsert to Pinecone in sub-batches of 100
                for p_idx in range(0, len(pinecone_vectors), PINECONE_BATCH_SIZE):
                    sub_v = pinecone_vectors[p_idx:p_idx + PINECONE_BATCH_SIZE]
                    upsert_vectors_to_pinecone(sub_v)

                total_chunks_indexed += len(pinecone_vectors)
                for c_id in batch_case_ids:
                    state["ingested_cases"][c_id] = True

                rate = total_chunks_indexed / (time.time() - t0_pine + 0.001)
                print(f"  Pinecone progress: {total_chunks_indexed:,} chunks indexed ({rate:.1f} chunks/sec)...", end="\r")

            batch_chunks = []
            batch_meta = []
            batch_case_ids = set()
            save_state(state)

    print(f"\n[PINECONE DONE] Finished {filename}: {total_chunks_indexed:,} chunks indexed in {time.time() - t0_pine:.1f}s.")
    save_state(state)

def main():
    print("=" * 80)
    print("PAKISTAN LEGAL MASTER CORPUS - PRODUCTION PINECONE INGESTION")
    print(f"Pinecone Index: {PINECONE_INDEX_NAME} (Namespace: '{NAMESPACE}')")
    print(f"Voyage AI Model: {VOYAGE_MODEL} (1024 Dim)")
    print("=" * 80)

    state = load_state()
    csv_files = sorted(glob.glob(os.path.join(CSV_DIR, "*_cleaned.csv")))

    t0_all = time.time()
    for f in csv_files:
        process_journal_pinecone(f, state)

    print("\n" + "=" * 80)
    print(f"ALL DATASETS INDEXED TO PINECONE!")
    print(f"Total Time Taken: {time.time() - t0_all:.1f}s")
    print("=" * 80)

if __name__ == "__main__":
    main()
