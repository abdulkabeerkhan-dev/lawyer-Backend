"""
tests/test_step4_deterministic_branches.py

Phase 2 Step 4 Acceptance Gate Test Suite:
Validates deterministic decomposition branches across 10 Priority Domains:
1. Family Law (5 golden tests)
2. Rent & Eviction (5 golden tests)
3. Banking Recovery (5 golden tests)
4. Criminal beyond murder (5 golden tests)
5. Constitutional Writs (5 golden tests)
6. FIR Quashment & Abuse of Process (5 golden tests)
7. Service Tribunal & Civil Servants (5 golden tests)
8. Land & Property Revenue (5 golden tests)
9. IP & Cybercrime (5 golden tests)
10. Family Property & Inheritance (5 golden tests)

Total: 50 golden tests.
Every test asserts:
- Correct primary domain
- Canonical ID format (^([A-Z0-9_]+_(?:SEC|ART|ORD|RULE)_[0-9A-Z_()]+)$)
- 100% existence of returned IDs in UnifiedStatuteStore (data/statutes_v2)
- Expected domain controlling provisions present
- Zero cross-domain contamination (no SRA 12 in rent/banking/service, no 489-F in family/rent)
"""

import os
import sys
import re
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.legal_query_planner import create_deterministic_fallback_plan
from core.legal_issue_extractor import extract_legal_issues_from_fact_pattern
from core.unified_statute_store import get_unified_statute_store

os.environ["SKIP_TURSO_DRIFT_CHECK"] = "1"
CANONICAL_ID_REGEX = re.compile(r'^[A-Z0-9_]+_(?:SEC|ART|ORD|RULE)_[0-9A-Z_()]+$')


def _verify_gate_plan(query: str, expected_domain: str, required_cids: list, forbidden_tokens: list):
    store = get_unified_statute_store()
    plan = create_deterministic_fallback_plan(query)
    decomp = extract_legal_issues_from_fact_pattern(query, planner_domain=plan.primary_domain)

    # 1. Primary domain check
    assert decomp.primary_domain == expected_domain, f"Decomp domain '{decomp.primary_domain}' != '{expected_domain}'"

    # 2. Gather provisions
    all_controlling = []
    for iss in decomp.issues:
        for prov in iss.controlling_provisions:
            all_controlling.append(prov)
    all_provisions = list(dict.fromkeys(all_controlling + plan.statutory_provisions))

    assert len(all_provisions) > 0, f"No provisions returned for query: {query}"

    # 3. Canonical ID format and Store Existence
    for cid in all_provisions:
        assert CANONICAL_ID_REGEX.match(cid), f"Invalid canonical ID format: '{cid}'"
        rec = store.get_by_canonical_id(cid)
        assert rec is not None, f"Canonical ID '{cid}' does not exist in UnifiedStatuteStore!"

    # 4. Required provisions check
    for req in required_cids:
        assert req in all_provisions, f"Required provision '{req}' missing from returned provisions: {all_provisions}"

    # 5. Forbidden contamination check
    for cid in all_provisions:
        cid_low = cid.lower()
        for bad in forbidden_tokens:
            assert bad.lower() not in cid_low, f"Forbidden contamination '{bad}' found in provision: {cid}"

    return plan, decomp


# =============================================================================
# 1. FAMILY LAW GOLDEN TESTS (5 Tests)
# =============================================================================

def test_family_1_khula_and_dower():
    q = "Wife seeking dissolution of marriage through Khula on ground of desertion and recovery of unpaid prompt dower of Rs. 1,000,000."
    _verify_gate_plan(q, "family", ["FAMILY_COURTS_1964_SEC_10", "FAMILY_COURTS_1964_SEC_5", "DMMA_1939_SEC_2", "MFLO_1961_SEC_10"], ["489F", "CRPC", "SRA"])

def test_family_2_child_maintenance_interim():
    q = "Husband refused maintenance to mother and three school going minor children. Filing suit for past and future maintenance with interim maintenance under Section 17A Family Courts Act."
    _verify_gate_plan(q, "family", ["MFLO_1961_SEC_9", "FAMILY_COURTS_1964_SEC_17A", "FAMILY_COURTS_1964_SEC_5"], ["489F", "CRPC", "SRA"])

