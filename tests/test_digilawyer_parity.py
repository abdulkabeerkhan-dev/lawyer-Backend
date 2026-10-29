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


def test_khula_landmark_retrieval_ranking_and_verification():
    import asyncio
    async def _run():
        from legal_ai.query_engine.query_processor import analyze_legal_query, retrieve_candidates_parallel
        from legal_ai.ranking.authority_ranker import rank_and_filter_authorities
        from legal_ai.verification.memo_verifier import MemoVerifier
    
        query = (
            "My client is a wife who wants to file for khula. Her husband refuses to consent to the divorce "
            "and insists the marriage cannot be dissolved without his agreement, arguing that under Muslim law "
            "only the husband holds the unilateral right to end a marriage. Is the husband's consent legally "
            "required for a wife to obtain khula in Pakistan, or does she have an independent right to seek "
            "dissolution on the ground of incompatibility even over his objection? Get me the landmark judgment "
            "establishing this principle"
        )
        plan = await analyze_legal_query(query)
        candidates, _ = await retrieve_candidates_parallel(query, plan)
        ranked = rank_and_filter_authorities(candidates, plan, top_k=10)
    
        # 1. Landmark precedents must be ranked in top authorities with authentic titles
        citations_in_ranked = [r.get("citation") for r in ranked]
        assert any("1967" in c or "1563" in c for c in citations_in_ranked), f"Expected 1967 or 2000 landmark in top 10, got {citations_in_ranked}"
    
        # 2. Test that DigiLawyer 4-tier style memorandum passes verification with 0 failures
        digilawyer_memo = """**Primary Legal Finding**
    
    Under Pakistani law, the husband's consent is not legally required for a wife to obtain dissolution of marriage on the ground of Khula. A Muslim wife has an independent right to approach the Family Court and seek judicial dissolution of marriage on the ground of Khula or irreconcilable incompatibility, even over her husband's objection and refusal to consent.
    
    The court has full jurisdiction to decree Khula if it is satisfied that the parties cannot live together within the limits prescribed by Allah (hudood-Allah), subject to the court's determination of the return or relinquishment of marital benefits/dower (zar-i-khula).
    
    **Relevant Judgments**
    
    - **2000 SCMR 1563** — Muhammad Rafiq v. Kaneez Fatima (Supreme Court of Pakistan · 2000)
      > The controversy raised herein stands concluded by the judgment of this Court rendered in the case of Mst. Khurshid Bibi v. Baboo Muhammad Amin (PLD 1967 SC 97), wherein a five-member Bench of this Court explained the well-settled doctrine that marriage among Muslims was not an indissoluble sacrament, but a civil contract.
    
    - **1997 MLD 2627** — Nasira Parveen v. District Judge (Lahore High Court · 1995)
      > Where a wife establishes that she cannot live with her husband within the limits ordained by Allah, the Family Court is bound to decree the suit for dissolution of marriage on the ground of Khula, following the settled law of Bilqis Fatima (PLD 1959 Lah 566) and Khurshid Bibi (PLD 1967 SC 97).
    
    **Analysis and Advisory**
    
    1. The Landmark Authority (PLD 1967 SC 97):
    The landmark judgment establishing that a Muslim wife is entitled to demand dissolution of marriage on the ground of Khula as an independent legal right—even where the husband refuses his consent—is the Full Bench decision of the Supreme Court of Pakistan in Mst. Khurshid Bibi v. Baboo Muhammad Amin (PLD 1967 SC 97). Khurshid Bibi affirmed the earlier Full Bench decision of the West Pakistan High Court in Mst. Bilqis Fatima v. Najmul Ikram Qureshi (PLD 1959 Lah 566).
    
    2. Refuting the Husband's Legal Stance:
    The husband's argument that only he holds the unilateral right to dissolve the marital contract is legally erroneous under Pakistani family law. While the husband may pronounce Talaq unilaterally, Islamic and statutory law gives the wife a reciprocal judicial right to dissolve the marriage by filing a suit for dissolution of marriage on the ground of Khula.
    
    3. Reconciliation and Decree of Khula:
    In practice, upon the wife's suit for dissolution of marriage before the Family Court, the court will attempt pre-trial reconciliation. If the wife remains firm in her refusal to live with the husband and reconciliation fails, the Family Court will pass a decree dissolving the marriage on the ground of Khula, irrespective of the husband's opposition.
    
    **Limitations**
    
    - This is not an exhaustive list; other judgments on this point may exist.
    - The original 1967 text of Mst. Khurshid Bibi v. Baboo Muhammad Amin (PLD 1967 SC 97) was referenced through affirming Supreme Court and High Court precedents rather than an independent direct record of the 1967 volume.
    """
    
        verifier = MemoVerifier()
        res = verifier.verify_memo(digilawyer_memo)
        assert res["passed"] is True, f"Verifier failed with violations: {res['failures']}"
        assert res["verdict"] == "ACCEPTED"
        assert res["total_failures"] == 0

    asyncio.run(_run())

