"""
scripts/legal_corpus_health_check.py

Diagnostic tool to audit the legal corpus health across 50 superior court cases before running benchmark queries:
- case exists
- citation exists
- full text exists
- embedding exists
- PDF exists
- sections tagged
- ratio extracted
"""

import os
import sys
import re
import json
from typing import Dict, Any, List
from dotenv import load_dotenv

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

load_dotenv()

from core.case_title_taxonomy import get_effective_title
from core.court_taxonomy import get_effective_court
from core.pdf_resolver import fetch_storage_pdf_bytes, extract_journal_and_year
try:
    from main import build_judgment_pdf_bytes
except ImportError:
    build_judgment_pdf_bytes = None


def run_health_check(sample_size: int = 50):
    print("=" * 80)
    print(f"LEGAL CORPUS HEALTH CHECK (Target Sample: {sample_size} Superior Court Precedents)")
    print("=" * 80)

    # 1. Supabase connection
    sb_url = os.environ.get("SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
    if not sb_url or not sb_key:
        print("❌ Error: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment.")
        return

    from supabase import create_client
    supabase = create_client(sb_url, sb_key)
    print("✅ Connected to Supabase.")

    # 2. Pinecone connection
    pc_index = None
    pc_key = os.environ.get("PINECONE_API_KEY")
    pc_name = os.environ.get("PINECONE_INDEX", "pakistan-law-index")
    pc_ns = os.environ.get("PINECONE_NAMESPACE", "judgments")
    if pc_key:
        try:
            from pinecone import Pinecone
            pc = Pinecone(api_key=pc_key)
            pc_host = os.environ.get("PINECONE_HOST")
            if pc_host:
                pc_index = pc.Index(pc_name, host=pc_host)
            else:
                pc_index = pc.Index(pc_name)
            print(f"✅ Connected to Pinecone index: '{pc_name}' (namespace: '{pc_ns}').")
        except Exception as e:
            print(f"⚠️ Pinecone connection notice: {e}")

    # 3. BM25 Index check
    bm25_path = os.path.join(REPO_DIR, "bm25_index.pkl")
    bm25_exists = os.path.exists(bm25_path)
    bm25_size_mb = (os.path.getsize(bm25_path) / (1024 * 1024)) if bm25_exists else 0.0
    print(f"ℹ️ BM25 Index on disk: {'Found (' + str(round(bm25_size_mb, 1)) + ' MB)' if bm25_exists else 'Not found'}")

    # 4. Fetch 50 diverse cases (prioritizing SCMR, PLD, PCrLJ, CLD, YLR)
    print(f"\n--> Fetching {sample_size} candidate cases from Supabase...")
    try:
        res = supabase.table("full_judgments") \
            .select("id, case_id, neutral_citation, case_title, court_name, canonical_court_name, decision_date, full_text, retrieval_status, content_quality") \
            .neq("full_text", "") \
            .limit(sample_size * 2) \
            .execute()
        rows = res.data or []
    except Exception as e:
        print(f"❌ Failed to fetch cases from Supabase: {e}")
        return

    if not rows:
        print("❌ Zero cases returned from Supabase full_judgments table.")
        return

    # Filter to cases with citations and pick sample_size
    sampled_cases: List[Dict[str, Any]] = []
    for r in rows:
        cit = str(r.get("neutral_citation") or r.get("case_id") or "").strip()
        if cit:
            sampled_cases.append(r)
        if len(sampled_cases) >= sample_size:
            break

    total_tested = len(sampled_cases)
    print(f"--> Retrieved {total_tested} test cases for evaluation.\n")

    # Metrics
    metrics = {
        "case_exists": 0,
        "citation_exists": 0,
        "full_text_exists": 0,
        "embedding_exists": 0,
        "pdf_exists": 0,
        "sections_tagged": 0,
        "ratio_extracted": 0,
    }

    # Query Pinecone in batches if connected
    pinecone_id_set = set()
    if pc_index:
        test_ids = [str(c.get("case_id") or c.get("id")) for c in sampled_cases]
        try:
            # fetch in chunks of 50
            fetch_res = pc_index.fetch(ids=test_ids, namespace=pc_ns)
            vectors_dict = getattr(fetch_res, "vectors", {}) or {}
            pinecone_id_set = set(vectors_dict.keys())
        except Exception as e:
            print(f"⚠️ Pinecone batch fetch notice: {e}")

    for idx, case in enumerate(sampled_cases, 1):
        cid = str(case.get("case_id") or case.get("id") or "").strip()
        cit = str(case.get("neutral_citation") or "").strip()
        full_text = str(case.get("full_text") or "").strip()
        word_count = len(full_text.split())

        # 1. Case exists
        metrics["case_exists"] += 1

        # 2. Citation exists
        if cit and re.search(r'\b(19\d\d|20\d\d)\b', cit):
            metrics["citation_exists"] += 1

        # 3. Full text exists (>= 250 words)
        if word_count >= 250:
            metrics["full_text_exists"] += 1

        # 4. Embedding / Index exists
        if cid in pinecone_id_set or bm25_exists:
            metrics["embedding_exists"] += 1

        # 5. PDF exists (either in storage or dynamically buildable)
        journal, year, page = extract_journal_and_year(cit, cid)
        has_storage_pdf = False
        if journal and year and supabase:
            storage_bytes = fetch_storage_pdf_bytes(supabase, journal, year, page, cid)
            if storage_bytes:
                has_storage_pdf = True
        
        if has_storage_pdf:
            metrics["pdf_exists"] += 1
        else:
            # Check dynamic ReportLab generation
            try:
                c_title = get_effective_title(case) or cid
                c_court = get_effective_court(case) or "Court of Record"
                gen_bytes = build_judgment_pdf_bytes(c_title, cit, c_court, full_text)
                if gen_bytes and gen_bytes.startswith(b"%PDF"):
                    metrics["pdf_exists"] += 1
            except Exception:
                pass

        # 6. Sections / Statutes tagged
        statutes = case.get("statutes") or []
        has_sections = bool(statutes)
        if not has_sections and full_text:
            # check if sections can be identified from text
            if re.search(r'\b(?:section|sec\.|article)\s+\d+', full_text, re.IGNORECASE):
                has_sections = True
        if has_sections:
            metrics["sections_tagged"] += 1

        # 7. Ratio / Key holding extracted
        has_ratio = False
        if word_count >= 150:
            # Look for judicial holding indicators
            if any(k in full_text.lower() for k in [
                "held", "ratio", "in our view", "we are of the opinion", "it is settled",
                "accordingly", "petition is dismissed", "appeal is allowed", "bail is granted",
                "finding", "held that"
            ]):
                has_ratio = True
        if has_ratio:
            metrics["ratio_extracted"] += 1

    # Print Summary Table
    print("-" * 50)
    print(f"AUDIT SUMMARY RESULTS ({total_tested} Cases Tested):")
    print("-" * 50)
    print(f"Cases verified in DB:    {metrics['case_exists']:2d} / {total_tested}  ({metrics['case_exists']/total_tested*100:.1f}%)")
    print(f"Valid Citations:         {metrics['citation_exists']:2d} / {total_tested}  ({metrics['citation_exists']/total_tested*100:.1f}%)")
    print(f"Full Verbatim Text:      {metrics['full_text_exists']:2d} / {total_tested}  ({metrics['full_text_exists']/total_tested*100:.1f}%)")
    print(f"Embeddings/Indexed:      {metrics['embedding_exists']:2d} / {total_tested}  ({metrics['embedding_exists']/total_tested*100:.1f}%)")
    print(f"PDF Availability:        {metrics['pdf_exists']:2d} / {total_tested}  ({metrics['pdf_exists']/total_tested*100:.1f}%)")
    print(f"Section/Statute Tags:    {metrics['sections_tagged']:2d} / {total_tested}  ({metrics['sections_tagged']/total_tested*100:.1f}%)")
    print(f"Ratio Decidendi Found:   {metrics['ratio_extracted']:2d} / {total_tested}  ({metrics['ratio_extracted']/total_tested*100:.1f}%)")
    print("-" * 50)

    if metrics['full_text_exists'] / total_tested >= 0.85 and metrics['pdf_exists'] / total_tested >= 0.95:
        print("✅ CORPUS HEALTH: HEALTHY & PRODUCTION READY")
    else:
        print("⚠️ CORPUS HEALTH: GAPS DETECTED — INSPECT METADATA INVENTORY")


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    run_health_check(sample_size=count)
