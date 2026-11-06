#!/usr/bin/env python3
"""
scripts/index_statutes_to_pinecone.py

Indexes all authentic Pakistani statutory provisions from Turso statute_provisions table
into Pinecone under the dedicated 'statutes' namespace using Voyage AI (voyage-law-2) embeddings.
"""

import os
import sys
import json
import time
import asyncio
from typing import List, Dict, Any

from core.turso_client import execute_turso_pipeline

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "legal-kb-pk-local")
PINECONE_HOST = os.environ.get("PINECONE_HOST", "https://legal-kb-pk-local-uc3rhld.svc.aped-4627-b74a.pinecone.io")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")
STATUTES_NAMESPACE = "statutes"

async def fetch_embeddings_batch(texts: List[str], max_retries: int = 3) -> List[List[float]]:
    import httpx
    url = "https://api.voyageai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {VOYAGE_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "input": [t[:3000] for t in texts],
        "model": "voyage-law-2",
        "input_type": "document"
    }
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return [item["embedding"] for item in data["data"]]
                else:
                    print(f"Voyage AI HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            if attempt == max_retries:
                raise e
            await asyncio.sleep(2.0 * attempt)
    return []

async def index_statutes_to_pinecone(batch_size: int = 32):
    if not PINECONE_API_KEY:
        print("ERROR: PINECONE_API_KEY is not set.")
        return {"status": "error", "message": "PINECONE_API_KEY not set"}
    if not VOYAGE_API_KEY:
        print("ERROR: VOYAGE_API_KEY is not set.")
        return {"status": "error", "message": "VOYAGE_API_KEY not set"}

    from pinecone import Pinecone
    pc = Pinecone(api_key=PINECONE_API_KEY)
    try:
        index = pc.Index(PINECONE_INDEX_NAME, host=PINECONE_HOST)
    except Exception:
        index = pc.Index(PINECONE_INDEX_NAME)

    print("Fetching all statutory provisions from Turso...")
    sql = "SELECT canonical_id, act_code, act_name, section_num, title, verbatim_text, domain, tier, in_force FROM statute_provisions"
    res = execute_turso_pipeline([{"sql": sql}])
    if not res or not res[0].get("rows"):
        print("No provisions found in Turso statute_provisions table.")
        return {"status": "error", "message": "No provisions in Turso"}

    provisions = res[0]["rows"]
    print(f"Loaded {len(provisions)} provisions from Turso.")

    total = len(provisions)
    indexed = 0
    t0 = time.time()

    for i in range(0, total, batch_size):
        chunk = provisions[i:i + batch_size]
        texts_to_embed = []
        for p in chunk:
            embed_text = f"{p['act_name']} Section {p['section_num']} - {p['title']}\n\n{p['verbatim_text']}"
            texts_to_embed.append(embed_text)

        try:
            embeddings = await fetch_embeddings_batch(texts_to_embed)
            if len(embeddings) != len(chunk):
                print(f"Embedding count mismatch at batch {i}: got {len(embeddings)} vs {len(chunk)}")
                continue

            vectors = []
            for j, p in enumerate(chunk):
                vid = f"statute_{p['canonical_id']}"
                v_text = p["verbatim_text"][:2000] if p.get("verbatim_text") else ""
                meta = {
                    "canonical_id": str(p["canonical_id"]),
                    "act_code": str(p["act_code"]),
                    "act_name": str(p["act_name"]),
                    "section_num": str(p["section_num"]),
                    "title": str(p["title"]),
                    "domain": str(p["domain"]),
                    "tier": str(p["tier"]),
                    "in_force": bool(p["in_force"]),
                    "text": v_text,
                    "type": "statute_provision"
                }
                vectors.append({
                    "id": vid,
                    "values": embeddings[j],
                    "metadata": meta
                })

            index.upsert(vectors=vectors, namespace=STATUTES_NAMESPACE)
            indexed += len(chunk)
            if indexed % 200 == 0 or indexed == total:
                pct = indexed * 100 // total
                elapsed = time.time() - t0
                print(f"Indexed {indexed}/{total} provisions ({pct}%) into Pinecone '{STATUTES_NAMESPACE}' namespace [{elapsed:.1f}s]")

            # Small pause to respect Voyage rate limits
            await asyncio.sleep(0.2)

        except Exception as e:
            print(f"Error indexing batch {i}-{i+len(chunk)}: {e}")

    print(f"Successfully finished indexing {indexed} provisions into Pinecone namespace '{STATUTES_NAMESPACE}'.")
    return {"status": "success", "indexed": indexed, "total": total}

if __name__ == "__main__":
    asyncio.run(index_statutes_to_pinecone())
