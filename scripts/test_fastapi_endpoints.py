import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["ENVIRONMENT"] = "test"

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_statute_endpoints():
    print("=" * 70)
    print("TESTING FASTAPI STATUTE ENDPOINTS")
    print("=" * 70)

    # 1. Search for 'willful default'
    r1 = client.get("/api/search/statutes?query=willful default&limit=5")
    print("1. GET /api/search/statutes?query=willful default -> Status:", r1.status_code)
    data1 = r1.json()
    print("   Total matches:", data1.get("total_matches"))
    for idx, r in enumerate(data1.get("results", [])[:3]):
        print(f"   [{idx+1}] {r.get('canonical_id')} - {r.get('display_name')} ({r.get('title')})")

    # 2. Search for 'wilful default'
    r2 = client.get("/api/search/statutes?query=wilful default&limit=5")
    print("\n2. GET /api/search/statutes?query=wilful default -> Status:", r2.status_code)
    data2 = r2.json()
    print("   Total matches:", data2.get("total_matches"))
    for idx, r in enumerate(data2.get("results", [])[:3]):
        print(f"   [{idx+1}] {r.get('canonical_id')} - {r.get('display_name')} ({r.get('title')})")

    # 3. Retrieve FIO 2(g)
    r3 = client.get("/api/statutes/FIO_2001_SEC_2_g")
    print("\n3. GET /api/statutes/FIO_2001_SEC_2_g -> Status:", r3.status_code)
    d3 = r3.json()
    print(f"   Canonical ID: {d3.get('canonical_id')}")
    print(f"   Act Name: {d3.get('act_name')}")
    print(f"   Section: {d3.get('primary_num')}")
    print(f"   Text (first 100 chars): {d3.get('text', '')[:100]}...")

    # 4. Retrieve NAO 5(u)
    r4 = client.get("/api/statutes/NAO_1999_SEC_5_u")
    print("\n4. GET /api/statutes/NAO_1999_SEC_5_u -> Status:", r4.status_code)
    d4 = r4.json()
    print(f"   Canonical ID: {d4.get('canonical_id')}")
    print(f"   Act Name: {d4.get('act_name')}")
    print(f"   Section: {d4.get('primary_num')}")
    print(f"   Text (first 100 chars): {d4.get('text', '')[:100]}...")

    # 5. Retrieve alias CONST_1973_SEC_199
    r5 = client.get("/api/statutes/CONST_1973_SEC_199")
    print("\n5. GET /api/statutes/CONST_1973_SEC_199 -> Status:", r5.status_code)
    d5 = r5.json()
    print(f"   Resolved Canonical ID: {d5.get('canonical_id')}")
    print(f"   Act Name: {d5.get('act_name')}")

if __name__ == "__main__":
    test_statute_endpoints()
