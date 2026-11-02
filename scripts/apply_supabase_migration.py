"""
scripts/apply_supabase_migration.py

Applies structured legal segmentation schema migrations to Supabase PostgreSQL.
Supports direct execution via Supabase Management API using personal access token.

Usage:
    python scripts/apply_supabase_migration.py --token <sbp_...>
"""

import os
import sys
import argparse
import requests
import time

def parse_args():
    parser = argparse.ArgumentParser(description="Apply Supabase schema migration")
    parser.add_argument("--token", default=os.getenv("SUPABASE_ACCESS_TOKEN"), help="Supabase personal access token (sbp_...)")
    parser.add_argument("--project-ref", default=None, help="Supabase project reference ID")
    return parser.parse_args()

def get_project_ref(provided_ref: str | None) -> str:
    if provided_ref:
        return provided_ref
    supabase_url = os.getenv("SUPABASE_URL", "")
    if supabase_url:
        ref = supabase_url.replace("https://", "").split(".")[0]
        if ref:
            return ref
    return "dexolywhperqvmnyqxpd"

def execute_query(token: str, ref: str, sql: str, label: str = "Query", timeout: int = 120):
    url = f"https://api.supabase.com/v1/projects/{ref}/database/query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    print(f"--> Executing: {label}...")
    start_time = time.time()
    try:
        r = requests.post(url, headers=headers, json={"query": sql}, timeout=timeout)
        elapsed = time.time() - start_time
        if r.status_code == 201:
            print(f"    [SUCCESS] {label} completed in {elapsed:.2f}s")
            return True, r.json()
        else:
            print(f"    [ERROR] {label} failed (status {r.status_code}) after {elapsed:.2f}s: {r.text}")
            return False, r.text
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"    [EXCEPTION] {label} encountered error after {elapsed:.2f}s: {e}")
        return False, str(e)

