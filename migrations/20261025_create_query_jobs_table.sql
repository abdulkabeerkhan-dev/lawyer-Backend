-- ============================================================================
-- Migration: 20261025_create_query_jobs_table.sql
-- Purpose: Create persistent database-backed job store for in-flight queries
--          replacing ephemeral/insecure local disk JSON files.
-- Target: public.query_jobs
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
