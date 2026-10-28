import pytest
import re
from core.legal_query_planner import create_deterministic_fallback_plan
from core.statute_currency import detect_statutory_provisions_in_query
from legal_ai.verification.memo_verifier import MemoVerifier, omit_unverified_blockquotes
from legal_ai.synthesis.memorandum_generator import filter_and_cap_authorities, sanitize_partner_markdown_presentation
from core.unified_statute_store import get_unified_statute_store


def test_q1_cpc_review_planning_and_currency():
    q = "Which section of the CPC lets the court review its own decision?"
    
    # 1. Currency detector
    detected = detect_statutory_provisions_in_query(q)
    cids = [d[0] for d in detected]
    assert "CPC_1908_SEC_114" in cids, f"Expected CPC_1908_SEC_114 in {cids}"
    assert "CPC_1908_ORD_XLVII_R_1" in cids, f"Expected CPC_1908_ORD_XLVII_R_1 in {cids}"
    
    # 2. Planner fallback
    plan = create_deterministic_fallback_plan(q)
    assert any("114" in p for p in plan.provisions), f"Section 114 missing from plan: {plan.provisions}"
    assert any("xlvii" in p.lower() or "47" in p for p in plan.provisions), f"Order XLVII missing: {plan.provisions}"
    assert "Code of Civil Procedure, 1908" in plan.governing_statutes


def test_q1_cpc_section_114_store_hygiene():
    store = get_unified_statute_store()
    rec = store.get_provision("CPC_1908", "114")
    assert rec is not None, "CPC Section 114 missing from store"
    txt = rec.get("text", "")
    assert "decree" in txt, "OCR typo 'degree' still present in Section 114"
    assert "thinks fit" in txt, "Grammar typo 'think fit' still present in Section 114"
    assert not txt.startswith("1["), "Footnote bracket '1[' not stripped from Section 114"


def test_q1_cpc_precedent_filtering():
    q = "Which section of the CPC lets the court review its own decision?"
    plan = create_deterministic_fallback_plan(q)
    
    candidates = [
        {
            "citation": "PLD 2025 SC 720",
            "case_title": "District Education Officer vs Sonia Begum",
            "court": "Supreme Court of Pakistan",
            "preview": "Article 188 of Constitution review power of Supreme Court",
            "sections": ["188"],
            "authority_score": 5.0
        },
        {
            "citation": "2006 YLR 2084",
            "case_title": "Allah Wasaya vs Member",
            "court": "Board of Revenue",
            "preview": "West Pakistan Board of Revenue Act review jurisdiction",
            "sections": ["1", "9"],
            "authority_score": 4.0
        },
        {
            "citation": "2007 YLR 1392",
            "case_title": "Mistri Mehraj Din vs Sheikh Muhammad Akbar",
            "court": "Lahore High Court",
            "preview": "powers of review under Section 114 and Order XLVII Rule 1 CPC cannot serve as rehearing or appeal in disguise",
            "sections": ["114", "XLVII"],
            "authority_score": 4.5
        },
        {
            "citation": "2008 YLR 846",
            "case_title": "Ghulam Dastgir vs Barkat Ali",
            "court": "Lahore High Court",
            "preview": "scope of review under Section 114 CPC against final decree",
            "sections": ["114", "12"],
            "authority_score": 4.2
        }
    ]
    
    filtered = filter_and_cap_authorities(candidates, query_plan=plan, query_text=q)
    cits = [c["citation"] for c in filtered]
    
    # Board of Revenue must be filtered out
    assert "2006 YLR 2084" not in cits, "Board of Revenue review case should be filtered out"
    # CPC cases must be present
    assert "2007 YLR 1392" in cits, "Direct CPC review precedent 2007 YLR 1392 must be retained"
    assert "2008 YLR 846" in cits, "Direct CPC review precedent 2008 YLR 846 must be retained"


def test_q2_companies_act_planning_and_store():
    q = (
        "A petition was filed before the Lahore High Court Company Bench by a shareholder holding 15% shareholding "
        "under Section 286 of the Companies Act, 2017, seeking relief against alleged mismanagement, exclusion from management, "
        "and financial oppression by the majority directors. The petitioner simultaneously prayed for an interim order freezing "
        "the company's operational bank accounts and appointing a provisional manager to run the day-to-day manufacturing business. "
        "The company is financially solvent, running at a profit, and meeting its commercial obligations. Under Pakistani company "
        "jurisprudence, can the Company Bench grant sweeping interim management or freeze operational bank accounts of a solvent "
        "company at the threshold of a Section 286 petition, or must interim relief be strictly tailored to preserve the status "
        "quo without crippling commercial operations? Cite the controlling apex precedents"
    )
    plan = create_deterministic_fallback_plan(q)
    assert any("286" in p for p in plan.provisions), f"Section 286 missing from {plan.provisions}"
    assert any("288" in p for p in plan.provisions), f"Section 288 missing from {plan.provisions}"
    assert "Companies Act, 2017" in plan.governing_statutes
    
    store = get_unified_statute_store()
    rec286 = store.get_provision("COMPANIES_2017", "286")
    assert rec286 is not None, "Companies Act Section 286 missing from store"
    rec288 = store.get_provision("COMPANIES_2017", "288")
    assert rec288 is not None, "Companies Act Section 288 missing from store"
    assert "just and equitable" in rec288.get("text", "").lower()