def test_family_3_custody_hizanat_minors():
    q = "Mother seeking custody (Hizanat) of 5 year old minor daughter from father under Guardians and Wards Act where welfare of minor is paramount consideration."
    _verify_gate_plan(q, "family", ["GWA_1890_SEC_17", "GWA_1890_SEC_25", "FAMILY_COURTS_1964_SEC_5"], ["489F", "CRPC", "SRA"])

def test_family_4_talaq_notice_arbitration():
    q = "Husband pronounced verbal talaq without serving notice of talaq to Chairman Union Council under Section 7 Muslim Family Laws Ordinance 1961."
    _verify_gate_plan(q, "family", ["MFLO_1961_SEC_7", "FAMILY_COURTS_1964_SEC_5"], ["489F", "CRPC", "SRA"])

def test_family_5_family_court_appeal():
    q = "Filing appeal before District Judge against final judgment and decree of Family Court granting dower and maintenance under Section 14 Family Courts Act 1964."
    _verify_gate_plan(q, "family", ["FAMILY_COURTS_1964_SEC_14", "FAMILY_COURTS_1964_SEC_5"], ["489F", "CRPC", "SRA"])


# =============================================================================
# 2. RENT & EVICTION GOLDEN TESTS (5 Tests)
# =============================================================================

def test_rent_1_ejectment_default_personal_need():
    q = "Landlord filed ejectment application under Section 15 of Punjab Rented Premises Act 2009 for default in payment of rent and personal bona fide need."
    _verify_gate_plan(q, "rent", ["PRPA_2009_SEC_15", "PRPA_2009_SEC_4"], ["SRA", "PPC", "CRPC"])

def test_rent_2_leave_to_contest_limitation():
    q = "Tenant served with summons from Rent Tribunal seeking leave to contest within mandatory 10 days limitation under Section 22 Punjab Rented Premises Act 2009."
    _verify_gate_plan(q, "rent", ["PRPA_2009_SEC_22", "PRPA_2009_SEC_19", "PRPA_2009_SEC_34"], ["SRA", "PPC", "CRPC"])

def test_rent_3_cash_payment_refused_receipts():
    q = "Tenant paid rent in cash regularly but landlord refused to issue receipts under Section 4 and filed eviction under Section 15 PRPA 2009."
    _verify_gate_plan(q, "rent", ["PRPA_2009_SEC_4", "PRPA_2009_SEC_15"], ["SRA", "PPC", "CRPC"])

def test_rent_4_sindh_rent_ejectment_srpo():
    q = "Landlord filed eviction of commercial shop in Karachi under Section 15 Sindh Rented Premises Ordinance 1979 and tenant ordered to deposit tentative rent under Section 16 SRPO."
    _verify_gate_plan(q, "rent", ["SRPO_1979_SEC_15", "SRPO_1979_SEC_16", "SRPO_1979_SEC_21"], ["SRA", "PPC", "CRPC"])

def test_rent_5_subletting_lease_expiry():
    q = "Application for eviction on grounds of unauthorized subletting and expiry of tenancy agreement under Section 15 Punjab Rented Premises Act 2009."
    _verify_gate_plan(q, "rent", ["PRPA_2009_SEC_15", "PRPA_2009_SEC_22"], ["SRA", "PPC", "CRPC"])


# =============================================================================
# 3. BANKING RECOVERY GOLDEN TESTS (5 Tests)
# =============================================================================

def test_banking_1_recovery_suit_section_9():
    q = "Commercial bank instituted recovery suit against corporate borrower under Section 9 Financial Institutions (Recovery of Finances) Ordinance 2001 for Rs. 50 million finance facility."
    _verify_gate_plan(q, "banking", ["FIO_2001_SEC_9", "FIO_2001_SEC_2", "FIO_2001_SEC_22"], ["SRA", "PPC", "CRPC"])

def test_banking_2_leave_to_defend_30_days():
    q = "Borrower served with Banking Court summons must file leave to defend application supported by affidavit within mandatory 30 days under Section 10 FIO 2001."
    _verify_gate_plan(q, "banking", ["FIO_2001_SEC_10"], ["SRA", "PPC", "CRPC"])

