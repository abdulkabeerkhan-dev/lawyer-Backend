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

-- Approved Batch 1 Cases:
INSERT INTO public.precedent_status (
    case_id, citation, case_name, status,
    superseded_by_case_id, superseding_citation, superseding_case_name,
    doctrinal_note, source_citation
) VALUES (
    '2004_CLC_1186',
    '2004 CLC 1186',
    '2004 CLC 1186',
    'overruled',
    '2012_CLC_1386',
    '2012 CLC 1386',
    'Liaquat Hussain v. Zil-e-Huma',
    'The prior decision reported at 2004 CLC 1186 was overruled in its entirety regarding the treatment of dower amount as consideration for Khula and the disposition of ornaments in the plaintiff''s possession.',
    '2012 CLC 1386'
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
    '1986_PLD_PESH_81',
    'PLD 1986 Pesh. 81',
    'PLD 1986 Pesh. 81',
    'overruled',
    '1997_CLC_1825',
    '1997 CLC 1825',
    'Zardar Khan v. Muhammad Ayaz Khan',
    'The prior Peshawar High Court decision was overruled regarding the applicability of Article 152 of the Limitation Act, 1908 to decrees passed under Order XVII, Rule 3 of the CPC.',
    '1997 CLC 1825'
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
    '1998_PLD_SC_AJK_26',
    'PLD 1998 SC (AJ&K) 26',
    'Fazal Karim v. Azad Government',
    'overruled',
    '2019_MLD_846',
    '2019 MLD 846',
    'Muhammad Hanif v. Muhammad Sadiq',
    'The prior judgment was overruled to establish that a designated court has jurisdiction to determine whether a reference filed before it is valid and can dismiss it on grounds of limitation, and that the Collector cannot waive objections regarding statutory limitation periods.',
    '2019 MLD 846'
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
    '1983_AIR_PUNJ_HAR_393',
    'AIR 1983 Punj. and Har. 393',
    'AIR 1983 Punj. and Har. 393',
    'overruled',
    '1989_MLD_3220',
    '1989 MLD 3220',
    'Gurpreet Singh v. Chatur Bhuj Goel',
    'The precedent''s interpretation that the requirement of ''in writing and signed by the parties'' under O. XXIII, R. 3 applies only to compromises effected outside Court was overruled.',
    '1989 MLD 3220'
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
    '1936_AIR_RANG_17',
    'AIR 1936 Rang. 17',
    'AIR 1936 Rang. 17',
    'overruled',
    '1989_MLD_3225',
    '1989 MLD 3225',
    'M. Veerappa v. Evelyn Sequeira',
    'The precedent was overruled regarding the interpretation of words in Section 306 of the Succession Act and the application of the maxim ''Actio personalis cum moritur persona'' in suits for damages involving defamation and assault.',
    '1989 MLD 3225'
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
    '1975_PLC_554',
    '1975 PLC 554',
    'Livestock Farm Labour Union, Okara v. Registrar, Trade Unions, Multan Region, Multan',
    'overruled',
    '1976_PLC_931',
    '1976 PLC 931',
    'Tubewell Employees'' Union, SCARP IV v. Secretary, Irrigation, Punjab',
    'The case was expressly held to be no longer good law, indicating it has been superseded and should not be relied upon as binding precedent.',
    '1976 PLC 931'
) ON CONFLICT (case_id) DO UPDATE SET
    status = EXCLUDED.status,
    superseded_by_case_id = EXCLUDED.superseded_by_case_id,
    superseding_citation = EXCLUDED.superseding_citation,
    superseding_case_name = EXCLUDED.superseding_case_name,
    doctrinal_note = EXCLUDED.doctrinal_note,
    source_citation = EXCLUDED.source_citation;
