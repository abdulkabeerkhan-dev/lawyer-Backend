-- ============================================================================
-- ⚠️ STAGING-FIRST ENFORCEMENT NOTICE (ORDER 1.13 - ITEM 9)
-- DO NOT EXECUTE DIRECTLY ON PRODUCTION DATABASE!
-- This migration MUST be validated in a dedicated staging database instance
-- with allocated maintenance_work_mem and execution monitoring prior to production.
-- ============================================================================
-- ============================================================================
-- Migration: 20261025_add_fts_index_full_judgments.sql
-- Purpose: Add PostgreSQL GIN Full-Text Search (FTS) index on public.full_judgments
--          (431,298 corpus entries) with safe truncation against the 1MB tsvector limit
--          and non-transactional concurrent index instructions.
-- Schema Target: public.full_judgments (columns: case_title, neutral_citation, court_name, full_text)
-- Output only: DO NOT RUN DIRECTLY ON PRODUCTION DB WITHOUT ALLOCATING MAINTENANCE_WORK_MEM.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. STATEMENT TIMEOUT & MEMORY CONFIGURATION
-- ----------------------------------------------------------------------------
-- Supabase / PostgreSQL hosted instances enforce statement_timeout limits.
-- Allocate adequate maintenance memory for GIN index construction.
SET statement_timeout = 0;
SET lock_timeout = '10s';
SET maintenance_work_mem = '512MB';

-- ----------------------------------------------------------------------------
-- 2. SCHEMA MUTATION: ADD FTS TSVECTOR COLUMN
-- ----------------------------------------------------------------------------
ALTER TABLE public.full_judgments 
    ADD COLUMN IF NOT EXISTS fts_tokens tsvector;

-- ----------------------------------------------------------------------------
-- 3. BATCHED BACKFILL PROCEDURE WITH TSVECTOR 1MB LIMIT TRUNCATION
-- ----------------------------------------------------------------------------
-- PostgreSQL tsvector has a hard 1MB (1,048,575 bytes) internal limit.
-- Landmark apex judgments exceeding ~100 pages will crash to_tsvector with:
--   "ERROR: string is too long for tsvector"
-- We safely truncate full_text to the first 500,000 characters using `substring(coalesce(fj.full_text, '') from 1 for 500000)`.
CREATE OR REPLACE PROCEDURE backfill_full_judgments_fts_batched(batch_size INT DEFAULT 5000)
LANGUAGE plpgsql
AS $$
DECLARE
    rows_updated INT := 0;
    total_updated INT := 0;
BEGIN
    LOOP
        WITH rows_to_update AS (
            SELECT id 
            FROM public.full_judgments 
            WHERE fts_tokens IS NULL 
            LIMIT batch_size
            FOR UPDATE SKIP LOCKED
        )
        UPDATE public.full_judgments fj
        SET fts_tokens = (
            setweight(to_tsvector('english', coalesce(fj.case_title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(fj.neutral_citation, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(fj.court_name, '')), 'B') ||
            setweight(to_tsvector('english', substring(coalesce(fj.full_text, '') from 1 for 500000)), 'C')
        )
        FROM rows_to_update
        WHERE fj.id = rows_to_update.id;

        GET DIAGNOSTICS rows_updated = ROW_COUNT;
        total_updated := total_updated + rows_updated;
        
        RAISE NOTICE 'Batched FTS Backfill: Updated % rows (Total: %)', rows_updated, total_updated;
        
        COMMIT;

        IF rows_updated = 0 THEN
            EXIT;
        END IF;
    END LOOP;

    RAISE NOTICE 'Batched FTS Backfill COMPLETE. Total rows indexed: %', total_updated;
END;
$$;

-- ----------------------------------------------------------------------------
-- 4. REAL-TIME SYNCHRONIZATION TRIGGER (FOR INGESTION PIPELINE)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION full_judgments_fts_trigger_func()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.fts_tokens := (
        setweight(to_tsvector('english', coalesce(NEW.case_title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.neutral_citation, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.court_name, '')), 'B') ||
        setweight(to_tsvector('english', substring(coalesce(NEW.full_text, '') from 1 for 500000)), 'C')
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_full_judgments_fts_update ON public.full_judgments;
CREATE TRIGGER trg_full_judgments_fts_update
    BEFORE INSERT OR UPDATE OF case_title, neutral_citation, court_name, full_text
    ON public.full_judgments
    FOR EACH ROW
    EXECUTE FUNCTION full_judgments_fts_trigger_func();

-- ----------------------------------------------------------------------------
-- 5. HIGH-PERFORMANCE SEARCH RPC (FOR HYBRID RETRIEVAL INTEGRATION)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION search_judgments_fts(
    query_text TEXT,
    court_filter TEXT DEFAULT NULL,
    match_limit INT DEFAULT 30
)
RETURNS TABLE (
    id UUID,
    case_id TEXT,
    neutral_citation TEXT,
    case_title TEXT,
    court_name TEXT,
    decision_date DATE,
    rank_score REAL,
    snippet TEXT
)
LANGUAGE sql
STABLE
AS $$
    SELECT 
        fj.id,
        fj.case_id,
        fj.neutral_citation,
        fj.case_title,
        fj.court_name,
        fj.decision_date,
        ts_rank_cd(fj.fts_tokens, websearch_to_tsquery('english', query_text), 32 /* rank normalization */) AS rank_score,
        ts_headline('english', coalesce(fj.full_text, ''), websearch_to_tsquery('english', query_text), 
                    'StartSel=<mark>, StopSel=</mark>, MaxWords=50, MinWords=25') AS snippet
    FROM public.full_judgments fj
    WHERE 
        fj.fts_tokens @@ websearch_to_tsquery('english', query_text)
        AND (court_filter IS NULL OR fj.court_name ILIKE ('%' || court_filter || '%'))
    ORDER BY rank_score DESC
    LIMIT match_limit;
$$;

-- ----------------------------------------------------------------------------
-- 6. STANDALONE GIN INDEX CREATION (NON-TRANSACTIONAL)
-- ----------------------------------------------------------------------------
-- CRITICAL: `CREATE INDEX CONCURRENTLY` CANNOT be executed inside a multi-statement
-- transaction block (`BEGIN ... COMMIT`). If executing via a migration tool that wraps
-- scripts in transactions, run the DDL above first, and then execute this single
-- statement in an isolated, autocommit session:
--
--   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_full_judgments_fts_tokens 
--       ON public.full_judgments 
--       USING gin (fts_tokens);
--
-- Alternatively, if running during a planned maintenance window where table locks
-- are acceptable, the standard non-concurrent index can be executed inside a transaction:
-- OPERATIVE PRODUCTION DDL (MUST RUN OUTSIDE TRANSACTION BLOCK):
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_full_judgments_fts_tokens 
--     ON public.full_judgments 
--     USING gin (fts_tokens);
-- NOTE: PostgreSQL enforces that `CREATE INDEX CONCURRENTLY` CANNOT be executed inside a multi-statement transaction block (`BEGIN ... COMMIT`). It must be executed in an autocommit connection.
-- ----------------------------------------------------------------------------
