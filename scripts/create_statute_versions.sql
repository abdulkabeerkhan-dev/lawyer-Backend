-- Schema for Supabase statute_versions table (Item 7.d)
-- Ensures version store persists across worker restarts and redeployments.

CREATE TABLE IF NOT EXISTS public.statute_versions (
    version_id TEXT PRIMARY KEY,
    canonical_id TEXT NOT NULL,
    act_code TEXT NOT NULL,
    provision_type TEXT NOT NULL DEFAULT 'section',
    primary_num TEXT NOT NULL,
    secondary_num TEXT,
    title TEXT,
    title_only TEXT,
    text TEXT,
    text_available BOOLEAN DEFAULT false,
    jurisdiction TEXT DEFAULT 'federal',
    status TEXT DEFAULT 'in_force',
    enacted_date DATE,
    assent_date DATE,
    commencement_date DATE,
    valid_from DATE,
    valid_to DATE,
    amending_instrument TEXT,
    gazette_reference TEXT,
    effective_application TEXT DEFAULT 'pending_and_prospective',
    ordinance_expiry_date DATE,
    court_challenges JSONB DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tier TEXT,
    verification_status TEXT DEFAULT 'baseline_unverified',
    fetched_at TIMESTAMPTZ,
    previous_version_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_statute_versions_canonical_id ON public.statute_versions(canonical_id);
CREATE INDEX IF NOT EXISTS idx_statute_versions_act_code ON public.statute_versions(act_code);
CREATE INDEX IF NOT EXISTS idx_statute_versions_created_at ON public.statute_versions(created_at DESC);
