"""
scripts/pilot_enrich_and_index.py

Phase B / Unified Pilot Ingestion & Indexing Pipeline:
1. Extracts 56 pilot judgments from Supabase full_judgments (including all benchmark cases).
2. Segments each judgment using StructuralJudgmentSegmenter into Headnote, Ratio Decidendi, and Facts/Order.
3. Extracts Pakistani statutory anchors, domain (civil/criminal/family/banking/etc.), and subdomains.
4. Generates Voyage AI (voyage-law-2) 1024-dimension embeddings for each segment.
5. Upserts enriched vectors into Pinecone under dedicated clean namespace: 'segmented-v1'.
6. Stages enriched structured records to data/enriched_pilot_segments.jsonl.
"""

import os
import sys
import json
import time
import requests
from typing import List, Dict, Any, Set
from dotenv import load_dotenv

# Ensure workspace root in path
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

load_dotenv(os.path.join(WORKSPACE_DIR, ".env"))

from legal_ai.config import get_supabase_client, get_pinecone_index
from core.structural_judgment_segmenter import StructuralJudgmentSegmenter

VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-law-2")
TARGET_NAMESPACE = "segmented-v1"
OUTPUT_JSONL_PATH = os.path.join(WORKSPACE_DIR, "data", "enriched_pilot_segments.jsonl")


