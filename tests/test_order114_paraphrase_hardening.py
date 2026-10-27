"""
tests/test_order114_paraphrase_hardening.py

ORDER 1.14 - ITEM 2 TESTS:
1. 'shall not grant leave' -> 'shall grant leave' -> BLOCKED (negation flipped)
2. 'may' -> 'shall' -> BLOCKED (modal shifted)
3. 'six months' kept but 'unless extended' dropped -> BLOCKED (condition dropped)
4. A clean paraphrase -> PASSES
"""

import pytest
from core.claim_first_memo import ClaimFirstVerifier, render_claim_first_memo

@pytest.fixture
def verifier():
    return ClaimFirstVerifier()

def test_paraphrase_negation_flipped_blocked(verifier):
    # s.10(1) FIO: "the defendant shall not be entitled to defend the suit unless he obtains leave"
    # Flipped: "shall grant leave" / "shall be entitled to defend"
    claim = {
        "text": "The Banking Court shall grant the defendant leave to defend the suit without conditions.",
        "type": "paraphrase",
        "support": "FIO_2001_SEC_10(1)"
    }
    res = verifier.verify_claim_memo([claim])
    assert res["passed"] is False, "Paraphrase flipping negative 'shall not' to affirmative 'shall' must be BLOCKED"
    assert any(f["category"] in ("NEGATION_FLIPPED", "PARAPHRASE_INTRODUCES_TERMS", "CONDITION_DROPPED") for f in res["failures"])

def test_paraphrase_modal_shifted_blocked(verifier):
    # s.22(1) FIO: "...may, within thirty days... prefer an appeal to the High Court"
    claim = {
        "text": "Any person aggrieved by any final order passed by a Banking Court shall prefer an appeal to the High Court within thirty days.",
        "type": "paraphrase",
        "support": "FIO_2001_SEC_22(1)"
    }
    res = verifier.verify_claim_memo([claim])
    assert res["passed"] is False, "Paraphrase shifting permissive 'may' to mandatory 'shall' must be BLOCKED"
    assert any(f["category"] == "MODAL_MISMATCH" for f in res["failures"])

def test_paraphrase_condition_dropped_blocked(verifier):
    # Order XXXIX Rule 2(3) CPC: "detained in prison for a term not exceeding six months, unless in the meantime the Court directs his release"
    claim = {
        "text": "The Court may order the person guilty of disobedience to be detained in prison for six months.",
        "type": "paraphrase",
        "support": "CPC_1908_ORD_XXXIX_R_2"
    }
    # Keeps 'six months' but drops 'unless in the meantime the Court directs his release'
    res = verifier.verify_claim_memo([claim])
    assert res["passed"] is False, "Paraphrase dropping condition 'unless' must be BLOCKED"
    assert any(f["category"] == "CONDITION_DROPPED" for f in res["failures"])

def test_paraphrase_clean_passes(verifier):
    # s.22(4) FIO: "(4) An appeal under sub-section (1) shall be heard by a bench of not less that two Judges of the High Court and, in case the appeal is admitted, it shall be decided within 90 days from the date of admission."
    claim = {
        "text": "An appeal under sub-section (1) shall be heard by a bench of two Judges of the High Court and decided within 90 days from the date of admission.",
        "type": "paraphrase",
        "support": "FIO_2001_SEC_22(4)"
    }
    res = verifier.verify_claim_memo([claim])
    assert res["passed"] is True, f"Clean paraphrase of s.22(4) must PASS, got failures: {res['failures']}"
    assert res["total_failures"] == 0

def test_paraphrase_rendering_beside_source(verifier):
    claim = {
        "text": "An appeal under sub-section (1) shall be heard by a bench of two Judges of the High Court and decided within 90 days from the date of admission.",
        "type": "paraphrase",
        "support": "FIO_2001_SEC_22(4)"
    }
    rendered = render_claim_first_memo([claim])
    assert "- **[paraphrase of s.22(4)]**" in rendered
    assert "*Official Store Text (s.22(4)):*" in rendered