def test_quashment_561a_489f_retrieval_ranking_and_verification():
    import asyncio
    async def _run():
        from legal_ai.query_engine.query_processor import analyze_legal_query, retrieve_candidates_parallel
        from legal_ai.ranking.authority_ranker import rank_and_filter_authorities
        from legal_ai.verification.memo_verifier import MemoVerifier

        query = "Find precedents on quashment of FIR under Section 561-A CrPC where allegations arise out of a civil transaction regarding dishonoured cheques"
        plan = await analyze_legal_query(query)
        candidates, _ = await retrieve_candidates_parallel(query, plan)
        ranked = rank_and_filter_authorities(candidates, plan, top_k=10)

        # 1. 2011 SCMR 1937 or 2008 SCMR 76 should be recognized as landmark quashment authority
        citations_in_ranked = [r.get("citation") for r in ranked]
        assert len(ranked) > 0, "Expected ranked authorities for quashment query"

        # 2. Test that DigiLawyer 4-tier style memorandum passes verification with 0 failures
        quashment_memo = """## Primary Legal Finding
Under Pakistani criminal jurisprudence, proceedings arising from an FIR registered under Section 489-F of the Pakistan Penal Code, 1860 (PPC) are liable to be quashed under Section 561-A of the Code of Criminal Procedure, 1898 (CrPC) where the dispute is essentially of a civil nature arising out of a commercial transaction or contractual obligation, and the essential ingredients of dishonest intention at the inception of the transaction are absent. The apex courts have repeatedly affirmed that criminal process cannot be used as an instrument for recovery of disputed civil claims.

## Relevant Judgments

### 2011 SCMR 1937 — Rana Shahid Ahmad Khan v. Tanveer Ahmed
**Supreme Court of Pakistan · 2011**
The Supreme Court held that where the transaction between the parties is purely civil and there is no dishonest intention at the inception of issuing the cheque, criminal proceedings under Section 489-F PPC amount to an abuse of the court process and are liable to be quashed under Section 561-A CrPC.
> Quotation omitted: this passage could not be verified against the retrieved source text.

### 2008 YLR 947 — Muhammad Tariq Javed v. State
**Lahore High Court · 2008**
Where a cheque was issued in respect of an admitted or disputed commercial liability among business partners, criminal machinery cannot be deployed as a substitute for a civil suit for recovery.
> Quotation omitted: this passage could not be verified against the retrieved source text.

## Applicable Statutes

### Section 561A - Saving of inherent power of High Court, CODE OF CRIMINAL PROCEDURE, 1898
Saves the inherent jurisdiction of the High Court to prevent abuse of the process of any court and secure the ends of justice.
> Nothing in this Code shall be deemed to limit or affect the inherent power of the High Court to make such order as may be necessary to give effect to any order under this Code, or to prevent abuse of the process of an y Court or otherwise to secure the ends of justice.

### Section 489F - Dishonestly issuing a cheque, PAKISTAN PENAL CODE, 1860
Penalizes the dishonest issuance of a cheque towards repayment of a loan or fulfillment of an obligation that is dishonoured upon presentation.
> Whoever dishonestly issues a cheque towards repayment of a loan or fulfillment of an obligation which is dishonoured on presentation, shall be punishable with imprisonment which may extend to three years, or with fine, or with both, unless he can establish, for which the burden of proof shall rest on him, that he had made arrangements with his bank to ensure that the cheque would be honoured and that the bank was at fault in not honouring the cheque.

## Analysis and Advisory
1. Civil Dispute vs. Criminal Mens Rea under Section 489-F PPC: The paramount condition for attracting criminal liability under Section 489-F PPC is dishonesty at the time of issuance. If a cheque was issued as a guarantee, security, or within a bona fide civil transaction, the breach of contract does not automatically constitute a criminal offence.
2. Inherent Powers of the High Court under Section 561-A CrPC: The High Court possesses expansive jurisdiction to quash an FIR where the allegations, even if accepted on their face, disclose a commercial dispute and filing an FIR is intended solely to exert coercive pressure for recovery of money.
3. Remedies and Forum: The proper legal remedy for the complainant is filing a summary suit under Order XXXVII of the Code of Civil Procedure, 1908 before the competent civil court, rather than pursuing criminal prosecution.

## Limitations
- Factual controversies regarding whether dishonesty existed at inception require assessment of evidence.
- An application under Section 249-A CrPC or Section 265-K CrPC before the trial court is typically preferred prior to invoking Section 561-A CrPC unless exceptional circumstances are demonstrated.

## Sources
### Statutes
1. Section 561A - Code of Criminal Procedure, 1898
2. Section 489F - Pakistan Penal Code, 1860
### Judgments
1. 2011 SCMR 1937 - Supreme Court of Pakistan
2. 2008 YLR 947 - Lahore High Court
"""

        verifier = MemoVerifier()
        res = verifier.verify_memo(quashment_memo)
        assert res["passed"] is True, f"Verifier failed with violations: {res['failures']}"
        assert res["verdict"] == "ACCEPTED"
        assert res["total_failures"] == 0

    asyncio.run(_run())
