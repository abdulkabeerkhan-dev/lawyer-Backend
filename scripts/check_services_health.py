"""
scripts/check_services_health.py

Performs health and connectivity diagnostics on:
1. Railway Production Deployment
2. Pinecone Vector Database
3. Supabase Database
4. Anthropic Claude API
5. Local In-Memory / Disk Stores (BM25 Index & Statute Store)

Outputs diagnostic results with response times and statuses without logging any secret values.
"""

import os
import sys
import time
import urllib.request
import json
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
os.chdir(REPO_DIR)
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

load_dotenv(".env")

print("=" * 70)
print("COMPREHENSIVE BACKEND SERVICES HEALTH CHECK")
print("=" * 70)

results = {}

# 1. RAILWAY PRODUCTION APP
print("\n[1/5] Checking Railway Production Deployment...")
prod_url = "https://lawyer-backend-production-3b52.up.railway.app"
try:
    t0 = time.time()
    req = urllib.request.Request(f"{prod_url}/health", headers={"User-Agent": "HealthCheck/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        status_code = resp.getcode()
        body = json.loads(resp.read().decode("utf-8"))
        latency = (time.time() - t0) * 1000
        if status_code == 200 and body.get("healthy"):
            print(f"  --> Railway: ONLINE & HEALTHY ({latency:.1f}ms)")
            print(f"      Status: {body.get('status')}, Model: {body.get('model')}, Version: {body.get('version')}")
            results["railway"] = {"status": "ONLINE", "healthy": True, "latency_ms": round(latency, 1), "details": body}
        else:
            print(f"  --> Railway: UNEXPECTED RESPONSE ({status_code}) -> {body}")
            results["railway"] = {"status": "WARNING", "healthy": False, "details": body}
except Exception as e:
    print(f"  --> Railway: ERROR connecting to {prod_url}: {e}")
    results["railway"] = {"status": "OFFLINE", "error": str(e)}

# 2. PINECONE VECTOR DATABASE
print("\n[2/5] Checking Pinecone Vector Database...")
pinecone_key = os.getenv("PINECONE_API_KEY")
pinecone_idx_name = os.getenv("PINECONE_INDEX_NAME", "legal-kb-pk")
pinecone_host = os.getenv("PINECONE_HOST", "https://legal-kb-pk-local-uc3rhld.svc.aped-4627-b74a.pinecone.io")

if not pinecone_key:
    print("  --> Pinecone: PINECONE_API_KEY is not set in environment.")
    results["pinecone"] = {"status": "NOT_CONFIGURED"}
else:
    try:
        from pinecone import Pinecone
        t0 = time.time()
        pc = Pinecone(api_key=pinecone_key)
        try:
            idx = pc.Index(pinecone_idx_name, host=pinecone_host)
        except Exception:
            idx = pc.Index(pinecone_idx_name)
        stats = idx.describe_index_stats()
        latency = (time.time() - t0) * 1000
        total_vectors = stats.get("total_vector_count", stats.get("total_vectors", 0))
        dimension = stats.get("dimension", 0)
        print(f"  --> Pinecone: ONLINE & CONNECTED ({latency:.1f}ms)")
        print(f"      Index: {pinecone_idx_name}, Total Vectors: {total_vectors:,}, Dimension: {dimension}")
        results["pinecone"] = {"status": "ONLINE", "healthy": True, "latency_ms": round(latency, 1), "total_vectors": total_vectors, "dimension": dimension}
    except Exception as e:
        print(f"  --> Pinecone: FAILED -> {e}")
        results["pinecone"] = {"status": "ERROR", "healthy": False, "error": str(e)}

# 3. SUPABASE DATABASE
print("\n[3/5] Checking Supabase Database...")
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    print("  --> Supabase: SUPABASE_URL or SUPABASE_KEY not set in environment.")
    results["supabase"] = {"status": "NOT_CONFIGURED"}
else:
    try:
        from supabase import create_client
        t0 = time.time()
        sb = create_client(supabase_url, supabase_key)
        # Test query on 'queries' table
        res = sb.table("queries").select("id", count="exact").limit(1).execute()
        latency = (time.time() - t0) * 1000
        total_queries = res.count if hasattr(res, "count") and res.count is not None else len(res.data)
        print(f"  --> Supabase: ONLINE & CONNECTED ({latency:.1f}ms)")
        print(f"      Host: {supabase_url.split('//')[-1].split('.')[0]}... | 'queries' table active (total records: {total_queries:,})")
        results["supabase"] = {"status": "ONLINE", "healthy": True, "latency_ms": round(latency, 1), "rows_found": total_queries}
    except Exception as e:
        print(f"  --> Supabase: FAILED -> {e}")
        results["supabase"] = {"status": "ERROR", "healthy": False, "error": str(e)}

# 4. ANTHROPIC CLAUDE API
print("\n[4/5] Checking Anthropic Claude API...")
anthropic_key = os.getenv("ANTHROPIC_API_KEY")
if not anthropic_key:
    print("  --> Anthropic: ANTHROPIC_API_KEY not set in environment.")
    results["anthropic"] = {"status": "NOT_CONFIGURED"}
else:
    try:
        from anthropic import Anthropic
        t0 = time.time()
        client = Anthropic(api_key=anthropic_key)
        model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        resp = client.messages.create(
            model=model,
            max_tokens=10,
            messages=[{"role": "user", "content": "Ping"}]
        )
        latency = (time.time() - t0) * 1000
        reply = resp.content[0].text.strip()
        print(f"  --> Anthropic: ONLINE & OPERATIONAL ({latency:.1f}ms)")
        print(f"      Model: {model}, Verified response received")
        results["anthropic"] = {"status": "ONLINE", "healthy": True, "latency_ms": round(latency, 1), "model": model}
    except Exception as e:
        print(f"  --> Anthropic: FAILED -> {e}")
        results["anthropic"] = {"status": "ERROR", "healthy": False, "error": str(e)}

# 5. LOCAL BM25 INDEX & STATUTE STORE
print("\n[5/5] Checking BM25 Index & Statute Store...")
try:
    import pickle
    bm25_file = "bm25_index.pkl"
    if os.path.exists(bm25_file):
        with open(bm25_file, "rb") as f:
            bm25_data = pickle.load(f)
        chunks = len(bm25_data.get("doc_ids", []))
        print(f"  --> BM25 Index: LOADED ({chunks:,} indexed judicial chunks)")
    else:
        chunks = 0
        print(f"  --> BM25 Index: NOT FOUND at {bm25_file}")
    
    statutes_dir = os.path.join("data", "statutes_v2")
    statute_files = [f for f in os.listdir(statutes_dir) if f.endswith(".json")] if os.path.exists(statutes_dir) else []
    print(f"  --> Verified Statute Store (v2): {len(statute_files)} primary acts present ({', '.join(f.replace('.json', '') for f in statute_files[:5])}...)")
    
    results["local_indices"] = {
        "status": "ONLINE",
        "healthy": chunks > 0 and len(statute_files) > 0,
        "bm25_chunks": chunks,
        "statute_acts": len(statute_files)
    }
except Exception as e:
    print(f"  --> Local Stores: FAILED -> {e}")
    results["local_indices"] = {"status": "ERROR", "healthy": False, "error": str(e)}

print("\n" + "=" * 70)
all_online = all(v.get("healthy", False) for v in results.values())
if all_online:
    print("ALL 5 CORE SUBSYSTEMS ARE 100% ONLINE AND OPERATIONAL!")
else:
    print("SOME SERVICES HAVE WARNINGS OR ERRORS.")
print("=" * 70)
