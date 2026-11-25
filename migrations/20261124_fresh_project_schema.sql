-- ============================================================================
-- Fresh Supabase project schema (2026-11-24)
-- The old project's 2 GB disk filled during the text trim, so the app moves to a
-- new project. Judgment text lives in Cloudflare R2 (texts/v1 by row id,
-- case_texts/v1 for the Turso copy); full_judgments keeps metadata and the
-- search index only, so full_text is stored as ''.
-- ============================================================================
create extension if not exists pg_trgm;

create table if not exists public.full_judgments (
    id uuid primary key default gen_random_uuid(),
    case_id text unique not null,
    case_title text,
    neutral_citation text,
    court_name text,
    bench text,
    decision_date text,
    full_text text not null default '',
    headnote text,
    ratio_decidendi text,
    holding_snippet text,
    docket_number text,
    case_type text,
    source_url text,
    domain varchar,
    subdomain varchar,
    statutes_cited text[],
    identity_status varchar,
    citation_status varchar,
    title_status varchar,
    provenance_status varchar,
    content_quality varchar,
    retrieval_status varchar,
    verification_reason text,
    verification_version varchar,
    verified_at timestamptz,
    content_hash varchar,
    canonical_court_name varchar,
    canonical_case_title text,
    fts_headnote tsvector,
    created_at timestamptz default now()
);
create index if not exists idx_full_judgments_neutral_citation on public.full_judgments (neutral_citation);
create index if not exists idx_full_judgments_canonical_case_title on public.full_judgments (canonical_case_title) where canonical_case_title is not null;
create index if not exists idx_full_judgments_gate3_composite on public.full_judgments (court_name, case_type, docket_number, decision_date);
create index if not exists idx_full_judgments_retrieval_status on public.full_judgments (retrieval_status);
create index if not exists idx_full_judgments_content_quality on public.full_judgments (content_quality);
create index if not exists idx_full_judgments_canonical_court_name on public.full_judgments (canonical_court_name);
create index if not exists idx_full_judgments_case_title_trgm on public.full_judgments using gin (case_title gin_trgm_ops);
create index if not exists idx_full_judgments_statutes_cited on public.full_judgments using gin (statutes_cited);
create index if not exists idx_full_judgments_fts_headnote on public.full_judgments using gin (fts_headnote);

