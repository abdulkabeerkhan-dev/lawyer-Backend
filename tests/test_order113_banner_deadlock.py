"""
tests/test_order113_banner_deadlock.py

ORDER 1.13 - ITEM 1 / ORDER 1.14 - ITEM 3: BANNER DEADLOCK & SYSTEM ASSEMBLER TESTS
Verifies that:
1. Disputed-provision check fails when system banner is skipped.
2. The model never writes banners (model-written banners are stripped and flagged under Rule b).
3. The system assembler attaches system warning banner and verifies final output under system authority.
"""

import pytest
from legal_ai.verification.memo_verifier import (
    verify_memorandum_text,
    assemble_and_verify_memorandum,
    attach_system_disputed_banner,
    LABEL_MODEL_BANNER_DETECTED
)

SAMPLE_FIO_S22_MEMO = (
    "## LEGAL RESEARCH MEMORANDUM\n\n"
    "### Appeal Procedure under Section 22 of the Financial Institutions Ordinance, 2001\n\n"
    "Under Section 22 of the Financial Institutions (Recovery of Finances) Ordinance, 2001, "
    "any person aggrieved by a final order of a Banking Court may file an appeal to the High Court within thirty days.\n\n"
    "Section 22 of the Financial Institutions (Recovery of Finances) Ordinance, 2001 provides:\n\n"
    "> 22. Appeal. (1) Subject to sub-section (2), any person aggrieved by any judgment, decree, sentence, or final order passed by a Banking Court may, within thirty days of such judgment, decree, sentence or final order prefer an appeal to the High Court.\n"
    "> (2) The appellant shall give notice of the filing of the appeal in accordance with the provisions of Order XLIII Rule 3 of the Code of Civil Procedure (Act V of 1908) to the respondent who may appear before the Banking Court to contest admission of the appeal on the date fixed for hearing.\n\n"
    "According to Section 22 of the Financial Institutions (Recovery of Finances) Ordinance, 2001, notice under Order XLIII Rule 3 is mandatory.\n"
)

def test_memo_fails_when_system_banner_is_skipped():
    """When the system banner attachment is skipped, the memo must fail under Rule (d) with DISPUTED_TEXT_UNNOTICED."""
    res = verify_memorandum_text(SAMPLE_FIO_S22_MEMO)
    assert not res["passed"], "Unbannered memo citing disputed provision must not pass"
    disputed_failures = [f for f in res["failures"] if f.get("category") == "DISPUTED_TEXT_UNNOTICED"]
    assert len(disputed_failures) > 0, "Expected DISPUTED_TEXT_UNNOTICED failure when banner step is skipped"

def test_memo_passes_with_system_banner():
    """When the system assembler attaches the system banner, it passes verification."""
    res = assemble_and_verify_memorandum(SAMPLE_FIO_S22_MEMO, [{"provision": "FIO_2001_SEC_22"}])
    assert res["passed"], f"Final assembled memo with system banner must pass, but got failures: {res['failures']}"
    assert len(res["failures"]) == 0

def test_model_injected_banner_is_blocked():
    """If the model attempts to write its own `> [!` banner, it is stripped and blocked under Rule (b)."""
    fake_model_banner = (
        "> [!WARNING] DISPUTED TEXT\n"
        "> Model generated warning banner.\n\n"
        + SAMPLE_FIO_S22_MEMO
    )
    res = verify_memorandum_text(fake_model_banner)
    assert not res["passed"]
    b_fails = [f for f in res["failures"] if f.get("rule") == "(b)"]
    assert len(b_fails) > 0, "Model-written banner must trigger Rule (b) failure"
    assert b_fails[0]["category"] == "MODEL_INJECTED_BANNER"
