import asyncio, sys
from dotenv import load_dotenv
load_dotenv('D:/lawyer-Backend/.env')
sys.path.append('D:/lawyer-Backend')
from legal_ai.retrieval.statute_search import search_statutes_hybrid

async def test():
    print("=== Query: 'eviction notice' ===")
    res1 = await search_statutes_hybrid('eviction notice', top_k=5)
    for r in res1:
        print(f"  {r['canonical_id']} | {r['act_name']} | {r['heading']}")

    print("\n=== Query: 'Just gave an eviction notice' ===")
    res2 = await search_statutes_hybrid('Just gave an eviction notice', top_k=10)
    for r in res2:
        print(f"  {r['canonical_id']} | {r['act_name']} | {r['heading']}")

asyncio.run(test())