-- fts_headnote is loaded with the headnote text at import time; the trigger only
-- recomputes it when a row arrives with text (new judgments), never wiping it.
create or replace function public.update_full_judgments_fts() returns trigger language plpgsql as $$
begin
    if coalesce(new.headnote, '') <> '' or tg_op = 'INSERT' and new.fts_headnote is null then
        new.fts_headnote :=
            setweight(to_tsvector('english', coalesce(new.neutral_citation, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(new.case_title, '')), 'B') ||
            setweight(to_tsvector('english', substring(coalesce(new.headnote, '') from 1 for 100000)), 'C');
    end if;
    return new;
end $$;
drop trigger if exists trg_full_judgments_fts on public.full_judgments;
create trigger trg_full_judgments_fts before insert or update on public.full_judgments
    for each row execute function public.update_full_judgments_fts();

create or replace function public.search_judgments_structured(p_query_terms text, p_domain varchar default null,
    p_statute text default null, p_limit integer default 20)
returns table(id uuid, case_id text, case_title text, neutral_citation text, court_name text, decision_date text,
    domain varchar, subdomain varchar, headnote text, ratio_decidendi text, statutes_cited text[], rank real)
language sql stable as $$
    select fj.id, fj.case_id, fj.case_title, fj.neutral_citation, fj.court_name, fj.decision_date, fj.domain,
           fj.subdomain, fj.headnote, fj.ratio_decidendi, fj.statutes_cited,
           ts_rank_cd(fj.fts_headnote, plainto_tsquery('english', p_query_terms)) as rank
    from public.full_judgments fj
    where (p_domain is null or fj.domain = p_domain)
      and (p_statute is null or fj.statutes_cited @> array[p_statute])
      and (p_query_terms is null or p_query_terms = '' or fj.fts_headnote @@ plainto_tsquery('english', p_query_terms))
    order by rank desc, fj.decision_date desc nulls last
    limit p_limit;
$$;

-- ---------------------------------------------------------------- app tables
create table if not exists public.users (
    id text primary key,                 -- Clerk user id
    email text unique,
    full_name text,
    role text default 'user',
    status text default 'active',
    input_tokens bigint default 0,
    output_tokens bigint default 0,
    created_at timestamptz default now()
);

create table if not exists public.queries (
    id uuid primary key default gen_random_uuid(),
    user_id text,
    query_text text,
    answer_text text,
    citations jsonb,
    result jsonb,
    status text,
    input_tokens bigint default 0,
    output_tokens bigint default 0,
    created_at timestamptz default now()
);
create index if not exists idx_queries_user_created on public.queries (user_id, created_at desc);

create table if not exists public.query_jobs (
    job_id text primary key,
    user_id text,
    stage text not null default 'queued',
    status text not null default 'running',
    error text,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    metadata jsonb default '{}'::jsonb
);
create index if not exists idx_query_jobs_user_status on public.query_jobs (user_id, status);
create index if not exists idx_query_jobs_updated_at on public.query_jobs (updated_at desc);

create table if not exists public.access_requests (
    id uuid primary key default gen_random_uuid(),
    email text,
    full_name text,
    firm_name text,
    status text default 'pending',
    message text,
    created_at timestamptz default now()
);
create index if not exists idx_access_requests_email on public.access_requests (email);

create table if not exists public.feedback (
    id uuid primary key default gen_random_uuid(),
    query_id text,
    user_id text,
    query_text text,
    original_answer text,
    correct_answer text,
    feedback_type text,
    comment text,
    created_at timestamptz default now()
);

create table if not exists public.user_case_diary (
    id uuid primary key default gen_random_uuid(),
    user_id text,
    case_title text,
    case_number text,
    court_name text,
    hearing_date date,
    stage_of_case text,
    notes text,
    created_at timestamptz default now()
);
create index if not exists idx_user_case_diary_user_date on public.user_case_diary (user_id, hearing_date);

create table if not exists public.quarantined_judgments (
    id uuid primary key default gen_random_uuid(),
    source_url text, source_domain text, fetched_at timestamptz,
    extracted_citation text, extracted_case_title text, extracted_court_name text, extracted_date text,
    extracted_judge_names jsonb, docket_number text, case_type text, raw_text text,
    ocr_confidence double precision, text_health_score double precision, extraction_method text,
    citation_format_valid boolean, court_domain_match boolean, passes_min_confidence boolean,
    status text default 'pending_review', reviewed_by text, reviewed_at timestamptz, rejection_reason text,
    promoted_to_case_id text, composite_key text unique, created_at timestamptz default now()
);

create table if not exists public.statute_currency_checks (
    id uuid primary key default gen_random_uuid(),
    act_code text, query_text text, query_hash text, status text, duration_ms integer,
    signals_found jsonb, cache_hit boolean, reason text, checked_at timestamptz default now()
);

CREATE TABLE IF NOT EXISTS public.citation_crosswalk (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    citation TEXT UNIQUE NOT NULL,      -- e.g. "2021 SCMR 2092"
    court TEXT NOT NULL,                -- e.g. "Supreme Court of Pakistan"
    docket_number TEXT NOT NULL,        -- e.g. "Crl.P. 408-L/2021" or "408-L/2021"
    case_title TEXT,                    -- e.g. "Muhammad Nasir Shafique v. The State"
    judgment_id UUID REFERENCES public.full_judgments(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_citation_crosswalk_cit ON public.citation_crosswalk (citation);
CREATE INDEX IF NOT EXISTS idx_citation_crosswalk_docket ON public.citation_crosswalk (docket_number);
CREATE TABLE IF NOT EXISTS public.precedent_status (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id TEXT NOT NULL UNIQUE,
    citation TEXT NOT NULL,
    case_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('overruled', 'criticized_not_followed', 'distinguished', 'superseded_by_statute')),
    superseded_by_case_id TEXT,
    superseding_citation TEXT,
    superseding_case_name TEXT,
    doctrinal_note TEXT NOT NULL,
    source_citation TEXT NOT NULL,
    annotated_by TEXT DEFAULT 'manual_review',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_precedent_status_case ON public.precedent_status(case_id);
CREATE INDEX IF NOT EXISTS idx_precedent_status_citation ON public.precedent_status(citation);
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

-- The backend uses the service-role key; keep public (anon) access off.
alter table public.full_judgments enable row level security;
alter table public.users enable row level security;
alter table public.queries enable row level security;
alter table public.query_jobs enable row level security;
alter table public.access_requests enable row level security;
alter table public.feedback enable row level security;
alter table public.user_case_diary enable row level security;
alter table public.quarantined_judgments enable row level security;
alter table public.statute_currency_checks enable row level security;
alter table public.citation_crosswalk enable row level security;
alter table public.precedent_status enable row level security;
alter table public.statute_versions enable row level security;
