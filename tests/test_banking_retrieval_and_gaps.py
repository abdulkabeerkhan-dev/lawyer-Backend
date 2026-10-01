import os
import json
import unittest
from core.legal_guardrails import decompose_compound_legal_query, lint_legal_output
from core.retrieval_logger import RetrievalTraceLogger, LOG_DIR
from main import determine_case_outcome, extract_clean_ratio_snippet, generate_clean_snippet


class TestBankingRetrievalAndGaps(unittest.TestCase):

    def test_decompose_compound_legal_query(self):
        query = (
            "Under Financial Institutions Recovery of Finances Ordinance 2001 and Order XXI Rule 90 CPC, "
            "what is the effect of fraud in conducting auction sale, whether 50% mandatory pre-deposit is constitutional, "
            "and what are the proclamation standards and reserve price requirements according to Lahore High Court and Supreme Court?"
        )
        subqueries = decompose_compound_legal_query(query)
        self.assertIsInstance(subqueries, list)
        self.assertGreaterEqual(len(subqueries), 3)

        self.assertTrue(any("fraud" in q.lower() or "auction" in q.lower() for q in subqueries))
        self.assertTrue(any("deposit" in q.lower() or "pre-deposit" in q.lower() for q in subqueries))
        self.assertTrue(any("proclamation" in q.lower() or "reserve price" in q.lower() for q in subqueries))

    def test_decompose_simple_query(self):
        simple_query = "What is the limitation period for filing an execution objection under Section 47 CPC?"
        subqueries = decompose_compound_legal_query(simple_query)
        self.assertEqual(len(subqueries), 1)
        self.assertEqual(subqueries[0], simple_query)

    def test_determine_case_outcome_appellate_tail_priority(self):
        judgment_text = (
            "The trial court previously allowed the application filed by respondent under Order IX Rule 13 CPC. "
            "The High Court also allowed the miscellaneous application. "
            "However, upon hearing both learned counsel at length and perusing the record of execution proceedings, "
            "we find that the petitioner failed to demonstrate any material irregularity or substantial fraud. "
            "Consequently, this civil petition is devoid of any legal merit and is accordingly dismissed with no order as to costs."
        )
        outcome = determine_case_outcome(judgment_text, None)
        self.assertEqual(outcome, "Dismissed")

    def test_determine_case_outcome_allowed(self):
        judgment_text = (
            "The respondent execution creditor failed to establish proper publication of the proclamation of sale. "
            "For the foregoing reasons, the impugned order of the High Court is set aside, the objection is accepted, "
            "and this appeal is allowed with costs throughout."
        )
        outcome = determine_case_outcome(judgment_text, None)
        self.assertEqual(outcome, "Allowed")

    def test_extract_clean_ratio_snippet_docket_stripping(self):
        raw_text = (
            "and others Respondents C.P.L.A. No. 88-P of 2024 on appeal from Peshawar High Court. "
            "For the reasons recorded, the deposit under the second proviso to Order XXI Rule 90 CPC is mandatory and must accompany the application."
        )
        snippet = extract_clean_ratio_snippet(raw_text)
        self.assertNotIn("and others Respondents", snippet)
        self.assertNotIn("C.P.L.A. No. 88-P", snippet)
        self.assertTrue(len(snippet) > 10)

    def test_lint_legal_output_rule_22_flags_50_percent_deposit_error(self):
        bad_response = (
            "### STATUTORY & PROCEDURAL FRAMEWORK\n"
            "Under the Financial Institutions (Recovery of Finances) Ordinance 2001 read with Order XXI Rule 90 CPC, "
            "an objector must comply with the 50% pre-deposit requirement before the court will entertain an objection.\n"
            "This 50% deposit requirement has been tested and upheld against constitutional challenge by the superior courts."
        )
        errors = lint_legal_output(bad_response)
        self.assertIsInstance(errors, list)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("50% pre-deposit" in e or "20%" in e for e in errors))

    def test_lint_legal_output_passes_with_correct_20_percent_rule(self):
        good_response = (
            "### STATUTORY & PROCEDURAL FRAMEWORK\n"
            "Under the second proviso to Order XXI Rule 90 CPC as amended and interpreted in Tariq Zubair Khan (2024 SCMR 1218), "
            "an applicant challenging an execution sale must deposit an amount not exceeding 20% of the sum realized in the sale, "
            "or furnish security. Neither FIO 2001 nor Order XXI Rule 90 imposes a mandatory 50% pre-deposit."
        )
        errors = lint_legal_output(good_response)
        self.assertIsInstance(errors, list)
        rule_22_errors = [e for e in errors if "50% pre-deposit" in e or "20%" in e]
        self.assertEqual(len(rule_22_errors), 0)

    def test_retrieval_trace_logger_lifecycle(self):
        job_id = "test_trace_job_12345"
        logger = RetrievalTraceLogger(job_id=job_id, raw_query="Test query for banking mortgage auction")
        logger.log_decomposition(["Subquery 1: Fraud", "Subquery 2: Proclamation"])
        logger.log_subquery_results("Subquery 1: Fraud", dense_count=5, sparse_count=3, top_hits=[
            {"id": "doc_1", "score": 0.85, "citation": "2024 SCMR 1218", "court": "Supreme Court of Pakistan"}
        ])
        logger.log_coverage_gap("Lahore High Court authority", "0 LHC cases found in database")
        logger.log_fallback_event("site:lhc.gov.pk auction sale", ["lhc.gov.pk"], 2)
        logger.log_negative_disclosure("50% mandatory pre-deposit", "Statutory deposit is 20% under Order XXI Rule 90 CPC")
        logger.log_final_context([
            {"case_id": "doc_1", "citation": "2024 SCMR 1218", "court": "Supreme Court of Pakistan", "content_type": "full_text", "outcome": "Dismissed"}
        ])
        logger.write_trace()

        trace_file = os.path.join(LOG_DIR, f"{job_id}.json")
        self.assertTrue(os.path.exists(trace_file), f"Trace file was not created at {trace_file}")

        with open(trace_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["job_id"], job_id)
        self.assertEqual(len(data["decomposed_subqueries"]), 2)
        self.assertEqual(len(data["subquery_retrievals"]), 1)
        self.assertEqual(len(data["coverage_gaps"]), 1)
        self.assertEqual(len(data["fallback_events"]), 1)
        self.assertEqual(len(data["negative_disclosures"]), 1)
        self.assertEqual(len(data["final_precedents"]), 1)

        try:
            os.remove(trace_file)
        except OSError:
            pass

    def test_generality_universal_citation_grounding(self):
        from core.legal_guardrails import lint_legal_output
        bad_text = (
            "According to the Supreme Court in 2026 PLD 999, the execution court must confirm the sale.\n"
            "Also citing 2024 SCMR 1218."
        )
        context_chunks = [{"citation": "2024 SCMR 1218", "text": "Under Order XXI Rule 90 CPC..."}]
        errors = lint_legal_output(bad_text, query_context="execution sale", context_chunks=context_chunks)
        self.assertTrue(any("2026 PLD 999" in e and "Ungrounded Precedent Citation" in e for e in errors))
        self.assertFalse(any("2024 SCMR 1218" in e for e in errors))

    def test_opposite_direction_headnote_vs_order(self):
        from core.legal_guardrails import is_compiled_headnote, classify_judgment_structure, parse_outcome_from_tail

        # 1. Tariq Zubair Khan (2024 SCMR 1218) - 531 words (exceeds 300 words, must be headnote_only)
        tariq_zubair_compiled_hn = (
            "Citation Name: 2024 SCMR 1218 SUPREME-COURT\n"
            "Bookmark this Case\n\n"
            "TARIQ ZUBAIR KHAN VS Mst. TABASSUM KHAN\n\n"
            "Auction proceedings--Term , Civil Procedure Code --Order XXI of C.P.C. Execution of Decrees and Orders--90 , "
            "Execution of decree--TERM , Objection petition--Term ,\n"
            "O. XXI., R. 90 Execution of decree Auction proceedings Objection petition Conditions required to be satisfied "
            "under Order XXI, Rule 90 of the Code of Civil Procedure, 1908 (\"C.P.C.\") Sale may be set aside on the grounds of "
            "material irregularity or fraud in publishing or conducting it Proviso to Order XXI, Rule 90, C.P.C. applicant "
            "must deposit an amount not exceeding 20% in court or furnish security Unless the applicant proves that he has sustained "
            "substantial injury by reason of such irregularity or fraud, no sale shall be set aside.\n\n"
            "Held: Second proviso to Order XXI Rule 90 CPC requires an applicant to deposit an amount not exceeding 20%--- "
            "Petition was dismissed and leave to appeal was refused.\n\n"
            "Copyrights © 2026 by Oratier Technologies (Pvt.) Ltd."
        )
        res_tariq = classify_judgment_structure(tariq_zubair_compiled_hn)
        self.assertEqual(res_tariq["detected_type"], "headnote_only")
        self.assertTrue(is_compiled_headnote(tariq_zubair_compiled_hn))
        self.assertEqual(res_tariq["parsed_outcome"], "leave_refused")

        # 2. Kauser Parveen (1997 PLD 208) - 339 words (exceeds 300 words, must be headnote_only)
        kauser_parveen_hn = (
            "Citation Name: 1997 PLD 208 LAHORE-HIGH-COURT-LAHORE\n"
            "Bookmark this Case\n\n"
            "KAUSAR PARVEEN VS AHMAD ALI ZAFAR\n\n"
            "Constitution of Pakistan 1973--199 ,\n"
            "Constitution of Pakistan 1973 S. 100 Constitution of Pakistan (1973), Art. 199 Constitutional petition--Quashing of order "
            "Judicial Magistrate on the application of respondent under S. 100, Cr.P.C. issued search warrant for recovery of petitioner...\n"
            "Copyrights © 2026 by Oratier Technologies (Pvt.) Ltd."
        )
        res_kauser = classify_judgment_structure(kauser_parveen_hn)
        self.assertEqual(res_kauser["detected_type"], "headnote_only")
        self.assertTrue(is_compiled_headnote(kauser_parveen_hn))

        # 3. Vital Chemical Corporation (2026 CLD 96) - 313 words (exceeds 300 words, must be headnote_only)
        vital_chemical_hn = (
            "Citation Name: 2026 CLD 96 LAHORE-HIGH-COURT-LAHORE\n\n"
            "VITAL CHEMICAL CORPORATION VS MCB BANK LIMITED\n\n"
            "Ss.19 & 22---Civil Procedure Code (V of 1908), O.XXI, R.66---Execution proceedings---Public auction---Reserve price---"
            "Determining factors---Appellant / judgment debtor was aggrieved of auction proceedings and dismissal of his objections---"
            "Contention of appellant / judgment debtor was that reserve price was not properly fixed---Validity---In public auctions it is "
            "imperative that reserve price is determined in the most transparent manner because it is in the interest of all the parties that "
            "mortgaged asset must fetch best and highest price---Before finalization of reserve price, there are two conditions precedent; "
            "first, to ensure that independent evaluators from the list of Pakistan Banks Association have been appointed who may evaluate "
            "the property according to its location, commercial value as well as assess rate compatible to DC rates' value---"
            "High Court remanded the matter to Executing Court to hold auction proceedings afresh from the stage of issuance of notices "
            "under O. XXI, R. 66, C.P.C.---Appeal was allowed accordingly."
        )
        res_vital = classify_judgment_structure(vital_chemical_hn)
        self.assertEqual(res_vital["detected_type"], "headnote_only")
        self.assertTrue(is_compiled_headnote(vital_chemical_hn))
        self.assertEqual(res_vital["parsed_outcome"], "appeal_allowed")

        # 4. Noor Hayat Cotton Ginners (2026 CLD 68) - 181 words (headnote_only)
        noor_hayat_hn = (
            "Citation Name: 2026 CLD 68 LAHORE-HIGH-COURT-LAHORE\n\n"
            "NOOR HAYAT COTTON GINNERS VS The BANK OF PUNJAB\n\n"
            "O. XXI, R.90---Financial Institutions (Recovery of Finances) Ordinance (XLVI of 2001), S. 19---Auction proceedings---"
            "Objection petition, filing/ hearing of---Condition precedent to deposit 50% of the sale proceeds ---Scope---"
            "Record revealed that in order to execute the judgment and decree passed by the Banking Court ,auction was conducted for the "
            "sale of mortgaged property---Appellants filed Objection Petition under O. XXI, R. 90 of the Civil Procedure Code, 1908 (C.P.C.) "
            "against the auction proceedings---The Executing Court directed Appellants to deposit 50% of the sale proceeds as a condition precedent "
            "for the Objection Petition to be heard on merits, failing which, the same would be dismissed on said sole ground---"
            "Held: Appellants failed to make the required deposit ; consequently, the Objection Petition was dismissed through the impugned order---"
            "The condition to deposit the amount under O. XXI, R. 90, C.P.C. is mandatory when the Executing Court specifically requires such deposit "
            "and warns of consequences of non-deposit---Appeal was dismissed, in circumstances."
        )
        res_noor = classify_judgment_structure(noor_hayat_hn)
        self.assertEqual(res_noor["detected_type"], "headnote_only")
        self.assertTrue(is_compiled_headnote(noor_hayat_hn))
        self.assertEqual(res_noor["parsed_outcome"], "appeal_dismissed")

        # 5. Abdul Salam Khan (genuine judicial short order - under 300 words, must NOT be headnote_only)
        abdul_salam_order_text = (
            "ORDER\n"
            "MUHAMMAD ALI MAZHAR, J.---Through this civil petition under Article 185(3) of the Constitution, "
            "the petitioner has called in question the order passed by the High Court. "
            "Heard learned counsel for the petitioner at length and perused the available record. "
            "The execution court had granted ample opportunities to the judgment-debtor to satisfy the decree. "
            "We find no legal infirmity or jurisdictional defect in the impugned order. Leave refused."
        )
        res_abdul = classify_judgment_structure(abdul_salam_order_text)
        self.assertEqual(res_abdul["detected_type"], "order_text")
        self.assertFalse(is_compiled_headnote(abdul_salam_order_text))
        self.assertEqual(res_abdul["parsed_outcome"], "leave_refused")

        # 6. Mixed Headnote + Order Text (Abdul Salam Khan full reporting style)
        mixed_record_text = (
            "P L D 2025 Supreme Court 1043\n"
            "Present: Syed Mansoor Ali Shah and Ayesha A. Malik, JJ\n"
            "ABDUL SALAM KHAN---Petitioner\nVersus\nMessrs BANK AL-HABIB LTD. and others---Respondents\n\n"
            "(a) Constitution of Pakistan---\n"
            "----Arts. 4, 9 & 10-A---Auction proceedings---Delay in adjudication---\n"
            "Held: The right to access to justice encompasses the right to timely justice.\n\n"
            "Date of hearing: 18th July, 2025.\n\n"
            "ORDER\n\n"
            "SYED MANSOOR ALI SHAH, J.---The present petition arises out of a challenge to the auction "
            "of an immovable property conducted by the respondent Bank under the Financial Institutions "
            "(Recovery of Finances) Ordinance, 2001. We have heard learned counsel for the petitioner. "
            "The objections of the petitioner against the auction were found to be untenable. "
            "The petition was dismissed on merits as well as for non-prosecution."
        )
        res_mixed = classify_judgment_structure(mixed_record_text)
        self.assertEqual(res_mixed["detected_type"], "mixed")
        self.assertTrue(res_mixed["is_mixed"])
        self.assertIsNotNone(res_mixed["split_offset"])
        self.assertIn("SYED MANSOOR ALI SHAH, J.", res_mixed["order_text"])
        self.assertIn("----Arts. 4, 9 & 10-A---", res_mixed["headnote_text"])
        self.assertEqual(res_mixed["parsed_outcome"], "petition_dismissed")

    def test_overclaim_holding_scope(self):
        from core.legal_guardrails import lint_legal_output
        overclaim_text = (
            "The Supreme Court held that 50% is non-waivable and must be deposited in all mortgage auctions."
        )
        errors = lint_legal_output(overclaim_text, query_context="banking mortgage auction")
        self.assertTrue(any("Over-claiming precedent holding" in e or "non-waivable" in e for e in errors))

        partition_misattribution = (
            "Under FIO 2001 and banking court mortgage execution, partition of the property must follow partition rules."
        )
        errors2 = lint_legal_output(partition_misattribution, query_context="FIO 2001 mortgage execution")
        self.assertTrue(any("Domain Misattribution" in e for e in errors2))

    def test_normalized_statute_attribution(self):
        from core.legal_guardrails import normalize_statute_citation, is_statute_in_source, verify_case_grounding
        norm1 = normalize_statute_citation("Order XXI Rule 66")
        norm2 = normalize_statute_citation("O.XXI, R.66")
        norm3 = normalize_statute_citation("Order 21, Rule 66")
        self.assertEqual(norm1, norm2)
        self.assertEqual(norm2, norm3)
        self.assertEqual(norm1, "order 21 rule 66")

        source_text = "The executing court drew up the sale proclamation under O. XXI, R. 66 CPC after notice."
        self.assertTrue(is_statute_in_source("Order XXI Rule 66", source_text))
        self.assertFalse(is_statute_in_source("Order XXI Rule 90", source_text))

        res_unsupported = verify_case_grounding(
            cited_case_name="Test Case",
            source_judgment_text=source_text,
            model_assertion="The court applied Order XXI Rule 90 to set aside the sale."
        )
        self.assertFalse(res_unsupported["is_grounded"])
        self.assertTrue(any("Order Xxi Rule 90" in p or "order 21 rule 90" in p.lower() for p in res_unsupported["unsupported_propositions"]))

    def test_reconciliation_20_vs_50_deposit(self):
        from core.legal_guardrails import lint_legal_output
        reconciled_text = (
            "Under the second proviso to Order XXI Rule 90 CPC, the statutory pre-deposit threshold is strictly 20%. "
            "While the High Court in the cited instance directed a 50% deposit as an ad-hoc interim condition, "
            "the legal basis for demanding an amount exceeding 20% is not addressed in retrieved sources."
        )
        errors = lint_legal_output(reconciled_text, query_context="banking mortgage auction 50% deposit")
        rule_errors = [e for e in errors if "50%" in e or "non-waivable" in e]
        self.assertEqual(len(rule_errors), 0)

    def test_card_identity_two_way_verification(self):
        citations_by_id = {
            "abdul_salam_1": {"case_id": "abdul_salam_1", "citation": "2024 SCMR 1218", "title": "Abdul Salam v. Bank"},
            "bench_case_2": {"case_id": "bench_case_2", "citation": "2025 PLD 280", "title": "Bench Case v. Federation"},
        }
        citations_by_citation = {
            "2024scmr1218": citations_by_id["abdul_salam_1"],
            "2025pld280": citations_by_id["bench_case_2"],
        }

        # Conflicting card: claimed_id is abdul_salam_1 but claimed citation is 2025 PLD 280
        conflicting_card = {"case_id": "abdul_salam_1", "citation": "2025 PLD 280"}
        claimed_id = conflicting_card.get("case_id")
        claimed_cit_key = "2025pld280"

        matched_by_id = citations_by_id.get(claimed_id)
        matched_by_cit = citations_by_citation.get(claimed_cit_key)

        matched = None
        if matched_by_id and matched_by_cit:
            id_from_id = matched_by_id.get("case_id")
            id_from_cit = matched_by_cit.get("case_id")
            if id_from_id != id_from_cit:
                matched = None  # Conflict -> Dropped!
            else:
                matched = matched_by_id

        self.assertIsNone(matched, "Conflicting card identity must be dropped!")

        # Consistent card
        consistent_card = {"case_id": "abdul_salam_1", "citation": "2024 SCMR 1218"}
        matched_by_id = citations_by_id.get(consistent_card["case_id"])
        matched_by_cit = citations_by_citation.get("2024scmr1218")
        if matched_by_id and matched_by_cit and matched_by_id.get("case_id") == matched_by_cit.get("case_id"):
            matched = matched_by_id
        self.assertIsNotNone(matched)
        self.assertEqual(matched["citation"], "2024 SCMR 1218")

    def test_fraud_subquery_decomposition(self):
        from core.legal_guardrails import decompose_compound_legal_query
        query = "Under Order XXI Rule 90 CPC, what is the effect of fraud in conducting execution sale and is 20% deposit mandatory?"
        subqueries = decompose_compound_legal_query(query)
        self.assertTrue(any("fraud" in sq.lower() for sq in subqueries))
        self.assertTrue(any("deposit" in sq.lower() for sq in subqueries))

    def test_check_memo_completeness(self):
        from core.legal_guardrails import check_memo_completeness
        incomplete_memo = (
            "### I. EXECUTIVE SUMMARY & LEGAL OPINION\nToo brief.\n"
            "### II. CONTROLLING STATUTORY ARCHITECTURE\nBrief.\n"
        )
        is_complete, issues = check_memo_completeness(incomplete_memo, is_formal_opinion=True)
        self.assertFalse(is_complete)
        self.assertGreater(len(issues), 0)

        complete_memo = (
            "### I. EXECUTIVE SUMMARY & LEGAL OPINION\n" + ("The court execution sale under Order XXI Rule 90 CPC was analyzed with legal precision. " * 5) + "\n\n"
            "### II. CONTROLLING STATUTORY ARCHITECTURE\n" + ("The Financial Institutions Recovery of Finances Ordinance 2001 Section 19 governs execution. " * 5) + "\n\n"
            "### III. CONTROLLING JUDICIAL PRECEDENTS & APPELLATE RATIO\n" + ("The Supreme Court in Tariq Zubair Khan 2024 SCMR 1218 settled the 20% deposit rule. " * 5) + "\n\n"
            "### IV. STRATEGIC LEGAL ANALYSIS & PROCEDURAL RISKS\n" + ("The judgment-debtor must demonstrate material irregularity and substantial injury resulting. " * 5) + "\n\n"
            "### V. PRACTICAL NEXT STEPS & PROCEDURAL ROADMAP\n" + ("File the objection petition within thirty days of sale accompanied by verified security. " * 5) + "\n\n"
            "<<<CARDS>>>\n[{\"case_name\": \"Tariq Zubair Khan\", \"citation\": \"2024 SCMR 1218\"}]\n<<<END_CARDS>>>"
        )
        is_complete, issues = check_memo_completeness(complete_memo, is_formal_opinion=True)
        self.assertTrue(is_complete, f"Completeness check failed with issues: {issues}")

    def test_statutory_validator_no_unverified_rules(self):
        statute_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "statute_tables", "CPC_1908.json")
        with open(statute_path, "r", encoding="utf-8") as f:
            cpc_data = json.load(f)

        has_23a = any("23-a" in str(r.get("canonical_id", "")).lower() or "23-a" in str(r.get("secondary_num", "")).lower() for r in cpc_data)
        has_8a = any("8-a" in str(r.get("canonical_id", "")).lower() or "8-a" in str(r.get("secondary_num", "")).lower() for r in cpc_data)
        self.assertFalse(has_23a, "Unverified Order XXI Rule 23-A must NOT be added to CPC_1908.json without certified gazette verification")
        self.assertFalse(has_8a, "Unverified Order XXVII Rule 8-A must NOT be added to CPC_1908.json without certified gazette verification")


if __name__ == "__main__":
    unittest.main()

