r"""
scripts/test_statutes_v3_retrieval.py

Tests hybrid dense (Voyage-4-Large) + sparse (BM25) search on `statutes_v3` in Zilliz Cloud
for queries like "willful default" and "wilful default".
"""

import os
import sys
import json
import re
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(r"d:\lawyer-Backend")
load_dotenv(ROOT_DIR / ".env")

import voyageai
from pymilvus import MilvusClient, AnnSearchRequest, RRFRanker

ZILLIZ_URI = os.environ.get("ZILLIZ_URI")
ZILLIZ_TOKEN = os.environ.get("ZILLIZ_TOKEN")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")

COLLECTION_NAME = "statutes_v3"

def run_test():
    print("=" * 70)
    print("TESTING RETRIEVAL ON STATUTES_V3 (HYBRID SEARCH)")
    print("=" * 70)

    zclient = MilvusClient(uri=ZILLIZ_URI, token=ZILLIZ_TOKEN)
    vclient = voyageai.Client(api_key=VOYAGE_API_KEY)

    queries = ["willful default", "wilful default"]

    for q in queries:
        print(f"\n" + "-" * 50)
        print(f"QUERY: '{q}'")
        print("-" * 50)

        # Normalize query spelling
        norm_q = re.sub(r'\bwilful\b', 'willful', q, flags=re.I)

        # Dense embedding via Voyage
        res = vclient.embed([norm_q], model="voyage-4-large", input_type="query")
        dense_vec = res.embeddings[0]

        # 1. Dense search request
        dense_req = AnnSearchRequest(
            data=[dense_vec],
            anns_field="dense",
            param={"metric_type": "COSINE"},
            limit=20,
            expr="in_force == true"
        )

        # 2. Sparse BM25 search request
        sparse_req = AnnSearchRequest(
            data=[norm_q],
            anns_field="sparse",
            param={"metric_type": "BM25"},
            limit=20,
            expr="in_force == true"
        )

        # 3. Hybrid Search with RRF
        hybrid_res = zclient.hybrid_search(
            collection_name=COLLECTION_NAME,
            reqs=[dense_req, sparse_req],
            ranker=RRFRanker(k=60),
            limit=10,
            output_fields=["canonical_id", "act_code", "act_name", "section", "heading", "domain", "forum", "text"]
        )

        hits = hybrid_res[0]
        print(f"Top {len(hits)} Results:")
        for idx, hit in enumerate(hits):
            cid = hit["entity"].get("canonical_id")
            act = hit["entity"].get("act_name")
            sec = hit["entity"].get("section")
            hdg = hit["entity"].get("heading")
            txt = hit["entity"].get("text", "")[:180].replace("\n", " ")
            score = hit.get("distance", 0.0)
            print(f"  [{idx+1:2d}] Score: {score:.4f} | {cid} ({act} s.{sec}) - {hdg}")
            print(f"       Preview: {txt}...")

if __name__ == "__main__":
    run_test()