def test_graceful_quote_omission_parity():
    memo_with_unmatched = (
        "## Primary Legal Finding\n"
        "Under Section 114 CPC, a civil court possesses review jurisdiction.\n\n"
        "## Applicable Statutes\n"
        "### Section 114 - Review, THE CODE OF CIVIL PROCEDURE, 1908\n"
        "Section 114 confers substantive review jurisdiction upon a civil court:\n"
        "> An unverified fabricated statutory quote that differs from gazette prints.\n\n"
        "## Analysis and Advisory\n"
        "1. Substantive power vs procedure.\n"
    )
    
    v = MemoVerifier()
    res1 = v.verify_memo(memo_with_unmatched)
    assert not res1["passed"], "Should fail before omission"
    
    sanitized = omit_unverified_blockquotes(memo_with_unmatched, res1["failures"])
    assert "> Quotation omitted: this passage could not be verified against the retrieved source text." in sanitized
    
    res2 = v.verify_memo(sanitized)
    assert res2["passed"], f"Expected clean pass after surgical quote omission, got failures: {res2['failures']}"


def test_partner_markdown_presentation_sanitizes_typography():
    ugly = (
        "> **Precedent Verification Notice**: Direct narrative analysis was withheld.\n\n"
        "# Verified Statutory Provisions on Record\n"
        "# Section 205, Companies Act, 2017\n"
        "#### Section 60, Companies Act, 2017\n"
        "### 1. ### Executive Summary\n"
        "The court held under Section 114 #CPC that #decree cannot be reviewed.\n"
        "# Verified Judicial Authorities on Record\n"
        "### Not in verified store\n"
        "- **Section 999**: no text available\n"
    )
    clean = sanitize_partner_markdown_presentation(ugly)
    # Zero top warning banners
    assert not clean.startswith("> **Precedent Verification Notice**")
    # Zero stray hashes on words
    assert "#decree" not in clean
    assert "#CPC" not in clean
    assert "### 1. ###" not in clean
    # Section headings converted to clean bold
    assert "**Section 205, Companies Act, 2017**" in clean
    assert "**Section 60, Companies Act, 2017**" in clean
    assert "**Verified Statutory Provisions on Record**" in clean
    assert "**Verified Judicial Authorities on Record**" in clean
    # Markdown H3 section preserved
    assert "### Not in verified store" in clean
    # No stray # attached to words or lines
    assert not re.search(r'#+\w+', clean), f"Found stray hashtag in: {clean}"

def test_multiturn_conversational_context_resolution():
    from main import QueryRequest, ChatMessagePayload
    from pydantic import BaseModel

    req = QueryRequest(
        query_text="Explain how to present this to the court?",
        messages=[
            ChatMessagePayload(role="user", content="An accused was arrested under Section 9(c) of the Control of Narcotic Substances Act 1997 for alleged recovery of 2 kilograms of Charas. At trial, the prosecution failed to examine the Moharrir to prove safe custody..."),
            ChatMessagePayload(role="assistant", content="## Primary Legal Finding\nUnder Section 9(c) CNSA 1997, failure to prove safe custody entitles the accused to an acquittal."),
            ChatMessagePayload(role="user", content="Explain how to present this to the court?")
        ]
    )

    # Simulate query processor context resolution
    raw_input_text = str(getattr(req, "query_text", "") or "").strip()
    effective_user_query = raw_input_text
    messages_list = getattr(req, "messages", None) or []
    prior_context_parts = []
    for m in messages_list:
        m_role = (m.get("role") if isinstance(m, dict) else getattr(m, "role", "user")) or "user"
        m_content = (m.get("content") if isinstance(m, dict) else getattr(m, "content", "")) or ""
        m_content = m_content.strip()
        if not m_content:
            continue
        if m_role == "user" and m_content != raw_input_text:
            prior_context_parts.append(f"Prior User Query: {m_content}")
        elif m_role == "assistant":
            m_match = re.search(r'## Primary Legal Finding\s*\n+([^\n]+(?:\n[^\n]+)?)', m_content)
            if m_match:
                prior_context_parts.append(f"Prior Finding: {m_match.group(1).strip()[:300]}")

    lower_q = effective_user_query.lower()
    follow_up_cues = ["this", "that", "it", "how to present", "how to argue", "court"]
    is_follow_up = len(effective_user_query.split()) < 25 or any(cue in lower_q for cue in follow_up_cues)
    if is_follow_up and prior_context_parts:
        effective_user_query = f"{' | '.join(prior_context_parts[-2:])}\n\nFollow-up Request: {effective_user_query}"

    assert "Section 9(c)" in effective_user_query
    assert "Explain how to present this to the court?" in effective_user_query
    assert "Prior Finding:" in effective_user_query
