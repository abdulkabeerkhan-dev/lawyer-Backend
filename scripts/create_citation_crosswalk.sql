-- SQL DDL Script for PostgreSQL / Supabase Citation Crosswalk Table
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
