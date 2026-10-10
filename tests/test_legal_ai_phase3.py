"""
tests/test_legal_ai_phase3.py

Unit tests for legal_ai Phase 3 modules:
- legal_ai.synthesis.memorandum_generator
- legal_ai.verification.citation_validator
- legal_ai.verification.quote_verifier
"""

import unittest
from legal_ai.synthesis.memorandum_generator import (
    purge_debug_warnings,
    sanitize_precedent_card,
    REQUIRED_12_FIELDS,
    enforce_judgment_first_boundaries,
    query_requests_strategy,
    enforce_holding_attribution,
    is_headnote_only_card,
    classify_precedent_authority_level,
    get_authority_classification_tag,
    filter_and_cap_authorities,
    check_missing_statutory_source,
    enforce_missing_statutory_source_warning,
    enforce_proposition_confidence_guardrails,
    log_runtime_diagnostic,
)
from legal_ai.verification.citation_validator import (
    parse_pakistan_citation,
    repair_ocr_citation
)
from legal_ai.verification.quote_verifier import verify_quotations_in_text


class TestLegalAIPhase3(unittest.TestCase):

    def test_purge_debug_warnings(self):
        dirty_text = (
            "> ⚠️ **Prototype. Not verified for use in pleadings.**\n\n"
            "### EXECUTIVE SUMMARY & LEGAL OPINION\n"
            "This is substantive legal advice regarding Section 409 PPC [NOT CHECKED].\n\n"
            "> ⚠️ **[JUDICIAL REVIEW CORROBORATION NOTICE]**\n"
            "Propositions need corroboration.\n\n"
            "### STATUTORY & PROCEDURAL FRAMEWORK\n"
            "Section 420 PPC governs cheating.\n\n"
            "#### Statutory Currency Verification Status\n"
            "- **PPC_1860_SEC_409**: [NOT CHECKED]\n\n"
            "### APPENDIX: SYSTEM & VERIFICATION NOTICE\n"
            "System notice text here.\n"
        )
        cleaned = purge_debug_warnings(dirty_text)
        self.assertNotIn("Prototype", cleaned)
        self.assertNotIn("[JUDICIAL REVIEW CORROBORATION NOTICE]", cleaned)
        self.assertNotIn("Statutory Currency Verification Status", cleaned)
        self.assertNotIn("[NOT CHECKED]", cleaned)
        self.assertNotIn("APPENDIX: SYSTEM & VERIFICATION NOTICE", cleaned)
        self.assertIn("### EXECUTIVE SUMMARY & LEGAL OPINION", cleaned)
        self.assertIn("Section 409 PPC", cleaned)

    def test_precedent_card_12_fields(self):
        raw_card = {
            "id": "2024_SCMR_500",
            "case_id": "2024_SCMR_500",
            "title": "Tariq Mahmood v. The State",
            "citation": "2024 SCMR 500",
            "court": "Supreme Court of Pakistan",
            "year": "2024",
            "sections": ["Section 409 PPC", "Section 420 PPC"],
            "legal_issue": "Commercial loan default vs criminal breach of trust",
            "ratio_decidendi": "Mere non-payment of loan without dishonest intention at inception is a civil dispute.",
            "important_paragraphs": "Paragraph 7 and 8 discussing distinction between civil debt and entrustment.",
            "authority_strength": "Binding Supreme Court Precedent (Article 189)",
            "is_supabase_fts": False,
            "dense_score": 0.85,
            "raw_judgment_text": "Mere non-payment of loan without dishonest intention at inception is a civil dispute. " + "Detailed judgment text exceeding 150 words. " * 30,
            "content_type": "full_text"
        }
        sanitized = sanitize_precedent_card(raw_card)
        for field in REQUIRED_12_FIELDS:
            self.assertIn(field, sanitized, f"Field '{field}' missing from precedent card")
            self.assertTrue(sanitized[field], f"Field '{field}' has empty value")

        self.assertEqual(sanitized["source_type"], "Pinecone")
        self.assertEqual(sanitized["verification_status"], "FULL_TEXT_CHECKED")
        self.assertTrue(sanitized["pdf_url"].startswith("http"))

    def test_citation_validator(self):
        # 1. OCR repair
        repaired = repair_ocr_citation("2O24 S.C.M.R. 5OO")
        self.assertIn("2024", repaired)
        self.assertIn("SCMR", repaired)

        # 2. Parsing
        res = parse_pakistan_citation("2024 SCMR 500")
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["journal"], "SCMR")
        self.assertEqual(res["year"], 2024)
        self.assertEqual(res["page"], 500)
        self.assertEqual(res["court_inference"], "Supreme Court of Pakistan")

        res_hc = parse_pakistan_citation("2021 PCrLJ 120")
        self.assertTrue(res_hc["is_valid"])
        self.assertEqual(res_hc["journal"], "PCRLJ")
        self.assertEqual(res_hc["court_inference"], "High Court")

    def test_quote_verifier(self):
        context = [
            {
                "case_id": "2024_SCMR_500",
                "preview": "Held that mere non-payment of commercial loan without dishonest intention at inception is not criminal breach of trust."
            }
        ]
        # Text with genuine quote
        genuine_text = 'The Supreme Court confirmed that "mere non-payment of commercial loan without dishonest intention at inception" does not constitute an offence.'
        passed, details = verify_quotations_in_text(genuine_text, context)
        self.assertTrue(passed)
        self.assertEqual(len(details), 1)
        self.assertTrue(details[0]["is_grounded"])

        # Text with fake quote
        fake_text = 'The Court ruled that "every loan default is strictly punishable with life imprisonment and immediate asset seizure".'
        passed_fake, details_fake = verify_quotations_in_text(fake_text, context)
        self.assertFalse(passed_fake)
        self.assertFalse(details_fake[0]["is_grounded"])

    def test_enforce_judgment_first_boundaries_default(self):
        """Verifies prohibited sections are stripped and default output ends after Application to Query."""
        memo = (
            "## Legal Opinion\n"
            "This is an unauthorized legal opinion section that must be removed.\n\n"
            "## Legal Issue\n"
            "Whether Section 498 CrPC applies to commercial loan disputes.\n\n"
            "## Relevant Provisions\n"
            "- Code of Criminal Procedure — Section 498: Pre-arrest bail jurisdiction\n\n"
            "## Judicial Authorities\n"
            "### Tariq Mahmood v. State — 2024 SCMR 500\n"
            "- Court: Supreme Court of Pakistan\n"
            "- Relevant facts: Commercial loan default without dishonest intention.\n"
            "- Court held: Pre-arrest bail confirmed.\n"
            "- Ratio decidendi: Commercial default is a civil dispute.\n\n"
            "## Application to Query\n"
            "The principles in 2024 SCMR 500 apply directly to the petitioner's facts.\n"
            "The dispute arises out of a commercial transaction.\n\n"
            "## Strategy\n"
            "The defense strategy is to file a Section 498 petition immediately.\n\n"
            "## Litigation Roadmap\n"
            "1. File bail application. 2. Seek interim relief.\n\n"
            "## Recommendations\n"
            "We recommend moving the High Court.\n\n"
            "## Prospects of Success\n"
            "Chances are high.\n\n"
            "## Probability Assessment\n"
            "Estimated 80% likelihood.\n\n"
            "### 8. ### APPENDIX: RESEARCH SCOPE & UNLOCATED AUTHORITIES\n"
            "All primary authorities analyzed.\n"
        )
        cleaned = enforce_judgment_first_boundaries(memo, allow_strategy=False)

        # Prohibited sections must NOT be in cleaned memo
        self.assertNotIn("## Legal Opinion", cleaned)
        self.assertNotIn("## Strategy", cleaned)
        self.assertNotIn("## Litigation Roadmap", cleaned)
        self.assertNotIn("## Recommendations", cleaned)
        self.assertNotIn("## Prospects of Success", cleaned)
        self.assertNotIn("## Probability Assessment", cleaned)
        self.assertNotIn("APPENDIX", cleaned)

        # Required 4 sections must remain intact
        self.assertIn("## Legal Issue", cleaned)
        self.assertIn("## Relevant Provisions", cleaned)
        self.assertIn("## Judicial Authorities", cleaned)
        self.assertIn("## Application to Query", cleaned)
        self.assertIn("The dispute arises out of a commercial transaction.", cleaned)

        # Output must end after Application to Query
        lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
        last_line = lines[-1]
        self.assertEqual(last_line, "The dispute arises out of a commercial transaction.")

    def test_enforce_judgment_first_boundaries_explicit_strategy(self):
        """Verifies strategy and roadmap sections are preserved when explicitly requested."""
        memo = (
            "## Legal Issue\n"
            "Whether Section 498 CrPC applies.\n\n"
            "## Relevant Provisions\n"
            "- CrPC — Section 498: Pre-arrest bail\n\n"
            "## Judicial Authorities\n"
            "### Tariq Mahmood v. State — 2024 SCMR 500\n"
            "- Court: Supreme Court of Pakistan\n"
            "- Relevant facts: Commercial loan default.\n"
            "- Court held: Pre-arrest bail confirmed.\n"
            "- Ratio decidendi: Civil dispute does not warrant arrest.\n\n"
            "## Application to Query\n"
            "The petitioner's transaction is commercial.\n\n"
            "## Strategy & Litigation Roadmap\n"
            "Move pre-arrest bail petition before the Sessions Court first.\n"
        )
        cleaned = enforce_judgment_first_boundaries(memo, allow_strategy=True)
        self.assertIn("## Strategy & Litigation Roadmap", cleaned)
        self.assertIn("Move pre-arrest bail petition", cleaned)

    def test_query_requests_strategy(self):
        """Verifies accurate detection of explicit strategy requests."""
        # Non-strategy queries (default)
        self.assertFalse(query_requests_strategy("What are the requirements for pre-arrest bail under Section 498 CrPC?"))
        self.assertFalse(query_requests_strategy("Explain the distinction between Section 409 and Section 420 PPC."))
        self.assertFalse(query_requests_strategy("Can a landlord evict a tenant under Punjab Rented Premises Act without notice?"))

        # Explicit strategy queries
        self.assertTrue(query_requests_strategy("What is the litigation strategy for defending a Section 409 PPC FIR?"))
        self.assertTrue(query_requests_strategy("Provide a strategic roadmap and recommendations for interim injunction."))
        self.assertTrue(query_requests_strategy("What are the prospects of success for this quashment petition?"))
        self.assertTrue(query_requests_strategy("Please provide a probability assessment and recommendations."))

    def test_enforce_holding_attribution(self):
        """Verifies 'Court held' is retained for full judgments and converted to 'The judgment record indicates' for headnotes."""
        memo = (
            "## Judicial Authorities\n\n"
            "### Tariq Mahmood v. State — 2024 SCMR 500\n"
            "- **Court**: Supreme Court of Pakistan\n"
            "- **Relevant facts**: Commercial loan dispute.\n"
            "- **Court held**: Pre-arrest bail is confirmed on grounds of commercial civil transaction.\n"
            "- **Ratio decidendi**: Mere default is civil dispute.\n\n"
            "### Ahmad v. Federation — 2018 CLC 120\n"
            "- **Court**: Lahore High Court\n"
            "- **Relevant facts**: Declaratory suit.\n"
            "- **Court held**: Declaratory decree barred without possession prayer.\n"
            "- **Ratio decidendi**: Section 42 Specific Relief Act.\n\n"
            "## Application to Query\n"
            "Under 2024 SCMR 500, the Court held that the civil remedy applies.\n"
            "Regarding 2018 CLC 120, the Court held that possession must be claimed."
        )

        cards = [
            {
                "citation": "2024 SCMR 500",
                "verification_status": "FULL_TEXT_CHECKED",
                "content_type": "full_text",
                "has_identifiable_holding": True
            },
            {
                "citation": "2018 CLC 120",
                "verification_status": "HEADNOTE_ONLY",
                "content_type": "headnote_only",
                "has_identifiable_holding": False
            }
        ]

        cleaned = enforce_holding_attribution(memo, cards)

        # 2024 SCMR 500 (full judgment with holding) MUST retain "Court held"
        self.assertIn("- **Court held**: Pre-arrest bail is confirmed on grounds of commercial civil transaction.", cleaned)
        self.assertIn("Under 2024 SCMR 500, the Court held that the civil remedy applies.", cleaned)

        # 2018 CLC 120 (headnote only) MUST be labeled "The judgment record indicates"
        self.assertNotIn("- **Court held**: Declaratory decree barred", cleaned)
        self.assertIn("- **The judgment record indicates**: Declaratory decree barred without possession prayer.", cleaned)
        self.assertIn("Regarding 2018 CLC 120, the judgment record indicates that possession must be claimed.", cleaned)

    def test_is_headnote_only_card(self):
        """Verifies identification of headnotes vs full judgments."""
        full_card = {"verification_status": "FULL_TEXT_CHECKED", "has_identifiable_holding": True}
        headnote_card1 = {"verification_status": "HEADNOTE_ONLY"}
        headnote_card2 = {"content_type": "editorial_summary"}
        headnote_card3 = {"has_identifiable_holding": False}

        self.assertFalse(is_headnote_only_card(full_card))
        self.assertTrue(is_headnote_only_card(headnote_card1))
        self.assertTrue(is_headnote_only_card(headnote_card2))
    def test_deterministic_removal_of_prohibited_headings(self):
        """Verifies deterministic removal of Senior Counsel Opinion, Executive Summary & Legal Opinion,
        Procedural Remedy & Appellate Strategy, Recommendations, Litigation Roadmap, and For an Advocate."""
        memo = (
            "### 1. ### Executive Summary & Legal Opinion\n"
            "Unauthorized executive summary and legal opinion that must be removed.\n\n"
            "## Legal Issue\n"
            "Whether commercial default under PRPA 2009 allows immediate eviction.\n\n"
            "## Relevant Provisions\n"
            "- PRPA 2009 — Section 15: Eviction grounds\n\n"
            "## Judicial Authorities\n"
            "### Muhammad Zaman v. Akram Hussain — 2011 CLC 755\n"
            "- Court: Lahore High Court\n"
            "- Court held: Exclusive jurisdiction lies with the Rent Tribunal.\n"
            "- Ratio decidendi: Civil court jurisdiction is barred.\n\n"
            "## Application of Law to Facts\n"
            "The commercial premises are subject to PRPA. The landlord cannot approach a civil court.\n\n"
            "### Senior Counsel Opinion\n"
            "In our senior counsel assessment, eviction is certain.\n\n"
            "### Procedural Remedy & Appellate Strategy\n"
            "File an ejectment application before the Special Judge Rent.\n\n"
            "### Recommendations\n"
            "Serve thirty days notice before filing.\n\n"
            "### Litigation Roadmap\n"
            "Step 1: Notice. Step 2: Petition. Step 3: Execution.\n\n"
            "### For an Advocate\n"
            "Check that tenancy agreement is registered under Section 5.\n\n"
            "**Senior Counsel Opinion**\n"
            "Alternate bold senior counsel opinion.\n\n"
            "**Recommendations & Litigation Roadmap**\n"
            "Alternate bold recommendations.\n\n"
            "**For an Advocate**\n"
            "Alternate bold instructions for advocate.\n"
        )

        cleaned = enforce_judgment_first_boundaries(memo, allow_strategy=False)

        # All 6 requested headings and bold variants must be deterministically removed
        self.assertNotIn("Executive Summary & Legal Opinion", cleaned)
        self.assertNotIn("Senior Counsel Opinion", cleaned)
        self.assertNotIn("Procedural Remedy & Appellate Strategy", cleaned)
        self.assertNotIn("Recommendations", cleaned)
        self.assertNotIn("Litigation Roadmap", cleaned)
        self.assertNotIn("For an Advocate", cleaned)

        # Core judgment-first sections must remain
        self.assertIn("## Legal Issue", cleaned)
        self.assertIn("## Relevant Provisions", cleaned)
        self.assertIn("## Judicial Authorities", cleaned)
        self.assertIn("## Application of Law to Facts", cleaned)
        self.assertIn("The landlord cannot approach a civil court.", cleaned)

        # Output must terminate immediately after Application of Law to Facts
        lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
        self.assertEqual(lines[-1], "The commercial premises are subject to PRPA. The landlord cannot approach a civil court.")

    def test_verification_task_terminates_after_verification_section(self):
        """Verifies that verification tasks terminate immediately after the requested verification/application section."""
        memo = (
            "### Legal Question\n"
            "Verification of Section 28 Limitation Act status.\n\n"
            "### Statutory Verification\n"
            "Section 28 was declared repugnant to Islam in 1991 SCMR 2063 with effect from 31 August 1991.\n"
            "The statutory provision ceased to have effect from that date.\n\n"
            "### Procedural Remedy & Appellate Strategy\n"
            "Argue adverse possession matured prior to August 1991 as a past and closed transaction.\n\n"
            "### Recommendations & Litigation Roadmap\n"
            "1. Procure certified copies. 2. File revision under Section 115 CPC.\n\n"
            "### For an Advocate\n"
            "Examine revenue records for entries before 1991.\n"
        )

        cleaned = enforce_judgment_first_boundaries(memo, allow_strategy=False)

        self.assertIn("### Legal Question", cleaned)
        self.assertIn("### Statutory Verification", cleaned)
        self.assertIn("The statutory provision ceased to have effect from that date.", cleaned)

        # Prohibited trailing sections must NOT be in cleaned text
        self.assertNotIn("Procedural Remedy & Appellate Strategy", cleaned)
        self.assertNotIn("Recommendations & Litigation Roadmap", cleaned)
        self.assertNotIn("For an Advocate", cleaned)

        # Must terminate exactly at the end of the Statutory Verification section
        lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
        self.assertEqual(lines[-1], "The statutory provision ceased to have effect from that date.")

    def test_classify_precedent_authority_level_prpa(self):
        """Verifies 3-tier classification: direct vs analogical vs background authority."""
        query_text = (
            "A tenant files a civil suit for declaration of tenancy rights and challenges an eviction notice. "
            "The landlord argues exclusive jurisdiction under the Punjab Rented Premises Act 2009."
        )

        # 1. Analogical authority: Land Revenue Act s.172 (Abdullah v. Waryam)
        card_lra = {
            "citation": "2026 SCMR 1042",
            "case_name": "Abdullah v. Waryam",
            "court": "Supreme Court of Pakistan",
            "sections": ["Section 172 Land Revenue Act", "Section 9 CPC"],
            "preview": "Exclusion of civil court jurisdiction under Section 172 Land Revenue Act does not bar suit where mutation was fraudulent.",
        }
        level_lra = classify_precedent_authority_level(card_lra, query_text=query_text)
        self.assertEqual(level_lra, "Analogical Authority")

        # 2. Analogical authority: Out-of-province Sindh rent case under SRPO 1979 (Dr. Shakeel Qureshi)
        card_srpo = {
            "citation": "2007 YLR 2064",
            "case_name": "Dr. Shakeel Qureshi v. Rent Controller",
            "court": "High Court of Sindh",
            "sections": ["Sindh Rented Premises Ordinance 1979", "Section 15"],
            "preview": "Rent Controller has exclusive jurisdiction to order eviction under SRPO 1979.",
        }
        level_srpo = classify_precedent_authority_level(card_srpo, query_text=query_text)
        self.assertEqual(level_srpo, "Analogical Authority")

        # 3. Direct authority: Punjab Rented Premises Act 2009 / Rent Tribunal
        card_prpa = {
            "citation": "2023 SCMR 800",
            "case_name": "Muhammad Aslam v. Rent Tribunal Lahore",
            "court": "Supreme Court of Pakistan",
            "sections": ["Punjab Rented Premises Act 2009", "Section 35"],
            "preview": "Section 35 of the Punjab Rented Premises Act 2009 explicitly excludes civil court jurisdiction in rent matters.",
        }
        level_prpa = classify_precedent_authority_level(card_prpa, query_text=query_text)
        self.assertEqual(level_prpa, "Direct Authority")

        # 4. Background authority: General Section 9 CPC plenary doctrine
        card_cpc = {
            "citation": "2015 SCMR 1200",
            "case_name": "Federation of Pakistan v. Province",
            "court": "Supreme Court of Pakistan",
            "sections": ["Section 9 CPC"],
            "preview": "Civil court has plenary jurisdiction to try all civil suits unless expressly or impliedly barred.",
        }
        level_cpc = classify_precedent_authority_level(card_cpc, query_text=query_text)
        self.assertEqual(level_cpc, "Background Authority")

    def test_filter_and_cap_authorities(self):
        """Verifies filtering out peripheral cross-provincial cases and capping at 2-5 authorities."""
        query_text = "Punjab Rented Premises Act 2009 Rent Tribunal eviction Section 9 CPC"

        pool = [
            {"citation": "2023 SCMR 800", "case_name": "PRPA Case 1", "court": "Supreme Court of Pakistan", "preview": "Punjab Rented Premises Act 2009 s.35"},
            {"citation": "2022 SCMR 500", "case_name": "PRPA Case 2", "court": "Supreme Court of Pakistan", "preview": "Punjab Rented Premises Act 2009 Rent Tribunal"},
            {"citation": "2021 CLC 100", "case_name": "PRPA Case 3", "court": "Lahore High Court", "preview": "PRPA 2009 eviction notice"},
            {"citation": "2026 SCMR 1042", "case_name": "Abdullah v. Waryam", "court": "Supreme Court of Pakistan", "preview": "Land Revenue Act s.172"},
            {"citation": "2007 YLR 2064", "case_name": "Dr. Shakeel Qureshi", "court": "High Court of Sindh", "preview": "SRPO 1979 Sindh rent eviction"},
            {"citation": "2018 SCMR 300", "case_name": "General CPC Case", "court": "Supreme Court of Pakistan", "preview": "Section 9 CPC jurisdiction of civil court"},
            {"citation": "2019 MLD 400", "case_name": "Extra Case", "court": "Lahore High Court", "preview": "Civil procedure"},
        ]

        capped = filter_and_cap_authorities(pool, query_text=query_text, min_k=2, max_k=5)
        # Must cap at max 5
        self.assertLessEqual(len(capped), 5)
        self.assertGreaterEqual(len(capped), 2)

        # Out-of-province High Court case under SRPO 1979 must be filtered out
        citations = [c["citation"] for c in capped]
        self.assertNotIn("2007 YLR 2064", citations)

        # Top cases must be Direct Authorities
        self.assertEqual(capped[0]["authority_level"], "Direct Authority")

    def test_missing_statutory_source_warning(self):
        """Verifies automatic insertion of warning when statutory text is unretrieved."""
        query_text = "Punjab Rented Premises Act 2009 eviction notice"
        is_missing, act_name = check_missing_statutory_source(query_text=query_text)
        self.assertTrue(is_missing)
        self.assertEqual(act_name, "Punjab Rented Premises Act, 2009")

        memo = (
            "## Legal Issue\n"
            "Whether civil court has jurisdiction under PRPA 2009.\n\n"
            "## Relevant Provisions\n"
            "- Punjab Rented Premises Act 2009 — Section 35: Exclusion of civil courts\n\n"
            "## Application to Query\n"
            "The civil court lacks jurisdiction.\n"
        )
        cleaned = enforce_missing_statutory_source_warning(memo, is_missing=True, statute_name=act_name)
        self.assertIn("> Statutory text unavailable in retrieved sources. The analysis is based only on judicial references.", cleaned)

    def test_enforce_proposition_confidence_guardrails(self):
        """Verifies elimination of broad overstatements on civil court tenancy jurisdiction."""
        memo = (
            "## Application to Query\n"
            "The civil court retains jurisdiction for declaration of tenancy rights under Section 9 CPC. "
            "Therefore, the tenant's suit is maintainable."
        )
        cleaned = enforce_proposition_confidence_guardrails(memo, query_text="Punjab Rented Premises Act 2009 tenancy")
        self.assertNotIn("retains jurisdiction for declaration of tenancy rights", cleaned)
        self.assertIn("Where the challenge concerns illegality, lack of jurisdiction, or action beyond statutory authority", cleaned)
        self.assertIn("special Rent Tribunal under the Punjab Rented Premises Act 2009", cleaned)

    def test_runtime_diagnostic_logging(self):
        """Verifies log_runtime_diagnostic produces output without error."""
        import io
        import sys
        buf = io.StringIO()
        old_stderr = sys.stderr
        try:
            sys.stderr = buf
            log_runtime_diagnostic("RAW_SYNTHESIS_OUTPUT", "## Legal Issue\nWhether civil court has jurisdiction.\n\n## Relevant Provisions\n- PRPA 2009")
            output = buf.getvalue()
            self.assertIn("[RUNTIME LOG] RAW_SYNTHESIS_OUTPUT:", output)
            self.assertIn("## Legal Issue", output)
        finally:
            sys.stderr = old_stderr


if __name__ == "__main__":
    unittest.main()

