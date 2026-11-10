import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.legal_issue_extractor import (
    extract_legal_issues_from_fact_pattern,
    extract_named_statute_canonical_ids
)
from core.evidence_pipeline import execute_stage4_evidence_pack
from legal_ai.synthesis.memorandum_generator import sanitize_precedent_card


def test_fix1_named_statute_canonical_ids_direct_lookup():
    """Fix 1: Queries naming PECA 2016, FIO 2001, or Section X of Y Act must directly produce canonical IDs."""
    peca_cids = extract_named_statute_canonical_ids("What is the offence under PECA 2016?")
    assert "PECA_2016_SEC_20" in peca_cids
    assert "PECA_2016_SEC_21" in peca_cids
    assert "PECA_2016_SEC_10" in peca_cids

    fio_cids = extract_named_statute_canonical_ids("Bank filed suit under FIO 2001 for recovery.")
    assert "FIO_2001_SEC_9" in fio_cids
    assert "FIO_2001_SEC_22" in fio_cids

    sec_cids = extract_named_statute_canonical_ids("Accused filed pre-arrest bail under Section 498 CrPC.")
    assert "CRPC_1898_SEC_498" in sec_cids

    sec_peca = extract_named_statute_canonical_ids("Notice alleging violation of Section 20 of PECA 2016.")
    assert "PECA_2016_SEC_20" in sec_peca


def test_fix2_peca_deterministic_branch():
    """Fix 2: PECA keywords trigger deterministic branch with the 4 sub-issues and controlling provisions."""
    query = (
        "Client received FIA notice alleging cybercrime and online defamation on social media, "
        "seeking pre-arrest bail under Section 498 CrPC."
    )
    decomp = extract_legal_issues_from_fact_pattern(query)

    assert decomp.primary_domain == "cybercrime"
    assert len(decomp.issues) == 4

    # Collect all controlling provisions across sub-issues
    all_controlling = []
    for issue in decomp.issues:
        all_controlling.extend(issue.controlling_provisions)

    assert "PECA_2016_SEC_20" in all_controlling
    assert "PECA_2016_SEC_21" in all_controlling
    assert "PECA_2016_SEC_10" in all_controlling
    assert "CRPC_1898_SEC_498" in all_controlling
    assert "FIA_1974_SEC_5" in all_controlling


def test_fix3_headnote_badge_downgrade():
    """Fix 3: When a precedent has content_level='headnote_only' or text_type='headnote', verified badge is downgraded."""
    card_headnote = {
        "case_id": "test_case_hd_01",
        "citation": "2022 SCMR 9999",
        "title": "State v. Accused",
        "court": "Supreme Court of Pakistan",
        "year": 2022,
        "content_level": "headnote_only",
        "text_type": "headnote",
        "ratio_decidendi": "High Court correctly granted bail under Section 498 CrPC in cybercrime matter.",
        "full_text": "High Court correctly granted bail under Section 498 CrPC in cybercrime matter.",
        "preview": "High Court correctly granted bail under Section 498 CrPC in cybercrime matter.",
    }

    sanitized = sanitize_precedent_card(card_headnote)
    assert sanitized["is_verified"] is False
    assert sanitized["verified"] is False
    assert sanitized["verified_source"] is False
    assert sanitized["verification_status"] == "HEADNOTE_ONLY - not verified"
    assert sanitized["source_badge"] == "Headnote Only - Not Verified"
    assert sanitized["is_headnote_only"] is True


def test_evidence_pipeline_populates_named_statutes_directly():
    """Fix 1: execute_stage4_evidence_pack admits named statute provisions directly."""
    pack, clean_cases = execute_stage4_evidence_pack(
        query_text="Advise on bail under PECA 2016 and Section 498 CrPC after FIA notice.",
        precedent_cards=[],
        verified_statutory_provisions=[]
    )
    # Check that PECA, CRPC, and FIA provisions were admitted into statute records
    admitted_act_names = [v.get("act_name", "") for v in pack.statutes.values()]
    assert any("PECA" in str(a) for a in admitted_act_names)
    assert any("CRPC" in str(a) for a in admitted_act_names)
    assert any("FIA" in str(a) for a in admitted_act_names)
