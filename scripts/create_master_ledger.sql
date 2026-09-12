-- PostgreSQL / Supabase DDL for Master Judgment Ledger Table
CREATE TABLE IF NOT EXISTS public.judgments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_id TEXT UNIQUE NOT NULL,       -- Format: {COURT}_{TYPE}_{NUMBER}_{YEAR}, e.g. 'SC_CP_408L_2021'
    reported_citation TEXT,                  -- e.g. '2021 SCMR 2092'
    case_title TEXT NOT NULL,                -- e.g. 'Muhammad Nasir Shafique v. The State'
    court TEXT NOT NULL,                     -- e.g. 'Supreme Court of Pakistan'
    docket_number TEXT NOT NULL,             -- e.g. 'Criminal Petition No. 408-L of 2021'
    decision_date DATE,                      -- e.g. '2021-10-19'
    pdf_url TEXT,                            -- e.g. 'https://web-production-53d0.up.railway.app/judgment-pdf/SC_CP_408L_2021'
    raw_text TEXT,                           -- Full raw text of judgment
    is_reported BOOLEAN DEFAULT FALSE,       -- TRUE if reported_citation is present
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Performance indices for deterministic lookups
CREATE INDEX IF NOT EXISTS idx_judgments_canonical_id ON public.judgments (canonical_id);
CREATE INDEX IF NOT EXISTS idx_judgments_reported_cit ON public.judgments (reported_citation);
CREATE INDEX IF NOT EXISTS idx_judgments_docket ON public.judgments (docket_number);
CREATE INDEX IF NOT EXISTS idx_judgments_court ON public.judgments (court);