def main():
    args = parse_args()
    token = args.token
    if not token:
        print("ERROR: --token or SUPABASE_ACCESS_TOKEN environment variable is required.", file=sys.stderr)
        sys.exit(1)

    ref = get_project_ref(args.project_ref)
    print(f"=== Supabase Migration Runner ===")
    print(f"Target Project Ref: {ref}")

    # Step 0: Test connection
    ok, _ = execute_query(token, ref, "SELECT 1 as test;", "Connection Probe")
    if not ok:
        sys.exit(1)

    # Step 1: Add columns
    sql_cols = """
    ALTER TABLE public.full_judgments 
        ADD COLUMN IF NOT EXISTS domain VARCHAR(50),
        ADD COLUMN IF NOT EXISTS subdomain VARCHAR(50),
        ADD COLUMN IF NOT EXISTS headnote TEXT,
        ADD COLUMN IF NOT EXISTS ratio_decidendi TEXT,
        ADD COLUMN IF NOT EXISTS statutes_cited TEXT[],
        ADD COLUMN IF NOT EXISTS provisions_cited TEXT[],
        ADD COLUMN IF NOT EXISTS fts_headnote tsvector;
    """
    ok, _ = execute_query(token, ref, sql_cols, "Step 1: Ensure Structured Columns & fts_headnote Exist")
    if not ok:
        sys.exit(1)

    # Step 2: Trigger function for fts_headnote
    sql_trg = """
    CREATE OR REPLACE FUNCTION update_full_judgments_fts() 
    RETURNS trigger AS $$
    BEGIN
        NEW.fts_headnote := 
            setweight(to_tsvector('english', coalesce(NEW.neutral_citation, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(NEW.case_title, '')), 'B') ||
            setweight(to_tsvector('english', substring(coalesce(NEW.headnote, '') from 1 for 100000)), 'C');
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_full_judgments_fts ON public.full_judgments;
    CREATE TRIGGER trg_full_judgments_fts
        BEFORE INSERT OR UPDATE OF neutral_citation, case_title, headnote
        ON public.full_judgments
        FOR EACH ROW
        EXECUTE FUNCTION update_full_judgments_fts();
    """
    ok, _ = execute_query(token, ref, sql_trg, "Step 2: Install FTS Auto-Update Trigger")
    if not ok:
        sys.exit(1)

    # Step 3: Performance B-Tree & GIN Indexes
    sql_idx1 = "CREATE INDEX IF NOT EXISTS idx_full_judgments_domain ON public.full_judgments(domain);"
    execute_query(token, ref, sql_idx1, "Step 3a: Create Domain B-Tree Index")

    sql_idx2 = "CREATE INDEX IF NOT EXISTS idx_full_judgments_subdomain ON public.full_judgments(subdomain);"
    execute_query(token, ref, sql_idx2, "Step 3b: Create Subdomain B-Tree Index")

    sql_idx3 = "CREATE INDEX IF NOT EXISTS idx_full_judgments_statutes_cited ON public.full_judgments USING GIN(statutes_cited);"
    execute_query(token, ref, sql_idx3, "Step 3c: Create Statutes Cited GIN Index")

    sql_idx4 = "CREATE INDEX IF NOT EXISTS idx_full_judgments_fts_headnote ON public.full_judgments USING GIN(fts_headnote);"
    execute_query(token, ref, sql_idx4, "Step 4: Create FTS Headnote GIN Index")

    # Step 5: Stored Procedure search_judgments_structured
    sql_proc = """
    CREATE OR REPLACE FUNCTION search_judgments_structured(
        p_query_terms TEXT,
        p_domain VARCHAR(50) DEFAULT NULL,
        p_statute TEXT DEFAULT NULL,
        p_limit INT DEFAULT 20
    )
    RETURNS TABLE (
        id UUID,
        case_id TEXT,
        case_title TEXT,
        neutral_citation TEXT,
        court_name TEXT,
        decision_date TEXT,
        domain VARCHAR,
        subdomain VARCHAR,
        headnote TEXT,
        ratio_decidendi TEXT,
        statutes_cited TEXT[],
        rank REAL
    )
    LANGUAGE sql
    STABLE
    AS $$
        SELECT 
            fj.id,
            fj.case_id,
            fj.case_title,
            fj.neutral_citation,
            fj.court_name,
            fj.decision_date,
            fj.domain,
            fj.subdomain,
            fj.headnote,
            fj.ratio_decidendi,
            fj.statutes_cited,
            ts_rank_cd(fj.fts_headnote, plainto_tsquery('english', p_query_terms)) AS rank
        FROM public.full_judgments fj
        WHERE 
            (p_domain IS NULL OR fj.domain = p_domain)
            AND (p_statute IS NULL OR fj.statutes_cited @> ARRAY[p_statute])
            AND (
                p_query_terms IS NULL 
                OR p_query_terms = '' 
                OR fj.fts_headnote @@ plainto_tsquery('english', p_query_terms)
            )
        ORDER BY rank DESC, fj.decision_date DESC NULLS LAST
        LIMIT p_limit;
    $$;
    """
    execute_query(token, ref, sql_proc, "Step 5: Create Stored Procedure search_judgments_structured")

    # Step 6: Post-Migration Schema Verification
    sql_verify_cols = """
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'public' 
      AND table_name = 'full_judgments'
      AND column_name IN ('domain', 'subdomain', 'headnote', 'ratio_decidendi', 'statutes_cited', 'provisions_cited', 'fts_headnote')
    ORDER BY column_name;
    """
    ok, cols = execute_query(token, ref, sql_verify_cols, "Step 6a: Verify Columns in information_schema")
    if ok:
        print("\n=== Post-Migration Column Verification ===")
        for c in cols:
            print(f"  + {c.get('column_name')}: {c.get('data_type')}")
        if len(cols) == 7:
            print("--> ALL 7/7 STRUCTURED COLUMNS SUCCESSFULLY VERIFIED!")

    sql_verify_proc = """
    SELECT routine_name, routine_type 
    FROM information_schema.routines 
    WHERE routine_schema = 'public' AND routine_name = 'search_judgments_structured';
    """
    ok, procs = execute_query(token, ref, sql_verify_proc, "Step 6b: Verify search_judgments_structured Routine")
    if ok and procs:
        print(f"--> STORED PROCEDURE search_judgments_structured IS LIVE AND VERIFIED!")

    print("\nMigration completed successfully!")

if __name__ == "__main__":
    main()
