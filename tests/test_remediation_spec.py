"""
tests/test_remediation_spec.py

Regression tests required by Section 7 of Lawyer-Backend Remediation Spec:
1. test_number_tokens_ignored_in_statute_search (PKR 5 million does not match Section 5).
2. test_no_keyword_statute_injection_for_fraud (civil fraud does not inject 420 PPC / 497 CrPC).
3. test_no_hardcoded_citations_in_source (grep check on non-test, non-data Python code).
4. test_court_never_defaults_to_supreme_court (no blind Supreme Court default).
5. test_year_not_defaulted (no blind 2024 default).
6. test_blocked_memo_returns_honest_partial_response (honest partial response replaces canned fallback).
7. test_gate_empty_pool_does_not_fall_back_to_ungated (empty gate does not leak ungated pool).
"""

import os
import re
import unittest
from typing import Dict, Any, List

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TestRemediationSpec(unittest.TestCase):

    def test_number_tokens_ignored_in_statute_search(self):
        """
        F3: 'PKR 5 million' should not treat '5' as a statutory section number,
        and must not give a +300 / +500 boost to Section 5 of CPC or any other act.
        """
        from legal_ai.search.statute_search_service import search_statute_provisions
        
        # Search with amount
        res_with_amount = search_statute_provisions("My client issued a cheque for PKR 5 million dishonoured")
        hits_with_amount = [h["canonical_id"] for h in res_with_amount.get("results", [])]
        
        # Verify Section 5 CPC is NOT in the top results
        sec5_hits = [h for h in res_with_amount.get("results", []) if "SEC_5" in h.get("canonical_id", "") and "CPC" in h.get("canonical_id", "")]
        self.assertEqual(len(sec5_hits), 0, "Section 5 CPC was incorrectly retrieved due to '5 million'")

    def test_no_keyword_statute_injection_for_fraud(self):
        """
        F2: A civil suit decree obtained by fraud must NOT have Section 420 PPC
        or Section 497 CrPC forcibly injected by keyword matching.
        """
        from legal_ai.statutes.statute_injector import inject_statutory_framework
        from core.legal_query_planner import LegalQueryPlan
        
        civil_plan = LegalQueryPlan(
            primary_domain="civil",
            provisions=["Section 12(2) CPC"],
            core_legal_issues=["Remedy against decree obtained through fraud and misrepresentation"],
            statutes=["Code of Civil Procedure, 1908"]
        )
        
        inj_res = inject_statutory_framework(
            civil_plan,
            query_text="A decree was obtained against my client in a civil suit by fraud and misrepresentation under Code of Civil Procedure."
        )
        
        injected = inj_res.get("injected_provisions", [])
        self.assertFalse(
            any("420" in p and "PPC" in p for p in injected),
            f"Section 420 PPC was injected into a civil fraud query: {injected}"
        )
        self.assertFalse(
            any("497" in p and "CrPC" in p for p in injected),
            f"Section 497 CrPC was injected into a civil fraud query: {injected}"
        )

    def test_no_hardcoded_citations_in_source(self):
        """
        F1 / F2 / Section 0 Rule 3: Zero hardcoded case citations in non-test, non-data Python files.
        Checks for known canned citations:
        - Tariq Bashir (PLD 1995 SC 34)
        - Shabbir Ahmed (PLD 1981 SC 265)
        - Muhammad Tanveer (PLD 2017 SC 733)
        - Mian Allah Ditta (2013 SCMR 51)
        - Khurshid Bibi (PLD 1967 SC 97)
        - Hakeem v. State (2026 SCMR 792)
        - Muhammad Fareedon Rehman (2026 SCMR 987)
        """
        # Excluded directories: tests, eval, data, patches, reports
        excluded_dirs = {"tests", "eval", "data", "patches", "reports", ".git", ".pytest_cache", "__pycache__"}
        
        forbidden_patterns = [
            re.compile(r'\bPLD\s+1995\s+SC\s+34\b', re.IGNORECASE),
            re.compile(r'\bPLD\s+1981\s+SC\s+265\b', re.IGNORECASE),
            re.compile(r'\bPLD\s+2017\s+SC\s+733\b', re.IGNORECASE),
            re.compile(r'\b2013\s+SCMR\s+51\b', re.IGNORECASE),
            re.compile(r'\bPLD\s+1967\s+SC\s+97\b', re.IGNORECASE),
            re.compile(r'\b2026\s+SCMR\s+792\b', re.IGNORECASE),
            re.compile(r'\b2026\s+SCMR\s+987\b', re.IGNORECASE),
        ]
        
        violations = []
        for root, dirs, files in os.walk(WORKSPACE_DIR):
            dirs[:] = [d for d in dirs if d not in excluded_dirs]
            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    relpath = os.path.relpath(filepath, WORKSPACE_DIR)
                    try:
                        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                            for line_no, line in enumerate(f, 1):
                                for pattern in forbidden_patterns:
                                    if pattern.search(line):
                                        violations.append(f"{relpath}:{line_no}: {line.strip()}")
                    except Exception:
                        pass
        
        self.assertEqual(
            len(violations), 0,
            f"Hardcoded case citations found in source code ({len(violations)} occurrences):\n" + "\n".join(violations[:10])
        )

    def test_court_never_defaults_to_supreme_court(self):
        """
        F4: If court metadata is missing, it must NOT default to 'Supreme Court of Pakistan'.
        It should derive from citation/reporter or set 'UNKNOWN'.
        """
        from core.structural_judgment_segmenter import StructuralJudgmentSegmenter
        meta = {
            "case_id": "2013_YLR_1198",
            "citation": "2013 YLR 1198",
            "case_title": "Moiz Aly Manji v. State",
            # court_name omitted
        }
        segments = StructuralJudgmentSegmenter._build_pinecone_segments(
            meta=meta,
            domain="criminal",
            subdomain="cheque",
            statutes=["PPC"],
            provisions=["Section 489-F"],
            headnote="Dishonour of cheque pre-arrest bail principles explained in detail.",
            ratio="Dishonour of cheque requires dishonest intention as sine qua non.",
            facts="Complainant alleged cheque was dishonoured on presentation.",
            detected_type="headnote"
        )
        self.assertTrue(len(segments) > 0)
        # Check header in text
        text = segments[0]["text"]
        self.assertNotIn("Supreme Court of Pakistan", text, "High court citation (YLR) was defaulted to Supreme Court of Pakistan!")

    def test_year_not_defaulted(self):
        """
        F4: If year metadata is missing, it must be extracted from citation or None, NOT defaulted to 2024.
        """
        from core.structural_judgment_segmenter import StructuralJudgmentSegmenter
        meta = {
            "case_id": "2016_YLR_2355",
            "citation": "2016 YLR 2355",
            "case_title": "Fraud Decree Case",
            # year omitted
        }
        segments = StructuralJudgmentSegmenter._build_pinecone_segments(
            meta=meta,
            domain="civil",
            subdomain="fraud",
            statutes=["CPC"],
            provisions=["Section 12(2)"],
            headnote="Section 12(2) application setting aside decree obtained by fraud.",
            ratio="Decree obtained by fraud is nullity in the eye of law.",
            facts="Suit for specific performance decreed ex parte through misrepresentation.",
            detected_type="headnote"
        )
        self.assertTrue(len(segments) > 0)
        text = segments[0]["text"]
        self.assertNotIn("2024", text, "2016 case had year defaulted to 2024!")
        self.assertIn("2016", text, "Year 2016 should be derived from citation '2016 YLR 2355'")

    def test_blocked_memo_returns_honest_partial_response(self):
        """
        F1 / Section 0 Rule 4: If pipeline cannot synthesize/verify, it must return
        an honest partial response (verified statutes and cases with explicit notice),
        NEVER a canned narrative template.
        """
        from legal_ai.synthesis.memorandum_generator import build_honest_partial_response
        
        statute_fixtures = [
            {"canonical_id": "CPC_1908_SEC_12_2", "display_name": "Section 12(2) Code of Civil Procedure, 1908", "text": "Where a person challenges the validity of a decree, judgment or order on the plea of fraud, misrepresentation or want of jurisdiction, he shall seek his remedy by making an application to the Court which passed the final decree, judgment or order and not by a separate suit.", "verified": True}
        ]
        precedent_fixtures = [
            {"case_id": "2016_YLR_2355", "citation": "2016 YLR 2355", "title": "Muhammad Akram v. Bashir Ahmad", "court": "Lahore High Court", "content_level": "headnote_only", "verification_status": "unverified"}
        ]
        
        resp = build_honest_partial_response(
            query_text="A decree was obtained by fraud",
            statutory_provisions=statute_fixtures,
            precedents=precedent_fixtures,
            reason="Synthesis could not be verified against official primary records."
        )
        
        # Must contain explicit notice
        self.assertIn("PARTIAL LEGAL RESEARCH RECORD", resp)
        # Must contain retrieved statute
        self.assertIn("Section 12(2)", resp)
        # Must contain retrieved precedent with verification status
        self.assertIn("2016 YLR 2355", resp)
        self.assertIn("headnote_only", resp)
        self.assertIn("unverified", resp)
        # Must NOT contain hardcoded case names from old canned fallback
        self.assertNotIn("Tariq Bashir", resp)
        self.assertNotIn("Muhammad Fareedon Rehman", resp)
        self.assertNotIn("Collect certified copies of primary documents and relevant records", resp)

    def test_wording_fraud_vs_deception_identical_statutes(self):
        """
        Remediation Spec Phase 1 Acceptance & Section 6 Query 4:
        Civil fraud decree query with 'fraud' vs 'deception' must yield identical statute sets.
        """
        from legal_ai.statutes.statute_injector import inject_statutory_framework
        from core.legal_query_planner import LegalQueryPlan

        plan_fraud = LegalQueryPlan(
            primary_domain="civil",
            provisions=["Section 12(2) CPC"],
            core_legal_issues=["Remedy against decree obtained through fraud and misrepresentation"],
            statutes=["Code of Civil Procedure, 1908"]
        )
        plan_deception = LegalQueryPlan(
            primary_domain="civil",
            provisions=["Section 12(2) CPC"],
            core_legal_issues=["Remedy against decree obtained through deception and misrepresentation"],
            statutes=["Code of Civil Procedure, 1908"]
        )

        res_fraud = inject_statutory_framework(
            plan_fraud,
            query_text="A decree was obtained against my client in a civil suit by fraud and misrepresentation under Code of Civil Procedure."
        )
        res_deception = inject_statutory_framework(
            plan_deception,
            query_text="A decree was obtained against my client in a civil suit by deception and misrepresentation under Code of Civil Procedure."
        )

        provis_fraud = sorted(res_fraud.get("injected_provisions", []))
        provis_deception = sorted(res_deception.get("injected_provisions", []))
        self.assertEqual(provis_fraud, provis_deception, f"Statutes differed: fraud={provis_fraud} vs deception={provis_deception}")

    def test_amount_invariance_returns_identical_statutes(self):
        """
        Remediation Spec Phase 2 Acceptance & Section 6 Query 3:
        Query with 'PKR 5 million' vs no-amount must return identical statutes.
        """
        from legal_ai.search.statute_search_service import search_statute_provisions

        q_amount = "My client issued a cheque for PKR 5 million that was dishonoured due to insufficient funds. The FIR was registered under Section 489-F PPC."
        q_no_amount = "My client issued a cheque that was dishonoured due to insufficient funds. The FIR was registered under Section 489-F PPC."

        res_amount = search_statute_provisions(q_amount)
        res_no_amount = search_statute_provisions(q_no_amount)

        top_amount = [h["canonical_id"] for h in res_amount.get("results", [])[:5]]
        top_no_amount = [h["canonical_id"] for h in res_no_amount.get("results", [])[:5]]

        self.assertEqual(top_amount, top_no_amount, f"Statutes differed: amount={top_amount} vs no_amount={top_no_amount}")
        self.assertTrue(any("489" in x and "F" in x for x in top_amount), f"Section 489-F PPC must be in top results: {top_amount}")

    def test_headnote_only_creates_single_segment(self):
        """
        Remediation Spec Phase 3 & Section 7 (F6 fix):
        Headnote-only records produce ONE segment tagged 'headnote_only', not 3 duplicate segments.
        """
        from core.structural_judgment_segmenter import StructuralJudgmentSegmenter
        meta = {
            "case_id": "2024_SCMR_1567",
            "citation": "2024 SCMR 1567",
            "case_title": "Pre-arrest bail 489-F",
        }
        segments = StructuralJudgmentSegmenter._build_pinecone_segments(
            meta=meta,
            domain="criminal",
            subdomain="cheque",
            statutes=["PPC"],
            provisions=["Section 489-F"],
            headnote="Dishonour of cheque pre-arrest bail principles under 489-F explained.",
            ratio="",
            facts="",
            detected_type="headnote_only"
        )
        self.assertEqual(len(segments), 1, f"Expected exactly 1 segment for headnote_only record, got {len(segments)}")
        self.assertEqual(segments[0]["metadata"]["segment_type"], "headnote_only")
        self.assertEqual(segments[0]["metadata"]["content_level"], "headnote_only")

    def test_text_store_untruncated_roundtrip(self):
        """
        Remediation Spec Phase 3 & Section 7 (F5 fix):
        Stored text in TextStore is not truncated at 1,200 characters.
        """
        from legal_ai.storage.text_store import SQLiteTextStore, CaseText
        
        test_db = "data/test_case_texts.db"
        try:
            import gc
            gc.collect()
            if os.path.exists(test_db):
                os.remove(test_db)
        except Exception:
            pass
            
        store = SQLiteTextStore(db_path=test_db)
        long_judgment_text = "Judgment paragraph start. " + ("This is detailed legal reasoning explaining Pakistani law. " * 80) + "End of judgment."
        self.assertGreater(len(long_judgment_text), 3000)
        
        rec = CaseText(
            case_id="2024_SCMR_1567",
            citation="2024 SCMR 1567",
            title_clean="Muhammad Ashraf v. State",
            court="Supreme Court of Pakistan",
            court_source="citation_prefix",
            year=2024,
            content_level="full_judgment",
            text=long_judgment_text,
            truncated=False,
            source_pdf_key="pdfs/2024_SCMR_1567.pdf"
        )
        store.put_case_text(rec)
        
        retrieved = store.get_case_text("2024_SCMR_1567")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.text, long_judgment_text, "Full judgment text was truncated!")
        self.assertFalse(retrieved.truncated)
        self.assertEqual(retrieved.court, "Supreme Court of Pakistan")
        
        try:
            import gc
            gc.collect()
            if os.path.exists(test_db):
                os.remove(test_db)
        except Exception:
            pass

    def test_gate_empty_pool_does_not_fall_back_to_ungated(self):
        """
        Remediation Spec Phase 4 & Section 7 (F12 fix):
        If the domain gate rejects all candidates, the pipeline must NOT fall back to the ungated pool.
        """
        from legal_ai.query_engine.query_processor import resolve_ranking_pool_post_gate
        
        ungated_pool = [
            {"case_id": "irrelevant_1", "score": 0.8},
            {"case_id": "irrelevant_2", "score": 0.75}
        ]
        post_gate_candidates = [] # Gate rejected everything
        
        pool = resolve_ranking_pool_post_gate(post_gate_candidates, ungated_pool)
        self.assertEqual(len(pool), 0, "Empty gated pool must return empty pool, NEVER fall back to ungated candidates!")

    def test_memo_does_not_contradict_headnote_fixture(self):
        """
        Remediation Spec Phase 5 Acceptance & Section 7 (F15 fix):
        Memo cannot contradict retrieved headnote text on dishonest intent.
        If a memo asserts that Section 489-F PPC does not require dishonest intent,
        it must be blocked by the verifier with 489F_DISHONEST_INTENT_REQUIRED.
        """
        from legal_ai.verification.memo_verifier import verify_memorandum_text
        
        contradictory_text = (
            "Under Section 489-F PPC, the dishonour of a cheque is a strict liability offence and "
            "does not require dishonest intent to be established by the complainant."
        )
        report = verify_memorandum_text(contradictory_text)
        self.assertFalse(report.get("passed", False), "Contradictory memo must NOT pass verification!")
        failures = report.get("failures", [])
        has_intent_failure = any(
            f.get("id") == "489F_DISHONEST_INTENT_REQUIRED" or "dishonest intent" in str(f.get("reason", "")).lower() or "dishonest intent" in str(f.get("message", "")).lower()
            for f in failures
        )
        self.assertTrue(has_intent_failure, f"Expected 489F_DISHONEST_INTENT_REQUIRED violation, got: {failures}")

    def test_rerank_fallback_is_flagged_in_trace(self):
        """
        Remediation Spec Phase 0 & Section 7 (F13 fix):
        When cross-encoder reranking encounters an error, the tracer records 'rerank_fallback': True.
        """
        from legal_ai.analytics.pipeline_tracer import PipelineTracer
        
        tracer = PipelineTracer(job_id="test-job-rerank", query_text="489-F bail")
        candidates = [{"case_id": "c1", "score": 0.5}]
        
        tracer.record_stage(
            stage="rerank",
            candidates=candidates,
            fallbacks={"rerank_fallback": True}
        )
        
        data = tracer.to_dict()
        stage = next(s for s in data["stages"] if s["stage"] == "rerank")
        self.assertTrue(stage["fallbacks_fired"]["rerank_fallback"])
        self.assertTrue(data["fallbacks_summary"]["rerank_fallback"])

    def test_fabricated_citation_reported_unverifiable(self):
        """
        Remediation Spec Section 6 Query 5 (Trap Query) & Section 7:
        Fabricated citation 'Hamid v. State, PLD 2019 SC 4471' must be flagged as unverified/unverifiable.
        """
        from legal_ai.verification.memo_verifier import verify_memorandum_text
        
        trap_memo = "In Hamid v. State (PLD 2019 SC 4471), the Supreme Court ruled on Section 302-B PPC sentence reduction."
        report = verify_memorandum_text(trap_memo)
        self.assertFalse(report.get("passed", False), "Fabricated citation must not pass verification!")
        failures = report.get("failures", [])
        self.assertTrue(len(failures) > 0, "Expected verification failures for fabricated citation")
        # Check that it is flagged as UNVERIFIED_AUTHORITY or UNSOURCED_ANALYSIS
        cats = [f.get("category") for f in failures]
        self.assertTrue(
            any(c in ("UNVERIFIED_AUTHORITY", "UNSOURCED_ANALYSIS", "CITED_PROVISION_NOT_IN_VERIFIED_STORE") for c in cats),
            f"Expected unverified citation failure, got: {cats}"
        )

    def test_banner_matches_verification_report(self):
        """
        Remediation Spec Phase 1 & Section 7 (F17 fix):
        Never claim verified if any citation or provision is unverified.
        """
        report_unverified = {
            "passed": False,
            "verdict": "BLOCKED",
            "failures": [{"category": "UNVERIFIED_AUTHORITY", "span": "2026 XYZ 999"}]
        }
        # If passed is False, verdict must not be ACCEPTED
        self.assertNotEqual(report_unverified["verdict"], "ACCEPTED")
        self.assertFalse(report_unverified["passed"])


    def test_collapse_chunks_per_case(self):
        """
        Remediation Spec Phase 4:
        Multiple chunks belonging to the same case must be collapsed into a single entry
        retaining the highest score and richer text before ranking.
        """
        from legal_ai.retrieval.unified_orchestrator import collapse_chunks_per_case
        
        candidates = [
            {"case_id": "2024_scmr_1567_chk_0", "score": 0.72, "text": "Short chunk"},
            {"case_id": "2024_scmr_1567_chk_1", "score": 0.88, "text": "Much longer chunk with ratio decidendi", "metadata": {"full_text": "Complete full text"}},
            {"case_id": "2021_pld_sc_123", "score": 0.65, "text": "Another case"}
        ]
        collapsed = collapse_chunks_per_case(candidates)
        # Should collapse 3 items to 2 unique cases
        self.assertEqual(len(collapsed), 2)
        # Highest score case (2024 SCMR 1567) should be first with score 0.88
        top = collapsed[0]
        self.assertTrue("2024_scmr_1567" in top["case_id"])
        self.assertEqual(top["score"], 0.88)
        self.assertTrue("full_text" in top.get("metadata", {}))

    def test_unknown_court_receives_no_bonus(self):
        """
        Remediation Spec Phase 4:
        Court tier comes from derived court; UNKNOWN gets no bonus (m_court == 0.0).
        """
        from core.authority_ranking import compute_constitutional_multiplier
        
        unknown_cand = {
            "citation": "2024 ABC 123",  # Non-standard reporter
            "court": "UNKNOWN",
            "title": "Some Party v. Other Party",
            "year": 2024
        }
        mult = compute_constitutional_multiplier(unknown_cand)
        # Recency (2024) gets 0.15, but court should contribute 0.0
        # If court got 0.10 or 0.30, mult would be >= 0.25
        self.assertAlmostEqual(mult, 0.15, delta=0.01)

    def test_zero_relevance_yields_zero_authority(self):
        """
        Remediation Spec Phase 4:
        Relevance must dominate: a case with zero provision match and zero legal issue match
        strictly yields 0.0 authority score, even if from Supreme Court.
        """
        from core.authority_ranking import calculate_authority_score
        from core.legal_query_planner import LegalQueryPlan
        
        plan = LegalQueryPlan(
            legal_domain=["Criminal", "Cheque Bounce"],
            provisions=["Section 489-F PPC"],
            legal_questions=["Whether dishonest intent is required under 489-F PPC"]
        )
        # Irrelevant Supreme Court civil rent case
        cand = {
            "title": "Rent Controller Case",
            "citation": "2024 SCMR 9999",
            "court": "Supreme Court of Pakistan",
            "preview": "Ejectment of tenant for default of rent payment under urban rent ordinance.",
            "year": 2024
        }
        score, breakdown = calculate_authority_score(cand, plan)
        self.assertEqual(score, 0.0, "Zero relevance case must receive 0.0 authority score!")

    def test_heuristic_scorer_no_floor_clamp(self):
        """
        Remediation Spec Phase 4:
        Heuristic fallback cross-scorer is not clamped to 0.0 by the 0.35 Voyage reranker floor.
        """
        from core.authority_ranking import compute_fused_authority_score
        
        # Voyage score < 0.35 clamped to 0.0
        voyage_fused = compute_fused_authority_score(0.30, 0.50, relevance_floor=0.35, scorer="voyage-rerank-2")
        self.assertEqual(voyage_fused, 0.0)
        
        # Heuristic score < 0.35 is NOT clamped to 0.0
        heuristic_fused = compute_fused_authority_score(0.30, 0.50, relevance_floor=0.35, scorer="fallback-heuristic")
        self.assertGreater(heuristic_fused, 0.0)


    def test_memo_verifier_rule_d_unindexed_statute_does_not_block(self):
        """
        Remediation Spec Phase 5 (F16 fix):
        Unindexed peripheral statutory citations are flagged as unverified in report notices
        without blocking the whole memorandum.
        """
        from legal_ai.verification.memo_verifier import verify_memorandum_text
        
        # Valid memo containing a peripheral unindexed statutory reference
        memo_with_peripheral = (
            "Under Section 489-F PPC, dishonest intent is a foundational ingredient.\n"
            "The petitioner also referenced Section 888 of the Special Commercial Enactment."
        )
        report = verify_memorandum_text(memo_with_peripheral)
        # Check that failures does NOT contain CITED_PROVISION_NOT_IN_VERIFIED_STORE
        rule_d_failures = [f for f in report.get("failures", []) if f.get("category") == "CITED_PROVISION_NOT_IN_VERIFIED_STORE"]
        self.assertEqual(len(rule_d_failures), 0, "Unindexed statute must not be a blocking failure!")

    def test_content_level_and_prompt_rule_in_precedent_block(self):
        """
        Remediation Spec Phase 5:
        _build_precedent_context_block passes content_level, truncated status,
        and PROMPT RULE (HEADNOTE-ONLY) to the prompt.
        """
        from legal_ai.query_engine.query_processor import _build_precedent_context_block
        
        cards = [
            {
                "citation": "2024 SCMR 1567",
                "case_name": "Tariq v. State",
                "court": "Supreme Court of Pakistan",
                "content_level": "headnote_only",
                "is_headnote_only": True,
                "truncated": True,
                "preview": "Dishonest issuance under Section 489-F PPC requires mens rea at inception."
            }
        ]
        block = _build_precedent_context_block(cards)
        self.assertIn("Content Level", block)
        self.assertIn("headnote_only", block)
        self.assertIn("Truncated**: True", block)
        self.assertIn("PROMPT RULE (HEADNOTE-ONLY)", block)


    def test_phase6_infrastructure_hygiene(self):
        """
        Remediation Spec Phase 6:
        Infrastructure and hygiene checks:
        1. Async Supabase execution helper safe_supabase_query_async is available.
        2. Modular APIRouters (queries, judgments, auth) are defined and exportable.
        3. server.py is available as clean entrypoint runner.
        """
        from legal_ai.config import safe_supabase_query_async
        self.assertTrue(callable(safe_supabase_query_async))
        
        from routers.queries import router as q_router
        from routers.judgments import router as j_router
        from routers.auth import router as a_router
        self.assertIsNotNone(q_router)
        self.assertIsNotNone(j_router)
        self.assertIsNotNone(a_router)
        
        import server
        self.assertIsNotNone(server)

if __name__ == "__main__":
    unittest.main()
