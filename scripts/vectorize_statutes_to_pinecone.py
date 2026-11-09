#!/usr/bin/env python3
"""
scripts/vectorize_statutes_to_pinecone.py

Generates 1024-dimension embeddings using Voyage Law-2 (voyage-law-2)
and upserts them into Pinecone index 'legal-kb-pk-local' under namespace 'statutes'.
Includes checkpointing, batching, and error recovery.
"""

import os
import sys
import json
import time
import sqlite3
import urllib.request
import urllib.error
from pinecone import Pinecone

DB_PATH = r"I:\Statutes\pakistan_statutes_master.db"
CHECKPOINT_PATH = r"I:\Statutes\pinecone_vector_checkpoint.json"

PINECONE_API_KEY = "pcsk_6Fq836_Si8eHmgEs2BFCbJC3cXsfZqg1B2UeXFUVYEu3aAXJdnE5BS1GvVUtv9UHe39XU8"
PINECONE_INDEX_NAME = "legal-kb-pk-local"
PINECONE_NAMESPACE = "statutes"

VOYAGE_API_KEY = "pa-uJAWGzb5_Z5GJKsXKYXORK7b8ndyc3J1_Viz3Nbrxzi"
VOYAGE_MODEL = "voyage-law-2"

BATCH_SIZE = 64  # Voyage recommends 32-128 items per batch

def get_voyage_embeddings(texts: list, max_retries: int = 5) -> list:
    payload = json.dumps({
        "input": texts,
        "model": VOYAGE_MODEL,
        "input_type": "document"
    }).encode("utf-8")

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                "https://api.voyageai.com/v1/embeddings",
                data=payload,
                headers={
                    "Authorization": f"Bearer {VOYAGE_API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [d["embedding"] for d in data["data"]]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait_time = 10 * attempt
                print(f"Voyage rate limit (429). Sleeping {wait_time}s...", flush=True)
                time.sleep(wait_time)
            else:
                print(f"Voyage HTTPError {e.code}: {e.read().decode()}", flush=True)
                if attempt == max_retries:
                    return []
                time.sleep(2 * attempt)
        except Exception as e:
            print(f"Voyage error (attempt {attempt}): {e}", flush=True)
            if attempt == max_retries:
                return []
            time.sleep(2 * attempt)
    return []

def main():
    print("=" * 70, flush=True)
    print("PINECONE STATUTE VECTOR EMBEDDING PIPELINE", flush=True)
    print(f"Index: {PINECONE_INDEX_NAME} | Namespace: {PINECONE_NAMESPACE} | Model: {VOYAGE_MODEL}", flush=True)
    print("=" * 70, flush=True)

    if not os.path.exists(DB_PATH):
        print(f"ERROR: SQLite database not found at {DB_PATH}", flush=True)
        sys.exit(1)

    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX_NAME)

    checkpoint = 0
    if os.path.exists(CHECKPOINT_PATH):
        try:
            with open(CHECKPOINT_PATH, "r") as fp:
                chk = json.load(fp)
                checkpoint = chk.get("last_offset", 0)
                print(f"Resuming from checkpoint offset: {checkpoint:,}", flush=True)
        except Exception as e:
            print(f"Notice: Failed to load checkpoint: {e}", flush=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM statutes")
    total_statutes = cur.fetchone()[0]
    print(f"Total provisions to embed: {total_statutes:,}", flush=True)

    cur.execute("""
    SELECT canonical_id, jurisdiction, statute_title, section_number, section_title, full_text, rowid
    FROM statutes
    WHERE rowid > ?
    ORDER BY rowid ASC
    """, (checkpoint,))

    records_batch = []
    processed = checkpoint
    batch_count = 0
    start_time = time.time()

    while True:
        rows = cur.fetchmany(1000)
        if not rows:
            break

        for row in rows:
            cid, jur, title, sec_num, sec_title, full_txt, r_id = row
            # Build embedding text: statute title + section + first 1500 chars of text
            content_snippet = (full_txt or "")[:1500].strip()
            embed_text = f"{title} ({jur})\nSection: {sec_num} - {sec_title or ''}\n{content_snippet}".strip()

            records_batch.append({
                "id": cid,
                "text": embed_text,
                "rowid": r_id,
                "metadata": {
                    "canonical_id": cid,
                    "jurisdiction": jur,
                    "statute_title": title[:100],
                    "section_number": sec_num[:50],
                    "section_title": (sec_title or "")[:100]
                }
            })

            if len(records_batch) >= BATCH_SIZE:
                texts = [r["text"] for r in records_batch]
                embeddings = get_voyage_embeddings(texts)

                if embeddings and len(embeddings) == len(records_batch):
                    vectors_to_upsert = []
                    for rec, emb in zip(records_batch, embeddings):
                        vectors_to_upsert.append({
                            "id": rec["id"],
                            "values": emb,
                            "metadata": rec["metadata"]
                        })

                    index.upsert(vectors=vectors_to_upsert, namespace=PINECONE_NAMESPACE)
                    processed += len(records_batch)
                    batch_count += 1
                    records_batch = []

                    if batch_count % 5 == 0:
                        with open(CHECKPOINT_PATH, "w") as fp:
                            json.dump({"last_offset": r_id, "upserted_provisions": processed}, fp)
                        elapsed = time.time() - start_time
                        rate = (processed - checkpoint) / max(elapsed, 1.0)
                        print(f"  Upserted: {processed:,} / {total_statutes:,} provisions ({rate:.1f} vec/s)", flush=True)
                else:
                    print(f"Embedding failed for batch ending at rowid {r_id}. Retrying in 5s...", flush=True)
                    time.sleep(5)

    if records_batch:
        texts = [r["text"] for r in records_batch]
        embeddings = get_voyage_embeddings(texts)
        if embeddings and len(embeddings) == len(records_batch):
            vectors_to_upsert = [{
                "id": rec["id"],
                "values": emb,
                "metadata": rec["metadata"]
            } for rec, emb in zip(records_batch, embeddings)]
            index.upsert(vectors=vectors_to_upsert, namespace=PINECONE_NAMESPACE)
            processed += len(records_batch)

    conn.close()
    print("=" * 70, flush=True)
    print(f"Pinecone Vector Ingestion Complete! Total in namespace '{PINECONE_NAMESPACE}': {processed:,}", flush=True)
    print("=" * 70, flush=True)

if __name__ == "__main__":
    main()
