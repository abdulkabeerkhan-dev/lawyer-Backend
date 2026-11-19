import sys
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from legal_ai.retrieval.statute_search import search_statutes_hybrid, get_statute_by_canonical_id
from legal_ai.query_engine.statute_router import build_evidence_pack_for_query
from legal_ai.search.statute_search_service import search_statute_provisions, get_provision_full_text

async def main():
    print("=" * 70)
    print("PHASE 2 RETRIEVAL VERIFICATION")
    print("=" * 70)

    for query in ["willful default", "wilful default"]:
        print(f"\n--- Testing Query: '{query}' ---")
        
        # 1. Zilliz Cloud hybrid search
        hits = await search_statutes_hybrid(query, top_k=5)
        print(f"1. search_statutes_hybrid hits: {len(hits)}")
        for idx, h in enumerate(hits[:3]):
            cid = h.get("canonical_id")
            act = h.get("act_name")
            sec = h.get("section")
            score = h.get("score", 0.0)
            txt = h.get("text", "")[:100].replace("\n", " ")
            print(f"   [{idx+1}] {cid} | {act} s.{sec} | score: {score:.4f}")
            print(f"       Preview: {txt}...")

        # 2. Evidence Pack
        pack, intent = build_evidence_pack_for_query(query)
        print(f"2. Evidence Pack items: {len(pack.items)}")
        for k, v in pack.items.items():
            print(f"   {k}: {v.statute_title} | {v.unit_type} {v.number} - {v.heading_description}")

        # 3. Statute search service
        svc_res = search_statute_provisions(query, limit=5)
        print(f"3. search_statute_provisions top 2:")
        for idx, r in enumerate(svc_res.get("results", [])[:2]):
            print(f"   [{idx+1}] {r.get('canonical_id')} | {r.get('display_name')} | {r.get('title')}")

    # 4. Pinpoint lookup
    print("\n--- Pinpoint Lookup ---")
    fio = get_statute_by_canonical_id("FIO_2001_SEC_2_g")
    print("FIO_2001_SEC_2_g found:", bool(fio), fio.get("act_name") if fio else None)
    nao = get_statute_by_canonical_id("NAO_1999_SEC_5_u")
    print("NAO_1999_SEC_5_u found:", bool(nao), nao.get("act_name") if nao else None)

    # 5. Citation Alias
    alias = get_statute_by_canonical_id("CONST_1973_SEC_199")
    print("CONST_1973_SEC_199 alias resolved:", bool(alias), alias.get("canonical_id") if alias else None)

if __name__ == "__main__":
    asyncio.run(main())
