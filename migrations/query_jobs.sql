-- ============================================================================
-- Migration: migrations/query_jobs.sql
-- Purpose: In-flight and persistent query job store for Pakistani legal research backend.
--          Stores execution stage, status, timings, and sanitized metadata.
--          Strictly excludes raw query text and client auth tokens.
-- Target: public.query_jobs
-- Note: Do NOT execute automatically; run manually via Supabase SQL Editor if desired.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.query_jobs (
    job_id TEXT PRIMARY KEY,
    user_id TEXT,
    stage TEXT NOT NULL DEFAULT 'queued',
    status TEXT NOT NULL DEFAULT 'running',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Fast lookup indexes for status polling, user scoping, and TTL cleanups
CREATE INDEX IF NOT EXISTS idx_query_jobs_user_status 
    ON public.query_jobs (user_id, status);

CREATE INDEX IF NOT EXISTS idx_query_jobs_updated_at 
    ON public.query_jobs (updated_at DESC);
