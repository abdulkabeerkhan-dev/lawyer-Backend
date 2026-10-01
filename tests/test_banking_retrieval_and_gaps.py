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
            "Under the second proviso to Order XXI Rule 90 CPC as amended and interpreted in Tariq Zubair Khan (2024 SCMR 1085), "
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
            {"id": "doc_1", "score": 0.85, "citation": "2024 SCMR 1085", "court": "Supreme Court of Pakistan"}
        ])
        logger.log_coverage_gap("Lahore High Court authority", "0 LHC cases found in database")
        logger.log_fallback_event("site:lhc.gov.pk auction sale", ["lhc.gov.pk"], 2)
        logger.log_negative_disclosure("50% mandatory pre-deposit", "Statutory deposit is 20% under Order XXI Rule 90 CPC")
        logger.log_final_context([
            {"case_id": "doc_1", "citation": "2024 SCMR 1085", "court": "Supreme Court of Pakistan", "content_type": "full_text", "outcome": "Dismissed"}
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


if __name__ == "__main__":
    unittest.main()
