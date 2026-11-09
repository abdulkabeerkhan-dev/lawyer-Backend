"""
tests/test_golden_repaired_statutes.py

Phase 2 Step 1 Golden Test Suite for CrPC 1898, CPC 1908, and PPC 1860.
Validates 10 core litigation provisions per statute (30 provisions total) against:
1. Existence in UnifiedStatuteStore and JSON files.
2. Mandatory verbatim legal anchor text present.
3. Zero running headers or page markers (Page X of Y).
4. Zero editorial footnote leakage (Subs. by, Ins. by, etc.).
5. Zero fused footnote digit artifacts (e.g. 3[, 4*).
6. 100% clean audit pass under scripts/audit_statute_corpus_phase1.py rules.
"""

import os
import sys
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.unified_statute_store import get_unified_statute_store
from scripts.audit_statute_corpus_phase1 import audit_record

store = get_unified_statute_store()
store.load()


# ==============================================================================
# CrPC 1898 Golden Tests (10 provisions)
# ==============================================================================
CRPC_GOLDEN_PROVISIONS = [
    ("CRPC_1898_SEC_1", ["Code of Criminal Procedure, 1898", "extends to the whole of Pakistan"]),
    ("CRPC_1898_SEC_4", ["Definitions", "cognizable", "bailable offence"]),
    ("CRPC_1898_SEC_54", ["arrest without warrant", "cognizable offence", "police"]),
    ("CRPC_1898_SEC_61", ["twenty-four hours", "Magistrate", "custody"]),
    ("CRPC_1898_SEC_154", ["Information in cognizable cases", "officer in charge"]),
    ("CRPC_1898_SEC_161", ["Examination of witnesses by police", "investigation", "questions"]),
    ("CRPC_1898_SEC_164", ["record statements", "Magistrate"]),
    ("CRPC_1898_SEC_173", ["Report of police", "investigation", "Magistrate"]),
    ("CRPC_1898_SEC_497", ["non-bailable offence", "reasonable grounds", "death", "imprisonment for life"]),
    ("CRPC_1898_SEC_498", ["Power to direct admission to bail", "High Court", "Court of Session"])
]

@pytest.mark.parametrize("cid, required_anchors", CRPC_GOLDEN_PROVISIONS)
def test_crpc_golden_provisions(cid, required_anchors):
    rec = store.get_by_canonical_id(cid)
    assert rec is not None, f"Provision {cid} missing from UnifiedStatuteStore"
    text = (rec.get("text") or rec.get("verbatim_text") or "").strip()
    assert len(text) > 40, f"Provision {cid} text too short ({len(text)} chars)"
    text_norm = " ".join(text.split()).lower()
    
    # Check mandatory legal phrasing
    for anchor in required_anchors:
        assert anchor.lower() in text_norm, f"Provision {cid} missing mandatory anchor: '{anchor}'"

    # Zero corruption checks
    issues = audit_record(rec, "CRPC_1898")
    assert len(issues) == 0, f"Provision {cid} failed audit with issues: {issues}"


# ==============================================================================
# CPC 1908 Golden Tests (10 provisions)
# ==============================================================================
CPC_GOLDEN_PROVISIONS = [
    ("CPC_1908_SEC_1", ["Code of Civil Procedure", "whole of Pakistan"]),
    ("CPC_1908_SEC_2", ["Definitions", "decree", "order"]),
    ("CPC_1908_SEC_9", ["civil suits", "cognizance"]),
    ("CPC_1908_SEC_10", ["Stay of suit", "directly and substantially in issue"]),
    ("CPC_1908_SEC_11", ["Res judicata", "former suit", "heard and finally decided"]),
    ("CPC_1908_SEC_12", ["Bar to further suit", "fraud", "misrepresentation", "jurisdiction"]),
    ("CPC_1908_SEC_115", ["Revision", "High Court", "subordinate", "jurisdiction"]),
    ("CPC_1908_ORD_VII_R_11", ["Rejection of plaint", "cause of action", "barred by any law"]),
    ("CPC_1908_ORD_XXXVII_R_1", ["Application of Order", "High Court", "District Court"]),
    ("CPC_1908_ORD_XXXIX_R_1", ["temporary injunction", "property in dispute"])
]

