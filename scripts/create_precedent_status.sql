-- Migration: Create Precedent Status Table for Overruling and Currency Tracking
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

-- Seed initial landmark reversal: State v. Dosso (overruled by Asma Jilani)
INSERT INTO public.precedent_status (
    case_id, citation, case_name, status, 
    superseded_by_case_id, superseding_citation, superseding_case_name, 
    doctrinal_note, source_citation
) VALUES (
    '1958_PLD_SC_533', 
    'PLD 1958 SC 533', 
    'State v. Dosso', 
    'overruled', 
    '1972_PLD_SC_139', 
    'PLD 1972 SC 139', 
    'Asma Jilani v. Government of Punjab', 
    'The doctrine of revolutionary legality validating extra-constitutional seizure of power was expressly rejected and declared bad law.',
    'PLD 1972 SC 139'
) ON CONFLICT (case_id) DO UPDATE SET
    status = EXCLUDED.status,
    superseded_by_case_id = EXCLUDED.superseded_by_case_id,
    superseding_citation = EXCLUDED.superseding_citation,
    superseding_case_name = EXCLUDED.superseding_case_name,
    doctrinal_note = EXCLUDED.doctrinal_note,
    source_citation = EXCLUDED.source_citation;

INSERT INTO public.precedent_status (
    case_id, citation, case_name, status, 
    superseded_by_case_id, superseding_citation, superseding_case_name, 
    doctrinal_note, source_citation
) VALUES (
    '1958_PLD_533', 
    'PLD 1958 SC 533', 
    'State v. Dosso', 
    'overruled', 
    '1972_PLD_SC_139', 
    'PLD 1972 SC 139', 
    'Asma Jilani v. Government of Punjab', 
    'The doctrine of revolutionary legality validating extra-constitutional seizure of power was expressly rejected and declared bad law.',
    'PLD 1972 SC 139'
) ON CONFLICT (case_id) DO UPDATE SET
    status = EXCLUDED.status,
    superseded_by_case_id = EXCLUDED.superseded_by_case_id,
    superseding_citation = EXCLUDED.superseding_citation,
    superseding_case_name = EXCLUDED.superseding_case_name,
    doctrinal_note = EXCLUDED.doctrinal_note,
    source_citation = EXCLUDED.source_citation;