def test_banking_3_compound_markup_penal_charges():
    q = "Challenging illegal compound mark-up and penal interest charged by bank beyond agreed finance agreement under Section 10 and 14 FIO 2001 for unconditional leave to defend."
    _verify_gate_plan(q, "banking", ["FIO_2001_SEC_10", "FIO_2001_SEC_14"], ["SRA", "PPC", "CRPC"])

def test_banking_4_mortgage_sale_without_court():
    q = "Financial institution initiated extra-judicial sale of mortgaged commercial factory under Section 15 of Financial Institutions (Recovery of Finances) Ordinance 2001."
    _verify_gate_plan(q, "banking", ["FIO_2001_SEC_15", "FIO_2001_SEC_9"], ["SRA", "PPC", "CRPC"])

def test_banking_5_high_court_appeal_section_22():
    q = "Statutory appeal before High Court under Section 22 FIO 2001 against final judgment and decree of Banking Court within 30 days limitation."
    _verify_gate_plan(q, "banking", ["FIO_2001_SEC_22", "FIO_2001_SEC_9"], ["SRA", "PPC", "CRPC"])


# =============================================================================
# 4. CRIMINAL BEYOND MURDER GOLDEN TESTS (5 Tests)
# =============================================================================

def test_criminal_1_theft_movable_property():
    q = "Accused implicated in FIR under Sections 378 and 379 PPC alleging theft of industrial machinery from factory premises."
    _verify_gate_plan(q, "criminal", ["PPC_1860_SEC_378", "PPC_1860_SEC_379"], ["SRA", "GWA", "FAMILY_COURTS"])

def test_criminal_2_cheating_dishonest_inducement():
    q = "FIR registered under Sections 415 and 420 PPC alleging cheating and fraudulent inducement to invest Rs. 5 million in bogus scheme."
    _verify_gate_plan(q, "criminal", ["PPC_1860_SEC_415", "PPC_1860_SEC_420"], ["SRA", "GWA", "FAMILY_COURTS"])

def test_criminal_3_criminal_breach_of_trust():
    q = "Director accused in FIR under Sections 405 and 406 PPC alleging criminal breach of trust and dishonest misappropriation of company funds."
    _verify_gate_plan(q, "criminal", ["PPC_1860_SEC_405", "PPC_1860_SEC_406"], ["SRA", "GWA", "FAMILY_COURTS"])

def test_criminal_4_pre_arrest_bail_mala_fide():
    q = "Apprehension of arrest in non-bailable offence due to political malice; seeking pre-arrest bail under Section 498 CrPC and post-arrest bail principles under Section 497 CrPC."
    _verify_gate_plan(q, "criminal", ["CRPC_1898_SEC_498", "CRPC_1898_SEC_497", "CRPC_1898_SEC_496"], ["SRA", "GWA", "FAMILY_COURTS"])

def test_criminal_5_cheque_dishonour_489f_ppc():
    q = "FIR lodged under Section 489-F PPC for dishonoured cheque of Rs. 20 lakh issued for repayment of commercial loan."
    _verify_gate_plan(q, "criminal", ["PPC_1860_SEC_489F", "CPC_1908_ORD_XXXVII_R_1"], ["NIA_1881_SEC_138", "SRA"])


# =============================================================================
# 5. CONSTITUTIONAL WRITS GOLDEN TESTS (5 Tests)
# =============================================================================

def test_const_1_writ_of_certiorari():
    q = "Filing constitutional writ petition for certiorari under Article 199(1)(a)(ii) of Constitution 1973 challenging arbitrary cancellation of public telecom license without lawful authority."
    _verify_gate_plan(q, "constitutional", ["CONST_1973_ART_199", "CONST_1973_ART_4", "CONST_1973_ART_10A"], ["489F", "SRA", "PRPA", "FIO"])

def test_const_2_writ_of_mandamus():
    q = "Constitutional writ of mandamus under Article 199(1)(a)(i) of Constitution 1973 to compel CDA public authority to perform statutory duty of issuing building completion certificate."
    _verify_gate_plan(q, "constitutional", ["CONST_1973_ART_199", "CONST_1973_ART_4"], ["489F", "SRA", "PRPA", "FIO"])

