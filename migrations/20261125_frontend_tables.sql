-- ============================================================================
-- Tables used by the frontend's server functions (section-frontend/src/lib/*.functions.ts).
-- They lived in a Lovable Cloud project the frontend had no service key for, so the
-- server used a mock client: every save was silently dropped and every read was empty.
-- Users are Clerk user ids (text). Access is server-side only (service role); RLS on.
-- ============================================================================
create table if not exists public.saved_precedents (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    card_key text not null,
    citation text not null default '',
    case_title text not null default '',
    matter text not null default '',
    note text not null default '',
    tags text[] not null default '{}',
    card jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (user_id, card_key)
);
create index if not exists idx_saved_precedents_user on public.saved_precedents (user_id, updated_at desc);

create table if not exists public.saved_searches (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    name text not null default '',
    filters jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
create index if not exists idx_saved_searches_user on public.saved_searches (user_id, created_at desc);

create table if not exists public.user_memory (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    category text not null default 'general',
    content text not null default '',
    source text not null default 'user',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_user_memory_user on public.user_memory (user_id, updated_at desc);

create table if not exists public.activity_log (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    thread_id text not null default '',
    category text not null default '',
    mode text not null default '',
    question text not null default '',
    response jsonb,
    created_at timestamptz not null default now()
);
create index if not exists idx_activity_log_user on public.activity_log (user_id, created_at desc);

create table if not exists public.citation_feedback (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    issue_type text not null default '',
    citation text,
    case_id text,
    case_title text,
    court text,
    note text,
    query_text text,
    created_at timestamptz not null default now()
);
create index if not exists idx_citation_feedback_created on public.citation_feedback (created_at desc);

alter table public.saved_precedents enable row level security;
alter table public.saved_searches enable row level security;
alter table public.user_memory enable row level security;
alter table public.activity_log enable row level security;
alter table public.citation_feedback enable row level security;
