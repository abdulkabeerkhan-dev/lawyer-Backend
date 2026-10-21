"""
tests/test_content_assertions.py

Verification test verifying that content assertions properly catch:
1. Section 406 penalty mismatch (3 years vs 7 years in PPC bare act) and ungrounded statute quotations.
2. Promissory note memo erroneously naming Article 181.
3. Ungrounded 'Court held' statements not traceable to retrieved headnotes.
"""

import re
import pytest
from tests.test_e2e_real_queries import (
    check_statute_quotes_grounded,
    check_court_held_traceable_to_precedents,
)


def test_assertion_fails_on_flawed_406_penalty_and_ungrounded_quote():
    # Flawed Round 2 memo text where 406 penalty is claimed as only 3 years and quotes ungrounded text
    flawed_memo = (
        "## Relevant Provisions\n"
        "> Statutory text unavailable in retrieved sources.\n"
        "Section 406 PPC provides: \"Whoever commits criminal breach of trust shall be punished with imprisonment up to seven years.\"\n"
        "The punishment under Section 406 is three years only."
    )
    injected_context = ""  # No bare-act text injected

    # 1. Test fails because quoted statute text was not in the injector
    with pytest.raises(AssertionError) as exc_info:
        check_statute_quotes_grounded(flawed_memo, injected_context)
    assert "not grounded in injected bare-act text" in str(exc_info.value)

    # 2. Test fails on 3-year penalty without seven years
    memo_with_3yr_only = "Section 406 PPC prescribes a maximum punishment of three years imprisonment."
    with pytest.raises(AssertionError):
        assert any(p in memo_with_3yr_only.lower() for p in ["seven years", "7 years"])


def test_assertion_fails_on_promissory_note_citing_article_181():
    # Flawed Round 2 memo citing Article 181 for a promissory note
    flawed_memo = (
        "## Relevant Provisions\n"
        "- Article 181 Limitation Act, 1908: Prescribes a three-year limitation period for promissory notes."
    )
    with pytest.raises(AssertionError):
        assert "article 181" not in flawed_memo.lower()


def test_assertion_fails_on_ungrounded_court_held_attribution():
    # Flawed memo asserting a holding not in the retrieved headnote
    flawed_memo = (
        "### Hakeem v. State (2026 SCMR 792)\n"
        "- **Court held**: Criminal breach of trust requires proof of dishonest intention at inception and criminal process cannot be used for recovery."
    )
    # Actual retrieved headnote (which only concerns s.497 prohibitory clause and further inquiry)
    mock_retrieved_cards = [
        {
            "citation": "2026 SCMR 792",
            "holding": "Offences under sections 406, 420, 489-F fall within the non-prohibitory clause of Section 497 Cr.P.C. where grant of bail is a rule and refusal an exception.",
            "preview": "Bail granted as a case of further inquiry was made out."
        }
    ]
    with pytest.raises(AssertionError) as exc_info:
        check_court_held_traceable_to_precedents(flawed_memo, mock_retrieved_cards)
    assert "insufficient grounding in retrieved precedents" in str(exc_info.value)