def test_const_3_writ_of_habeas_corpus():
    q = "Writ of habeas corpus under Article 199(1)(b)(i) Constitution 1973 and Section 61 CrPC for recovery and release of citizen held in unlawful detention at police station."
    _verify_gate_plan(q, "constitutional", ["CONST_1973_ART_199", "CONST_1973_ART_9", "CRPC_1898_SEC_61"], ["SRA", "PRPA", "FIO"])

def test_const_4_fair_trial_due_process():
    q = "Challenging administrative penalty imposed without hearing violating right to fair trial and due process under Article 10A and Article 4 in writ petition under Article 199."
    _verify_gate_plan(q, "constitutional", ["CONST_1973_ART_199", "CONST_1973_ART_10A", "CONST_1973_ART_4"], ["489F", "SRA"])

def test_const_5_property_rights_expropriation():
    q = "Constitutional writ petition under Article 199 challenging unlawful expropriation and taking possession of private freehold land without compensation under Article 24 Constitution."
    _verify_gate_plan(q, "constitutional", ["CONST_1973_ART_199", "CONST_1973_ART_24", "CONST_1973_ART_4"], ["489F", "SRA"])


# =============================================================================
# 6. FIR QUASHMENT & ABUSE OF PROCESS GOLDEN TESTS (5 Tests)
# =============================================================================

def test_quashment_1_civil_dispute_criminalized():
    q = "Commercial breach of contract gave rise to malicious FIR under Section 420 and 406 PPC; petition under Section 561-A CrPC for quashment of FIR as abuse of process of the court."
    _verify_gate_plan(q, "criminal", ["CRPC_1898_SEC_561A", "PPC_1860_SEC_406", "PPC_1860_SEC_420"], ["SRA", "FAMILY_COURTS", "PRPA"])

def test_quashment_2_bar_on_second_fir():
    q = "Police registered a second FIR on identical facts after accused was declared innocent in earlier inquiry; seeking quashment of second FIR under Section 154 and 561-A CrPC."
    _verify_gate_plan(q, "criminal", ["CRPC_1898_SEC_561A", "CRPC_1898_SEC_154"], ["SRA", "FAMILY_COURTS"])

def test_quashment_3_writ_quashing_malicious_fir():
    q = "Filing constitutional writ petition under Article 199 and Section 561-A CrPC to quash false criminal proceedings and FIR registered with political malice."
    _verify_gate_plan(q, "criminal", ["CRPC_1898_SEC_561A"], ["SRA", "PRPA", "FIO"])

def test_quashment_4_magistrate_early_acquittal_249a():
    q = "Application before Judicial Magistrate for early acquittal under Section 249-A CrPC on grounds that charge is groundless and no probability of conviction."
    _verify_gate_plan(q, "criminal", ["CRPC_1898_SEC_249A", "CRPC_1898_SEC_561A"], ["SRA", "FAMILY_COURTS"])

def test_quashment_5_sessions_early_acquittal_265k():
    q = "Application before Sessions Court for acquittal at any stage of trial under Section 265-K CrPC as there is no probability of accused being convicted."
    _verify_gate_plan(q, "criminal", ["CRPC_1898_SEC_265K", "CRPC_1898_SEC_561A"], ["SRA", "FAMILY_COURTS"])


# =============================================================================
# 7. SERVICE TRIBUNAL & CIVIL SERVANTS GOLDEN TESTS (5 Tests)
# =============================================================================

def test_service_1_seniority_list_dispute():
    q = "Federal civil servant challenging altered seniority list issued in violation of Section 8 Civil Servants Act 1973 before Federal Service Tribunal under Article 212 Constitution."
    _verify_gate_plan(q, "service", ["CIVIL_SERVANTS_1973_SEC_8", "CONST_1973_ART_212"], ["SRA", "PPC", "CRPC", "CPC_1908_SEC_9"])

def test_service_2_promotion_eligibility():
    q = "Civil servant superseded in promotion despite fulfilling eligibility criteria under Section 9 Civil Servants Act 1973; Service Tribunal appeal under Article 212."
    _verify_gate_plan(q, "service", ["CIVIL_SERVANTS_1973_SEC_9", "CONST_1973_ART_212"], ["SRA", "PPC", "CRPC"])

