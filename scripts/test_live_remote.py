import urllib.request
import urllib.parse
import json

base = 'https://lawyer-backend-production-5c6d.up.railway.app'

print("=== CHECKING REMOTE RAILWAY BACKEND ===")
req = urllib.request.urlopen(f"{base}/health", timeout=10)
health = json.loads(req.read().decode())
print("Health:", health)

for q in ['willful default', 'wilful default']:
    url = f"{base}/api/search/statutes?query={urllib.parse.quote(q)}"
    req = urllib.request.urlopen(url, timeout=10)
    data = json.loads(req.read().decode())
    print(f"\n=== Query: '{q}' ===")
    print("Total matches:", data.get('total_matches'))
    for idx, r in enumerate(data.get('results', [])[:5]):
        print(f"  [{idx+1}] {r.get('canonical_id')} | {r.get('act_name')} | {r.get('title')}")

for cid in ['FIO_2001_SEC_2_g', 'NAO_1999_SEC_5_u', 'CONST_1973_SEC_199']:
    url = f"{base}/api/statutes/{cid}"
    try:
        req = urllib.request.urlopen(url, timeout=10)
        data = json.loads(req.read().decode())
        print(f"\n=== Pinpoint: {cid} ===")
        print(f"  Found: {data.get('act_name')} | Section: {data.get('section')} | Heading: {data.get('heading')}")
    except Exception as e:
        print(f"\n=== Pinpoint: {cid} -> Error: {e} ===")
