-- ============================================================================
-- Migration: 20261025_add_fts_index_full_judgments.sql
-- Purpose: Add non-blocking, batched PostgreSQL GIN Full-Text Search (FTS)
--          index on public.full_judgments (431,298 corpus entries).
-- Author: Section Engineering / Phase 1.7
--
-- CRITICAL SAFETY DIRECTIVE: DO NOT EXECUTE DIRECTLY VIA MIGRATION RUNNER WITHOUT
-- ALLOCATING MAINTENANCE_WORK_MEM AND MONITORING REPLICATION SLOTS.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. STATEMENT TIMEOUT & MEMORY CONFIGURATION
-- ----------------------------------------------------------------------------
-- Supabase / PostgreSQL hosted instances enforce strict statement_timeout limits
-- (typically 8 seconds for API pools or 60 seconds for administrative sessions).
-- Indexing several gigabytes of text across 431k judgments will fail with
-- "canceling statement due to statement timeout (57014)" under default settings.
SET statement_timeout = 0;
SET lock_timeout = '10s';
SET maintenance_work_mem = '512MB';

-- ----------------------------------------------------------------------------
-- 2. LOCK RISK ANALYSIS & CONCURRENCY
-- ----------------------------------------------------------------------------
-- Standard `CREATE INDEX` acquires an AccessExclusiveLock on public.full_judgments,
-- entirely locking out SELECT, INSERT, UPDATE, and DELETE operations.
-- For a 431,298 row table with large full_text bodies, this would cause an outage
-- lasting several minutes.
--
-- SOLUTION:
-- Use `CREATE INDEX CONCURRENTLY`. This acquires only a ShareUpdateExclusiveLock,
-- allowing ongoing live production traffic, client queries, and new ingestions
-- to proceed without interruption.
-- (Note: CONCURRENTLY cannot be executed inside a multi-statement transaction block).

-- ----------------------------------------------------------------------------
-- 3. SCHEMA MUTATION: ADD FTS TSVECTOR COLUMN
-- ----------------------------------------------------------------------------
-- Adding an unpopulated column is a fast metadata-only operation in Postgres 11+
-- that does not rewrite the table or take prolonged locks.
ALTER TABLE public.full_judgments 
    ADD COLUMN IF NOT EXISTS fts_tokens tsvector;

-- ----------------------------------------------------------------------------
-- 4. BATCHED BACKFILL PROCEDURE (PREVENTING TABLE BLOAT & TIMEOUTS)
-- ----------------------------------------------------------------------------
-- Updating all 431,298 rows in a single UPDATE statement causes severe transaction
-- log (WAL) bloat, memory pressure, and replication lag.
-- The procedure below processes rows in chunks of 5,000, issuing COMMIT after each chunk.

CREATE OR REPLACE PROCEDURE backfill_full_judgments_fts_batched(batch_size INT DEFAULT 5000)
LANGUAGE plpgsql
AS $$
DECLARE
    rows_updated INT := 0;
    total_updated INT := 0;
BEGIN
    LOOP
        -- Update a slice of rows where fts_tokens has not yet been computed
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
            setweight(to_tsvector('english', coalesce(fj.full_text, '')), 'C')
        )
        FROM rows_to_update
        WHERE fj.id = rows_to_update.id;

        GET DIAGNOSTICS rows_updated = ROW_COUNT;
        total_updated := total_updated + rows_updated;
        
        RAISE NOTICE 'Batched FTS Backfill: Updated % rows (Total: %)', rows_updated, total_updated;
        
        -- Commit the transaction slice to release row locks and flush WAL
        COMMIT;

        -- Exit loop when all rows have been populated
        IF rows_updated = 0 THEN
            EXIT;
        END IF;
    END LOOP;

    RAISE NOTICE 'Batched FTS Backfill COMPLETE. Total rows indexed: %', total_updated;
END;
$$;

-- ----------------------------------------------------------------------------
-- 5. NON-BLOCKING GIN INDEX CREATION
-- ----------------------------------------------------------------------------
-- Run after the batched backfill completes. GIN inverted index allows sub-50ms
-- lexical search and phrase matching across the entire 431,298 judgment dataset.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_full_judgments_fts_tokens 
    ON public.full_judgments 
    USING gin (fts_tokens);

-- ----------------------------------------------------------------------------
-- 6. REAL-TIME SYNCHRONIZATION TRIGGER (FOR INGESTION PIPELINE)
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
        setweight(to_tsvector('english', coalesce(NEW.full_text, '')), 'C')
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
-- 7. HIGH-PERFORMANCE SEARCH RPC (FOR HYBRID RETRIEVAL INTEGRATION)
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

-- ============================================================================
-- ARCHITECTURAL COVERAGE COMPARISON:
-- 1. Current State: In-memory BM25 in `core/hybrid_search.py` is loaded from
--    `data/bm25_corpus.json` (40,575 chunks, representing ~9.4% of judgments)
--    due to memory limits of lightweight container environments (512MB RAM).
-- 2. Target State: PostgreSQL GIN FTS index (`idx_full_judgments_fts_tokens`)
--    covers 100% of the 431,298 judgments in Supabase without loading text chunks
--    into application RAM. Hybrid search merges Pinecone dense vectors (top-30)
--    with Postgres lexical FTS results (top-30) via Reciprocal Rank Fusion (RRF),
--    increasing corpus lexical recall by >10x.
-- ============================================================================