@pytest.mark.parametrize("cid, required_anchors", CPC_GOLDEN_PROVISIONS)
def test_cpc_golden_provisions(cid, required_anchors):
    rec = store.get_by_canonical_id(cid)
    assert rec is not None, f"Provision {cid} missing from UnifiedStatuteStore"
    text = (rec.get("text") or rec.get("verbatim_text") or "").strip()
    assert len(text) > 40, f"Provision {cid} text too short ({len(text)} chars)"
    text_norm = " ".join(text.split()).lower()

    for anchor in required_anchors:
        assert anchor.lower() in text_norm, f"Provision {cid} missing mandatory anchor: '{anchor}'"

    issues = audit_record(rec, "CPC_1908")
    assert len(issues) == 0, f"Provision {cid} failed audit with issues: {issues}"


# ==============================================================================
# PPC 1860 Golden Tests (10 provisions)
# ==============================================================================
PPC_GOLDEN_PROVISIONS = [
    ("PPC_1860_SEC_1", ["Pakistan Penal Code", "throughout Pakistan"]),
    ("PPC_1860_SEC_302", ["qatl-i-amd", "qisas", "ta'zir"]),
    ("PPC_1860_SEC_378", ["Theft", "moveable property", "dishonest"]),
    ("PPC_1860_SEC_379", ["Punishment for theft", "imprisonment", "three years"]),
    ("PPC_1860_SEC_390", ["Robbery", "theft", "extortion"]),
    ("PPC_1860_SEC_405", ["Criminal breach of trust", "entrusted with property", "dishonestly misappropriates"]),
    ("PPC_1860_SEC_406", ["Punishment for criminal breach of trust", "seven years", "fine"]),
    ("PPC_1860_SEC_415", ["Cheating", "deceiving"]),
    ("PPC_1860_SEC_420", ["Cheating and dishonestly inducing delivery of property", "valuable security", "seven years"]),
    ("PPC_1860_SEC_489F", ["dishonestly issues a cheque", "repayment of a loan", "fulfillment of an obligation", "dishonoured"])
]

@pytest.mark.parametrize("cid, required_anchors", PPC_GOLDEN_PROVISIONS)
def test_ppc_golden_provisions(cid, required_anchors):
    rec = store.get_by_canonical_id(cid)
    assert rec is not None, f"Provision {cid} missing from UnifiedStatuteStore"
    text = (rec.get("text") or rec.get("verbatim_text") or "").strip()
    assert len(text) > 40, f"Provision {cid} text too short ({len(text)} chars)"
    text_norm = " ".join(text.split()).lower()

    for anchor in required_anchors:
        assert anchor.lower() in text_norm, f"Provision {cid} missing mandatory anchor: '{anchor}'"

    issues = audit_record(rec, "PPC_1860")
    assert len(issues) == 0, f"Provision {cid} failed audit with issues: {issues}"


if __name__ == "__main__":
    print("Running 30 Golden Tests across CrPC, CPC, and PPC...")
    all_passed = True
    for cat, items in [("CrPC 1898", CRPC_GOLDEN_PROVISIONS), ("CPC 1908", CPC_GOLDEN_PROVISIONS), ("PPC 1860", PPC_GOLDEN_PROVISIONS)]:
        print(f"\n--- {cat} ---")
        for cid, anchors in items:
            rec = store.get_by_canonical_id(cid)
            if not rec:
                print(f"[FAIL] {cid}: missing from store!")
                all_passed = False
                continue
            text = (rec.get("text") or rec.get("verbatim_text") or "").strip()
            text_norm = " ".join(text.split()).lower()
            missing_anchors = [a for a in anchors if a.lower() not in text_norm]
            act_code = cid.split("_")[0] + "_" + cid.split("_")[1]
            issues = audit_record(rec, act_code)
            if missing_anchors or issues:
                print(f"[FAIL] {cid}: missing={missing_anchors} issues={issues}")
                all_passed = False
            else:
                print(f"[PASS] {cid} ({len(text)} chars, 0 issues)")

    if all_passed:
        print("\nALL 30 GOLDEN TESTS PASSED!")
    else:
        sys.exit(1)