def test_service_3_article_212_constitutional_bar():
    q = "High Court writ petition dismissed on grounds of constitutional bar under Article 212 Constitution of Pakistan regarding civil servant terms and conditions of service."
    _verify_gate_plan(q, "service", ["CONST_1973_ART_212", "CIVIL_SERVANTS_1973_SEC_4"], ["SRA", "PPC", "CRPC"])

def test_service_4_disciplinary_removal_appeal():
    q = "Civil servant dismissed from service following disciplinary inquiry; filing mandatory departmental appeal before approaching Service Tribunal under Article 212."
    _verify_gate_plan(q, "service", ["CIVIL_SERVANTS_1973_SEC_4", "CONST_1973_ART_212"], ["SRA", "PPC", "CRPC"])

def test_service_5_tenure_and_reversion():
    q = "Civil servant reverted to lower grade in violation of terms and conditions of service and tenure protection under Section 4 Civil Servants Act 1973."
    _verify_gate_plan(q, "service", ["CIVIL_SERVANTS_1973_SEC_4", "CONST_1973_ART_212"], ["SRA", "PPC", "CRPC"])


# =============================================================================
# 8. LAND & PROPERTY REVENUE GOLDEN TESTS (5 Tests)
# =============================================================================

def test_land_1_forged_mutation_challenge():
    q = "Challenge to forged mutation (intiqal) of agricultural land sanctioned by Patwari and Revenue Officer under Section 42 and 52 Land Revenue Act 1967."
    _verify_gate_plan(q, "civil", ["LAND_REVENUE_1967_SEC_42", "LAND_REVENUE_1967_SEC_52"], ["489F", "FAMILY_COURTS", "MFLO"])

def test_land_2_presumption_record_of_rights():
    q = "Evidentiary presumption of truth attached to entries in periodic Record of Rights (Jamabandi) under Section 52 Land Revenue Act 1967 and rebuttal."
    _verify_gate_plan(q, "civil", ["LAND_REVENUE_1967_SEC_52", "LAND_REVENUE_1967_SEC_42"], ["489F", "FAMILY_COURTS"])

def test_land_3_partition_agricultural_holding():
    q = "Application for partition of joint agricultural land holding before Revenue Officer under Section 135 Land Revenue Act 1967."
    _verify_gate_plan(q, "civil", ["LAND_REVENUE_1967_SEC_135", "LAND_REVENUE_1967_SEC_172"], ["489F", "FAMILY_COURTS"])

def test_land_4_revenue_jurisdiction_bar_civil_courts():
    q = "Civil suit challenging revenue partition barred under Section 172 Land Revenue Act 1967 regarding matters within exclusive jurisdiction of Revenue Officer."
    _verify_gate_plan(q, "civil", ["LAND_REVENUE_1967_SEC_172", "LAND_REVENUE_1967_SEC_135"], ["489F", "FAMILY_COURTS"])

def test_land_5_illegal_dispossession_act_2005():
    q = "Lawful owner dispossessed by land grabbers; complaint before Sessions Court for immediate restoration of possession under Section 3, 5, 8 Illegal Dispossession Act 2005."
    _verify_gate_plan(q, "civil", ["ILLEGAL_DISPOSSESSION_2005_SEC_3", "ILLEGAL_DISPOSSESSION_2005_SEC_5", "ILLEGAL_DISPOSSESSION_2005_SEC_8"], ["489F", "FAMILY_COURTS"])


# =============================================================================
# 9. IP & CYBERCRIME GOLDEN TESTS (5 Tests)
# =============================================================================

def test_cyber_1_unauthorized_access_hacking():
    q = "Accused gained unauthorized access to secure corporate information system and copied proprietary data under Section 3 and 10 PECA 2016."
    _verify_gate_plan(q, "cybercrime", ["PECA_2016_SEC_3", "PECA_2016_SEC_10"], ["FAMILY_COURTS", "PRPA", "FIO", "SRA"])

