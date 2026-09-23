import unittest
import sys
import os

# Add parent directory to path so core can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.legal_guardrails import lint_legal_output, SYSTEM_LEGAL_DIRECTIVE

class TestLegalGuardrails(unittest.TestCase):

    def test_lint_legal_output_catches_hallucinations(self):
        """
        Test 1: Validate that lint_legal_output correctly catches:
        - 12-year limitation hallucination for specific performance
        - Foreign statutes (Indian Evidence Act, IPC)
        - Non-existent Section 271 CPC
        - Forum mismatch (High Court of Balochistan for Lahore query)
        """
        bad_output = """
        Suit for Specific Performance of Agreement to Sell regarding plot in DHA Lahore.
        Limitation: Governed by Article 109 under a 12 years limitation period.
        Under Section 114 Indian Evidence Act and Section 228 IPC, the defendant is liable.
        Enforcement must be filed under Section 271 CPC.
        Maintainable Forum: Constitutional Writ before High Court of Balochistan.
        """
        query_context = "Agreement to sell plot in DHA Lahore specific performance"
        
        errors = lint_legal_output(bad_output, query_context=query_context)
        
        self.assertTrue(any("12 years limitation" in e for e in errors), "Failed to detect 12 years limitation for specific performance")
        self.assertTrue(any("Article 109" in e for e in errors), "Failed to detect Article 109 misuse for specific performance")
        self.assertTrue(any("Indian Evidence Act" in e for e in errors), "Failed to detect Indian Evidence Act citation")
        self.assertTrue(any("IPC" in e for e in errors), "Failed to detect IPC citation")
        self.assertTrue(any("Section 271 CPC" in e for e in errors), "Failed to detect phantom Section 271 CPC")
        self.assertTrue(any("High Court of Balochistan" in e for e in errors), "Failed to detect Balochistan forum mismatch for Lahore query")

    def test_clean_specific_performance_response_dha_lahore(self):
        """
        Test 2: Mock a specific performance query for DHA Lahore and assert that
        formatted response complies with guardrails:
        - Mentions Article 113, 3 years, Lahore High Court
        - Does NOT mention Article 109 (12 years) or Balochistan
        """
        valid_response = """
        ### I. EXECUTIVE SUMMARY & LEGAL OPINION
        Suit for Specific Performance of an Agreement to Sell concerning property in DHA Lahore lies under Section 12 of the Specific Relief Act 1877.
        Limitation is strictly THREE (3) YEARS under Article 113 of the Limitation Act 1908.
        The competent forum for civil remedy is the Senior Civil Judge, Lahore, subject to appellate jurisdiction of the Lahore High Court.
        Evidence must be proved in accordance with Article 79 of the Qanun-e-Shahadat Order 1984 (QSO 1984).
        """
        query_context = "Suit for specific performance of agreement to sell for DHA Lahore plot"
        
        errors = lint_legal_output(valid_response, query_context=query_context)
        self.assertEqual(len(errors), 0, f"Valid output triggered unexpected lint errors: {errors}")
        
        self.assertIn("Article 113", valid_response)
        self.assertIn("THREE (3) YEARS", valid_response)
        self.assertIn("Lahore High Court", valid_response)
        self.assertNotIn("Article 109", valid_response)
        self.assertNotIn("12 years", valid_response)
        self.assertNotIn("Balochistan", valid_response)

    def test_cross_jurisdiction_semantic_leakage(self):
        """
        Test 3: Validate that lint_legal_output catches cross-jurisdiction semantic leakage:
        - CrPC 1973 / anticipatory bail Section 438
        - Limitation Act 1963 / Specific Relief Act 1963
        - Companies Act 2013 / SARFAESI / Evidence Act 1872
        - Section 148 ITO 2001 as reassessment/reopening
        """
        bad_response = """
        Application for anticipatory bail under Section 438 of CrPC 1973.
        Suit governed by Limitation Act 1963 and Specific Relief Act 1963.
        Company governance under Companies Act 2013 and SARFAESI Act.
        Evidence produced under Evidence Act 1872.
        Tax reassessment under Section 148 Income Tax Ordinance 2001.
        """
        errors = lint_legal_output(bad_response)
        self.assertTrue(any("CrPC 1973" in e for e in errors))
        self.assertTrue(any("Section 438" in e for e in errors))
        self.assertTrue(any("Limitation Act 1963" in e for e in errors))
        self.assertTrue(any("Specific Relief Act 1963" in e for e in errors))
        self.assertTrue(any("Companies Act 2013" in e for e in errors))
        self.assertTrue(any("SARFAESI" in e for e in errors))
        self.assertTrue(any("Evidence Act 1872" in e for e in errors))
        self.assertTrue(any("Section 148 ITO 2001" in e for e in errors))

    def test_489f_bail_classification_and_affidavit_checks(self):
        """
        Test 4: Validate that lint_legal_output catches:
        - 489-F PPC misclassified as a bailable offence
        - Punjab pre-arrest bail draft missing a supporting affidavit
        """
        bailable_err_response = """
        The accused is charged under Section 489-F PPC which is a bailable offence in Pakistan.
        """
        errors1 = lint_legal_output(bailable_err_response)
        self.assertTrue(any("bailable offence" in e for e in errors1))

        draft_missing_affidavit = """
        IN THE COURT OF THE SESSIONS JUDGE, LAHORE
        Petition for Pre-arrest Bail under Section 498 CrPC in FIR No. 123/2026 under Section 489-F PPC.
        Grounds:
        1. That the petitioner has been falsely implicated.
        2. That the cheque was given as security.
        PRAYER:
        It is respectfully prayed that pre-arrest bail may be granted to the petitioner.
        CERTIFICATE OF URGENCY:
        This matter is of urgent nature.
        """ + (" " * 500)
        errors2 = lint_legal_output(draft_missing_affidavit)
        self.assertTrue(any("Supporting Affidavit" in e for e in errors2))

    def test_narcotics_chain_of_custody_guardrail(self):
        """
        Test 5: Validate that lint_legal_output catches erroneous claim that
        failure to examine the Moharrir or carrier is not fatal in CNSA prosecutions.
        """
        bad_narcotics_response = """
        In this prosecution under Section 9(c) CNSA 1997, 5 kg charas was recovered.
        Although the Moharrir of the Malkhana was not produced, failure to examine the Moharrir is not fatal
        and is a mere irregularity cured by the positive Chemical Examiner's report.
        """
        query_context = "CNSA 1997 chain of custody effect of non-examination of Moharrir"
        errors = lint_legal_output(bad_narcotics_response, query_context=query_context)
        self.assertTrue(any("failure to examine the Moharrir" in e for e in errors), f"Failed to detect fatal Moharrir omission: {errors}")

        # Assert that SYSTEM_LEGAL_DIRECTIVE contains Rule 9 verbatim
        self.assertIn("In CNSA 1997 prosecutions, safe custody and safe transmission are mandatory links", SYSTEM_LEGAL_DIRECTIVE)
        self.assertIn("Ikramullah (2015 SCMR 1002)", SYSTEM_LEGAL_DIRECTIVE)
        self.assertIn("Imam Bakhsh (2018 SCMR 2039)", SYSTEM_LEGAL_DIRECTIVE)

    def test_section58_cpc_execution_guardrail(self):
        """
        Test 6: Validate that lint_legal_output catches:
        - Erroneous claim that civil imprisonment discharges or satisfies the decretal debt
        - Inappropriate citation of Section 34 CPC or Article 109 in decree execution
        """
        bad_execution_response = """
        The judgment-debtor has already served 6 months civil imprisonment in execution of the maintenance decree.
        Therefore, undergoing civil imprisonment satisfies the decretal debt and waives the decretal liability.
        The decree-holder can only claim interest under Section 34 CPC or mesne profits under Article 109.
        """
        query_context = "execution of maintenance decree civil imprisonment Section 58 CPC"
        errors = lint_legal_output(bad_execution_response, query_context=query_context)
        self.assertTrue(any("civil imprisonment discharges or satisfies" in e for e in errors), f"Failed to detect civil imprisonment debt discharge error: {errors}")
        self.assertTrue(any("Section 34 CPC" in e for e in errors), f"Failed to detect Section 34 CPC misuse: {errors}")
        self.assertTrue(any("Article 109" in e for e in errors), f"Failed to detect Article 109 misuse: {errors}")

        # Assert that SYSTEM_LEGAL_DIRECTIVE contains Rule 10 verbatim
        self.assertIn("In execution of Family Court and civil money decrees, civil imprisonment under Section 51 and Section 58 CPC / Section 13 Family Courts Act 1964 does NOT discharge or waive the decretal debt", SYSTEM_LEGAL_DIRECTIVE)
        self.assertIn("Serving the period of detention only bars the judgment-debtor from being re-arrested for that same default under Section 58(2) CPC", SYSTEM_LEGAL_DIRECTIVE)
        self.assertIn("Do NOT cite Section 34 CPC (which deals with interest) or Article 109 Limitation Act", SYSTEM_LEGAL_DIRECTIVE)

    def test_sanitize_precedent_card_removes_scraper_junk(self):
        from main import sanitize_precedent_card
        dirty_card = {
            "case_name": "Citation Name: PLD 2007 Lah 190 LAHORE-HIGH-COURT MUHAMMAD ASLAM VS Mst. NASREEN AKHTAR and others Before: Lahore High Court (Rawalpindi Bench) Writ",
            "citation": "Citation Name: PLD 2007 Lah 190 LAHORE",
            "court_name": "Lahore High Court",
            "court": "Lahore High Court",
            "holding": "Citation Name: PLD 2007 Lah 190 LAHORE-HIGH-COURT MUHAMMAD ASLAM VS Mst. NASREEN AKHTAR. Civil imprisonment does NOT discharge, satisfy, or wipe out the decretal debt.",
            "raw_judgment_text": "Citation Name: PLD 2007 Lah 190 LAHORE-HIGH-COURT MUHAMMAD ASLAM VS Mst. NASREEN AKHTAR and others Before: Lahore High Court (Rawalpindi Bench) Writ Petition No. 123 of 2006. Civil imprisonment does not satisfy debt.",
            "operative_result": "Citation Name: PLD 2007 Lah 190 The decree remains alive, operative, and fully enforceable against property.",
            "parties": {"initiator": "Citation Name: Muhammad Aslam", "initiator_role": "Petitioner", "defender": "Mst. Nasreen Akhtar", "defender_role": "Respondent"}
        }
        clean = sanitize_precedent_card(dirty_card)
        self.assertEqual(clean["case_name"], "Muhammad Aslam v. Mst. Nasreen Akhtar And Others")
        self.assertEqual(clean["citation"], "PLD 2007 Lah 190")
        self.assertIn("Civil imprisonment does NOT discharge", clean["holding"])
        self.assertNotIn("Citation Name", clean["holding"])
        self.assertNotIn("Citation Name", clean["case_name"])
        self.assertNotIn("Citation Name", clean["citation"])
        self.assertNotIn("Citation Name", clean["raw_judgment_text"])
        self.assertNotIn("Citation Name", clean["operative_result"])
        self.assertNotIn("LAHORE-HIGH-COURT", str(clean))

    def test_fio_2001_section10_guardrail(self):
        # Assert Rule 13 directive text in SYSTEM_LEGAL_DIRECTIVE
        self.assertIn("Under Section 10 of the Financial Institutions (Recovery of Finances) Ordinance 2001, compliance with subsections (3), (4), and (5) is mandatory", SYSTEM_LEGAL_DIRECTIVE)
        self.assertIn("As held in Apollo Textile Mills (PLD 2012 SC 268) and Tri-Star Shipping (2015 SCMR 1060), failure to provide a specific statement of accounts or formulated dispute points is fatal", SYSTEM_LEGAL_DIRECTIVE)
        self.assertIn("The Banking Court has no jurisdiction to grant conditional leave on deposit of security and must reject the leave application and pass a decree under Section 10(11)", SYSTEM_LEGAL_DIRECTIVE)

        # Assert linter intercepts false claims that Section 10(3)-(5) is directory
        bad_output = "In a suit under FIO 2001, the requirements of section 10 subsections (3), (4), and (5) are directory and the court can grant conditional leave on deposit of security despite non-compliance."
        errors = lint_legal_output(bad_output, query_context="FIO 2001 Section 10 leave to defend")
        self.assertTrue(any("Apollo Textile Mills" in e and "Section 10(3)-(5)" in e for e in errors))

        # Assert clean output passes
        good_output = "Under Section 10 FIO 2001 and Apollo Textile Mills (PLD 2012 SC 268), compliance with subsections (3), (4), and (5) is mandatory; non-compliance mandates rejection and a decree under Section 10(11)."
        clean_errors = lint_legal_output(good_output, query_context="FIO 2001 Section 10 leave to defend")
        self.assertFalse(any("Section 10(3)-(5)" in e for e in clean_errors))

    def test_tax_writ_guardrail(self):
        # Assert Rule 14 directive text in SYSTEM_LEGAL_DIRECTIVE
        self.assertIn("Under Article 199 of the Constitution of Pakistan, the presence of an adequate alternate statutory remedy (such as appeals under Section 127 Income Tax Ordinance 2001) generally bars the entertainment of a writ petition", SYSTEM_LEGAL_DIRECTIVE)
        self.assertIn("As settled in Collector of Customs v. Sheikh Spinning Mills (1999 SCMR 1402) and Premier Systems (2022 SCMR 1978), allegations of procedural defect, ex-parte order, or lack of notice under Section 122(9) fall squarely within the remedial jurisdiction of the Commissioner (Appeals) and ATIR, unless the order is completely coram non judice or passed under an ultra vires law", SYSTEM_LEGAL_DIRECTIVE)

        # Assert linter intercepts assertion that natural justice defects automatically bypass tax appellate hierarchy
        bad_output = "Where the assessing officer passed an amended assessment without notice under Section 122(9), this violation of natural justice automatically bypasses the statutory appeal under Section 127 ITO 2001 and directly entitles the taxpayer to maintain an Article 199 writ petition."
        errors = lint_legal_output(bad_output, query_context="Income Tax Ordinance 2001 Section 122 assessment writ")
        self.assertTrue(any("1999 SCMR 1402" in e and "Section 127 ITO 2001" in e for e in errors))

        # Assert clean output passes
        good_output = "Under Premier Systems (2022 SCMR 1978) and 1999 SCMR 1402, an ex-parte order or lack of notice under Section 122(9) must be challenged via statutory appeal under Section 127 ITO 2001 before the Commissioner (Appeals), as an Article 199 writ does not lie when an adequate alternate remedy exists."
        clean_errors = lint_legal_output(good_output, query_context="Income Tax Ordinance 2001 Section 122 assessment writ")
        self.assertFalse(any("1999 SCMR 1402" in e for e in clean_errors))

    def test_corporate_oppression_guardrail(self):
        # Assert Rule 15 directive text in SYSTEM_LEGAL_DIRECTIVE
        self.assertIn("Under the Companies Act 2017, winding up of a commercially solvent and running company under the 'just and equitable' clause (Section 301) is strictly a remedy of last resort", SYSTEM_LEGAL_DIRECTIVE)
        self.assertIn("Where minority shareholders allege oppression, mismanagement, or deadlock under Section 286, the Company Bench must explore alternative corrective remedies", SYSTEM_LEGAL_DIRECTIVE)
        self.assertIn("The Court will not order the corporate death of a solvent company where its substratum remains intact, in accordance with Haji Muhammad Ismail (PLD 2002 SC 510)", SYSTEM_LEGAL_DIRECTIVE)

        # Assert linter intercepts assertion that winding up is the primary/mandatory remedy for oppression in solvent company
        bad_output = "In this dispute under the Companies Act 2017 regarding minority oppression in a solvent company, winding up is the primary remedy and must be ordered for deadlock without exploring alternative remedies."
        errors = lint_legal_output(bad_output, query_context="Companies Act 2017 Section 286 minority oppression winding up")
        self.assertTrue(any("Haji Muhammad Ismail" in e and "Section 286/301" in e for e in errors))

        # Assert clean output passes
        good_output = "Under Haji Muhammad Ismail (PLD 2002 SC 510) and Section 286/301 Companies Act 2017, winding up a solvent running company is strictly a remedy of last resort; the Company Bench should order forensic audits or share buyouts."
        clean_errors = lint_legal_output(good_output, query_context="Companies Act 2017 Section 286 minority oppression winding up")
        self.assertFalse(any("Haji Muhammad Ismail" in e for e in clean_errors))

    def test_statutory_conflict_non_obstante_guardrail(self):
        # Assert Rule 16 directive text in SYSTEM_LEGAL_DIRECTIVE
        self.assertIn("Where two special statutes both contain non-obstante clauses", SYSTEM_LEGAL_DIRECTIVE)
        self.assertIn("the statute enacted LATER IN TIME generally prevails over the prior statute (leges posteriores priores contrarias abrogant)", SYSTEM_LEGAL_DIRECTIVE)
        self.assertIn("Syed Mushahid Shah v. Federal Investigation Agency (2017 SCMR 1218)", SYSTEM_LEGAL_DIRECTIVE)

        # Assert linter intercepts assertion that earlier statute prevails without considering later in time
        bad_output = "Where two special laws conflict, the earlier statute prevails over the later statute."
        errors = lint_legal_output(bad_output, query_context="two special laws in conflict with non-obstante clause which would prevail")
        self.assertTrue(any("Syed Mushahid Shah" in e and "2017 SCMR 1218" in e for e in errors))

        # Assert clean output passes
        good_output = "Under Syed Mushahid Shah v. FIA (2017 SCMR 1218), where two special laws conflict and both contain non-obstante clauses, the statute later in time generally prevails under leges posteriores priores contrarias abrogant, subject to legislative purpose and Article 25 safeguards."
        clean_errors = lint_legal_output(good_output, query_context="two special laws in conflict with non-obstante clause which would prevail")
        self.assertFalse(any("Syed Mushahid Shah" in e for e in clean_errors))

    def test_headnote_only_disclosure_guardrail(self):
        """
        Test Rule 19: Answers citing headnote_only precedents must include the
        mandatory disclosure (headnote summary + advice to verify against certified text).
        """
        mock_chunks = [
            {
                "citation": "2026 SCMR 99",
                "content_type": "headnote_only",
                "title": "Binyameen v. The State"
            }
        ]

        # Case 1: Answer cites 2026 SCMR 99 without any disclosure -> MUST fail
        bad_answer = "In 2026 SCMR 99, the Supreme Court held that the accused was entitled to bail under Section 497(2) CrPC."
        errors = lint_legal_output(bad_answer, context_chunks=mock_chunks)
        self.assertTrue(any("2026 SCMR 99" in e and "headnote-only" in e for e in errors))

        # Case 2: Answer cites 2026 SCMR 99 with full Directive 13 disclosure -> MUST pass
        good_answer = (
            "In 2026 SCMR 99, the reported headnote summary indicates that bail was granted under Section 497(2) CrPC. "
            "Note: Only the editorial headnote summary is currently recorded in the database; counsel is advised to verify "
            "the proposition against the certified official full judgment text before presenting in pleadings."
        )
        clean_errors = lint_legal_output(good_answer, context_chunks=mock_chunks)
        self.assertFalse(any("headnote-only" in e for e in clean_errors))

if __name__ == '__main__':
    unittest.main()