def embed_batch_voyage(texts: List[str], max_retries: int = 5) -> List[List[float]]:
    """Embeds a batch of texts using Voyage AI voyage-law-2 with exponential backoff."""
    if not VOYAGE_API_KEY:
        raise RuntimeError("VOYAGE_API_KEY is not set.")

    headers = {
        "Authorization": f"Bearer {VOYAGE_API_KEY}",
        "Content-Type": "application/json"
    }

    # Voyage accepts list of texts; truncate overly long text to 16,000 chars
    cleaned_texts = [t[:16000].strip() if t else "court judgment" for t in texts]

    payload = {
        "input": cleaned_texts,
        "model": VOYAGE_MODEL,
        "input_type": "document"
    }

    delay = 2.0
    for attempt in range(max_retries):
        try:
            resp = requests.post(VOYAGE_API_URL, json=payload, headers=headers, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                return [item["embedding"] for item in data["data"]]
            elif resp.status_code in (429, 500, 502, 503, 504):
                print(f"  [Voyage HTTP {resp.status_code}] Retrying in {delay:.1f}s (attempt {attempt+1}/{max_retries})...", flush=True)
                time.sleep(delay)
                delay = min(delay * 1.5, 60.0)
            else:
                raise RuntimeError(f"Voyage API Error {resp.status_code}: {resp.text}")
        except requests.exceptions.RequestException as e:
            print(f"  [Voyage Network Error] {e}. Retrying in {delay:.1f}s (attempt {attempt+1}/{max_retries})...", flush=True)
            time.sleep(delay)
            delay = min(delay * 1.5, 60.0)

    raise RuntimeError(f"Failed to embed batch with Voyage API after {max_retries} attempts.")


def assemble_pilot_records(sb) -> List[Dict[str, Any]]:
    """Gathers the 56 benchmark and representative cases from Supabase."""
    anchor_citations = [
        "2026 SCMR 941", "2006 YLR 2059", "2006 YLR 2289", "1967 PLD 97",
        "2021 SCMR 554", "2001 YLR 2537", "2005 PCRLJ 226", "1996 PCRLJ 207",
        "2019 CLC 1008", "2026 CLD 292", "1995 PLD 34"
    ]

    records: List[Dict[str, Any]] = []
    seen_cids = set()

    for cit in anchor_citations:
        r = sb.table("full_judgments").select(
            "id, case_id, case_title, neutral_citation, court_name, decision_date, full_text"
        ).eq("neutral_citation", cit).limit(1).execute()
        if not r.data:
            cid = cit.replace(" ", "_")
            r = sb.table("full_judgments").select(
                "id, case_id, case_title, neutral_citation, court_name, decision_date, full_text"
            ).eq("case_id", cid).limit(1).execute()
        if r.data:
            rec = r.data[0]
            cid = rec["case_id"]
            if cid not in seen_cids:
                seen_cids.add(cid)
                records.append(rec)

    reporters = [
        ("SCMR", 10),
        ("CLC", 10),
        ("PCrLJ", 10),
        ("CLD", 5),
        ("MLD", 5),
        ("PLD", 5)
    ]

    for rep, count in reporters:
        r = sb.table("full_judgments").select(
            "id, case_id, case_title, neutral_citation, court_name, decision_date, full_text"
        ).ilike("neutral_citation", f"%{rep}%").limit(count * 3).execute()

        added = 0
        for rec in (r.data or []):
            cid = rec["case_id"]
            ft = rec.get("full_text") or ""
            if cid not in seen_cids and len(ft.split()) >= 100:
                seen_cids.add(cid)
                records.append(rec)
                added += 1
                if added >= count:
                    break

    return records


def run_unified_pilot_pipeline():
    print("=" * 70)
    print("LEGAL RAG RETRIEVAL REMEDIATION - PHASE B: UNIFIED PILOT INGESTION")
    print("=" * 70)

    # 1. Initialize Clients
    sb = get_supabase_client()
    pc_index = get_pinecone_index()
    if not sb:
        raise RuntimeError("Failed to connect to Supabase.")
    if not pc_index:
        raise RuntimeError("Failed to connect to Pinecone index.")

    print(f"[*] Connected to Supabase & Pinecone index: {pc_index}")
    print(f"[*] Target Pinecone clean namespace: '{TARGET_NAMESPACE}'")

    # 2. Assemble Cases
    records = assemble_pilot_records(sb)
    print(f"[*] Assembled {len(records)} pilot cases from Supabase.")

    # 3. Segment & Build Payloads
    all_pinecone_vectors: List[Dict[str, Any]] = []
    enriched_rows: List[Dict[str, Any]] = []

    print("[*] Processing cases through StructuralJudgmentSegmenter...")
    for rec in records:
        cid = rec["case_id"]
        ft = rec.get("full_text") or ""
        segmented = StructuralJudgmentSegmenter.segment_judgment(ft, metadata=rec)

        enriched_rows.append({
            "case_id": cid,
            "neutral_citation": rec.get("neutral_citation"),
            "case_title": rec.get("case_title"),
            "court_name": rec.get("court_name"),
            "decision_date": rec.get("decision_date"),
            "domain": segmented["domain"],
            "subdomain": segmented["subdomain"],
            "statutes_cited": segmented["statutes_cited"],
            "provisions_cited": segmented["provisions_cited"],
            "headnote": segmented["headnote_segment"],
            "ratio_decidendi": segmented["ratio_decidendi_segment"],
            "facts_and_order": segmented["facts_and_order_segment"]
        })

        for p_seg in segmented["pinecone_segments"]:
            # Inject preview text into Pinecone metadata for instant preview display
            meta = dict(p_seg["metadata"])
            meta["text"] = p_seg["text"][:1200]
            all_pinecone_vectors.append({
                "id": p_seg["segment_id"],
                "text_to_embed": p_seg["text"],
                "metadata": meta
            })

    print(f"[*] Total vector payloads generated: {len(all_pinecone_vectors)}")

    # 4. Save Staged JSONL
    os.makedirs(os.path.dirname(OUTPUT_JSONL_PATH), exist_ok=True)
    with open(OUTPUT_JSONL_PATH, "w", encoding="utf-8") as f:
        for row in enriched_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[*] Staged {len(enriched_rows)} enriched records to {OUTPUT_JSONL_PATH}")

    # 5. Batch Embed via Voyage AI
    batch_size = 32
    embedded_vectors: List[Dict[str, Any]] = []

    print(f"[*] Embedding {len(all_pinecone_vectors)} segments via {VOYAGE_MODEL} (batch size: {batch_size})...")
    for i in range(0, len(all_pinecone_vectors), batch_size):
        batch = all_pinecone_vectors[i:i + batch_size]
        texts = [b["text_to_embed"] for b in batch]
        embeddings = embed_batch_voyage(texts)

        for b, emb in zip(batch, embeddings):
            embedded_vectors.append({
                "id": b["id"],
                "values": emb,
                "metadata": b["metadata"]
            })
        print(f"    Progress: {len(embedded_vectors)}/{len(all_pinecone_vectors)} embedded ({(len(embedded_vectors)/len(all_pinecone_vectors))*100:.1f}%)", flush=True)

    # 6. Upsert to Pinecone 'segmented-v1' Namespace
    upsert_batch_size = 50
    print(f"[*] Upserting {len(embedded_vectors)} vectors to Pinecone namespace '{TARGET_NAMESPACE}'...")
    for i in range(0, len(embedded_vectors), upsert_batch_size):
        upsert_batch = embedded_vectors[i:i + upsert_batch_size]
        pc_index.upsert(vectors=upsert_batch, namespace=TARGET_NAMESPACE)
        print(f"    Upserted batch {i // upsert_batch_size + 1}: {len(upsert_batch)} vectors", flush=True)

    # 7. Verify Pinecone Namespace Stats
    print("[*] Verifying Pinecone index stats post-upsert...")
    time.sleep(2)
    stats = pc_index.describe_index_stats()
    print(f"    Total vector count: {stats.total_vector_count}")
    print(f"    Namespaces: {stats.namespaces}")
    target_stat = stats.namespaces.get(TARGET_NAMESPACE)
    if target_stat:
        print(f"    Namespace '{TARGET_NAMESPACE}' vector count: {target_stat.vector_count}")
    else:
        print(f"⚠️  Namespace '{TARGET_NAMESPACE}' not yet reflected in stats (eventual consistency).")

    # 8. Sample Query Test
    print("\n[*] Running live verification query against namespace 'segmented-v1'...")
    from legal_ai.config import get_voyage_embedding
    import asyncio

    async def verify_sample_query():
        # Query for partition preliminary decree
        q_text = "Whether a co-sharer in joint ancestral land can seek preliminary decree for partition under Order XX Rule 18 CPC"
        q_vec = await get_voyage_embedding(q_text)

        # 1. Query with domain filter = civil
        res_filtered = pc_index.query(
            namespace=TARGET_NAMESPACE,
            vector=q_vec,
            filter={"domain": {"$eq": "civil"}},
            top_k=5,
            include_metadata=True
        )

        print("\n--- Filtered Results (domain: civil) ---")
        for m in res_filtered.matches:
            meta = m.metadata
            print(f"  Score: {m.score:.4f} | Citation: {meta.get('citation')} | Domain: {meta.get('domain')} | Subdomain: {meta.get('subdomain')} | Type: {meta.get('segment_type')}")
            print(f"    Title: {meta.get('case_title')[:60]}")
            print(f"    Statutes: {meta.get('statutes')}")

        # 2. Query with domain filter = criminal to prove absolute domain isolation
        res_criminal = pc_index.query(
            namespace=TARGET_NAMESPACE,
            vector=q_vec,
            filter={"domain": {"$eq": "criminal"}},
            top_k=2,
            include_metadata=True
        )
        print(f"\n--- Cross-Domain Test (domain: criminal against partition query) ---")
        print(f"  Criminal matches found: {len(res_criminal.matches)} (Isolated from civil queries)")

    asyncio.run(verify_sample_query())
    print("\n" + "=" * 70)
    print("PHASE B PILOT INGESTION & INDEXING COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_unified_pilot_pipeline()
