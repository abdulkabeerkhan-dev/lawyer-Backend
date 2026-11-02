-- ============================================================================
-- Migration: 20261102_add_structured_legal_segments.sql
-- Purpose: Schema Enrichment & Structural Segmentation for Pakistani Court Judgments
-- Target Table: public.full_judgments
-- 
-- Adds structured segmentation columns:
-- 1. domain (civil, criminal, family, banking_commercial, constitutional, tax_corporate)
-- 2. subdomain (partition, benami, bail, murder, khula, recovery_of_finances, etc.)
-- 3. headnote (Editorial digest, statutory anchors, legal issue)
-- 4. ratio_decidendi (Judicial holding, binding tests, operative reasoning)
-- 5. statutes_cited (Canonical statute titles as array)
-- 6. provisions_cited (Specific sections, orders, rules as array)
-- 7. fts_headnote (High-speed GIN-indexed tsvector over citation, title, and headnote)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. STATEMENT & MEMORY CONFIGURATION
-- ----------------------------------------------------------------------------
SET statement_timeout = 0;
SET lock_timeout = '10s';

-- ----------------------------------------------------------------------------
-- 2. SCHEMA MUTATION: ADD STRUCTURED LEGAL SEGMENTATION COLUMNS
-- ----------------------------------------------------------------------------
ALTER TABLE public.full_judgments 
    ADD COLUMN IF NOT EXISTS domain VARCHAR(50),
    ADD COLUMN IF NOT EXISTS subdomain VARCHAR(50),
    ADD COLUMN IF NOT EXISTS headnote TEXT,
    ADD COLUMN IF NOT EXISTS ratio_decidendi TEXT,
    ADD COLUMN IF NOT EXISTS statutes_cited TEXT[],
    ADD COLUMN IF NOT EXISTS provisions_cited TEXT[];

-- ----------------------------------------------------------------------------
-- 3. COMPUTED FULL-TEXT SEARCH COLUMN OVER HEADNOTES
-- ----------------------------------------------------------------------------
-- Generates weighted tsvector:
--   Weight A: neutral_citation & case_id (exact citation hits)
--   Weight B: case_title (party names & forum keywords)
--   Weight C: headnote (substantive legal holding & statutory anchors)
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'full_judgments' 
          AND column_name = 'fts_headnote'
    ) THEN
        ALTER TABLE public.full_judgments 
            ADD COLUMN fts_headnote tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector('english', coalesce(neutral_citation, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(case_title, '')), 'B') ||
                setweight(to_tsvector('english', substring(coalesce(headnote, '') from 1 for 100000)), 'C')
            ) STORED;
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 4. PERFORMANCE INDEXES
-- ----------------------------------------------------------------------------
-- B-Tree index for domain-level partition and filtering
CREATE INDEX IF NOT EXISTS idx_full_judgments_domain 
    ON public.full_judgments(domain);

-- B-Tree index for subdomain-level routing
CREATE INDEX IF NOT EXISTS idx_full_judgments_subdomain 
    ON public.full_judgments(subdomain);

-- GIN index for rapid array containment search (@> array['Partition Act, 1893'])
CREATE INDEX IF NOT EXISTS idx_full_judgments_statutes_cited 
    ON public.full_judgments USING GIN(statutes_cited);

-- GIN index for sub-10ms full-text search against headnotes
CREATE INDEX IF NOT EXISTS idx_full_judgments_fts_headnote 
    ON public.full_judgments USING GIN(fts_headnote);

-- ----------------------------------------------------------------------------
-- 5. DOMAIN-AWARE HIGH SPEED SEARCH STORED PROCEDURE
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION search_judgments_structured(
    p_query_terms TEXT,
    p_domain VARCHAR(50) DEFAULT NULL,
    p_statute TEXT DEFAULT NULL,
    p_limit INT DEFAULT 20
)
RETURNS TABLE (
    id BIGINT,
    case_id VARCHAR,
    case_title TEXT,
    neutral_citation VARCHAR,
    court_name TEXT,
    decision_date VARCHAR,
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