def test_cyber_2_harassment_modesty_stalking():
    q = "Complaint before FIA Cyber Crime Wing for online harassment, cyberstalking, and blackmailing of female victim under Section 21 PECA 2016."
    _verify_gate_plan(q, "cybercrime", ["PECA_2016_SEC_21", "PECA_2016_SEC_16"], ["FAMILY_COURTS", "PRPA", "FIO"])

def test_cyber_3_identity_theft_fake_account():
    q = "Unauthorized use of identity information and creating fake social media account to impersonate complainant under Section 16 PECA 2016."
    _verify_gate_plan(q, "cybercrime", ["PECA_2016_SEC_16", "PECA_2016_SEC_3"], ["FAMILY_COURTS", "PRPA", "FIO"])

def test_ip_4_trademark_infringement_passing_off():
    q = "Counterfeit manufacturer using deceptively similar trademark; suit for trademark infringement and passing off under Section 40 and 46 Trade Marks Ordinance 2001."
    _verify_gate_plan(q, "intellectual_property", ["TRADEMARKS_2001_SEC_40", "TRADEMARKS_2001_SEC_46"], ["FAMILY_COURTS", "PRPA", "FIO"])

def test_ip_5_copyright_infringement_piracy():
    q = "Commercial sale of pirated software in violation of exclusive copyright; suit for copyright infringement and damages under Section 56 and 60 Copyright Ordinance 1962."
    _verify_gate_plan(q, "intellectual_property", ["COPYRIGHT_1962_SEC_56", "COPYRIGHT_1962_SEC_60"], ["FAMILY_COURTS", "PRPA", "FIO"])


# =============================================================================
# 10. FAMILY PROPERTY & INHERITANCE GOLDEN TESTS (5 Tests)
# =============================================================================

def test_inheritance_1_joint_property_partition():
    q = "Legal heirs filing civil suit for partition of joint inherited commercial building under CPC Order XX Rule 18 and Section 2 Partition Act 1893."
    _verify_gate_plan(q, "civil", ["CPC_1908_ORD_XX_R_18", "PARTITION_1893_SEC_2", "PARTITION_1893_SEC_4"], ["489F", "CRPC"])

def test_inheritance_2_shariat_act_shares():
    q = "Distribution of deceased father's estate among legal heirs in accordance with Islamic law under Section 2 and 3 West Pakistan Muslim Personal Law Shariat Application Act 1962."
    _verify_gate_plan(q, "civil", ["SHARIAT_APPLICATION_1962_SEC_2", "SHARIAT_APPLICATION_1962_SEC_3"], ["489F", "CRPC"])

def test_inheritance_3_deprivation_of_sister():
    q = "Brothers refusing sister's share in deceased father's estate; complaint under Section 4 Enforcement of Women's Property Rights Act 2020 and Section 498-A PPC."
    _verify_gate_plan(q, "civil", ["WOMEN_PROPERTY_RIGHTS_2020_SEC_4", "WOMEN_PROPERTY_RIGHTS_2020_SEC_5", "PPC_1860_SEC_498A"], ["489F", "CRPC_1898_SEC_497"])

def test_inheritance_4_dwelling_house_preemption():
    q = "Partition of family dwelling house where family member seeks to buy out external share under Section 4 Partition Act 1893 and Order XX Rule 18 CPC."
    _verify_gate_plan(q, "civil", ["PARTITION_1893_SEC_4", "PARTITION_1893_SEC_2", "CPC_1908_ORD_XX_R_18"], ["489F", "CRPC"])

def test_inheritance_5_benami_property_challenge():
    q = "Legal heirs challenging benami property purchased by deceased father in the name of one son under Section 3 and 4 Benami Transactions (Prohibition) Act 2017."
    _verify_gate_plan(q, "civil", ["BENAMI_2017_SEC_3", "BENAMI_2017_SEC_4"], ["489F", "CRPC"])


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    print(f"Running {len(tests)} Step 4 Golden Tests across 10 Priority Domains...")
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"[PASS] {t.__name__}")
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
    print(f"\nCompleted: {passed}/{len(tests)} PASSED.")
    if passed == len(tests):
        print("ALL 50 STEP 4 GOLDEN TESTS PASSED!")
