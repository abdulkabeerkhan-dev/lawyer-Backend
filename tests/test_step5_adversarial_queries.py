"""
tests/test_step5_adversarial_queries.py
Phase 2 Step 5 Acceptance Gate: Verification of Keyword Contamination Elimination.

Tests 10 adversarial queries specifically engineered to provoke cross-domain false matches:
1. Word: 'unpaid' in Family Law (unpaid dower) -> Must route to family, zero 489-F PPC / CrPC
2. Word: 'unpaid' in Rent (unpaid rent default) -> Must route to rent, zero 489-F PPC / SRA 12
3. Word: 'unpaid' in Service (unpaid pension arrears) -> Must route to service, zero 489-F PPC / SRA 12
4. Word: 'fraud' in Land context (fraudulent mutation) -> Must route to civil land revenue, zero PPC 420 / SRA 12
5. Word: 'fraud' in Corporate context (directors siphoning assets) -> Must route to corporate, zero petty PPC 420 / SRA 12
6. Word: 'fraud' in Criminal context (penal cheating / inducement) -> Must route to criminal, zero SRA 12 / CPC 12(2)
7. Word: 'recovery' in Rent context (recovery of possession) -> Must route to rent, zero SRA 12 / Limitation money articles
8. Word: 'recovery' in Banking context (recovery of finance facility) -> Must route to banking, zero SRA 12 / Limitation money articles
9. Word: 'recovery' in Criminal context (recovery of stolen property) -> Must route to criminal, zero banking / Limitation money articles
10. Word: 'arrest' in Civil Execution (arrest of judgment debtor) -> Must route to civil execution, zero CrPC 497/498 bail
"""

import os
import pytest

os.environ["SKIP_TURSO_DRIFT_CHECK"] = "1"

from core.legal_query_planner import create_deterministic_fallback_plan
from core.legal_issue_extractor import extract_legal_issues_from_fact_pattern


def test_adversarial_1_unpaid_dower():
    """Adversarial Query 1: 'unpaid' in Family Law must never trigger cheque dishonour or criminal procedure."""
    query = "Wife filed suit for dissolution of marriage and unpaid dower of Rs. 10 lakh against husband who has not paid since 2 years."
    plan = create_deterministic_fallback_plan(query)

    assert plan.primary_domain == "family"
    assert "Family Court" in plan.competent_forum
    assert any("FAMILY_COURTS_1964" in p for p in plan.statutory_provisions) or any("MFLO_1961" in p for p in plan.statutory_provisions)

    # Invariants: Zero criminal / cheque / specific performance provisions
    assert not any("489" in p for p in plan.statutory_provisions)
    assert not any("PPC" in p for p in plan.statutory_provisions)
    assert not any("CRPC" in p for p in plan.statutory_provisions)
    assert not any("SRA_1877_SEC_12" in p for p in plan.statutory_provisions)


def test_adversarial_2_unpaid_rent():
    """Adversarial Query 2: 'unpaid' in Rent must never trigger cheque dishonour or SRA 12."""
    query = "Tenant has not paid rent for 6 months; landlord filed eviction application for default in payment of unpaid rent in Lahore."
    plan = create_deterministic_fallback_plan(query)

    assert plan.primary_domain == "rent"
    assert "Rent" in plan.competent_forum
    assert any("PRPA_2009" in p for p in plan.statutory_provisions)

    # Invariants: Zero cheque dishonour or civil specific performance
    assert not any("489" in p for p in plan.statutory_provisions)
    assert not any("PPC" in p for p in plan.statutory_provisions)
    assert not any("CRPC" in p for p in plan.statutory_provisions)
    assert not any("SRA_1877_SEC_12" in p for p in plan.statutory_provisions)


def test_adversarial_3_unpaid_pension():
    """Adversarial Query 3: 'unpaid' in Service must never trigger cheque dishonour or SRA 12."""
    query = "Retired civil servant claims unpaid pension arrears and gratuity withheld by department without lawful authority."
    plan = create_deterministic_fallback_plan(query)

    assert plan.primary_domain in ("service", "constitutional")
    assert "Service Tribunal" in plan.competent_forum or "High Court" in plan.competent_forum

    # Invariants
    assert not any("489" in p for p in plan.statutory_provisions)
    assert not any("PPC" in p for p in plan.statutory_provisions)
    assert not any("SRA_1877_SEC_12" in p for p in plan.statutory_provisions)


def test_adversarial_4_fraudulent_mutation():
    """Adversarial Query 4: 'fraud' in Land context must route to Land Revenue, never petty PPC 420 or SRA 12."""
    query = "Brother fraudulently sanctioned mutation (intiqal) of agricultural land behind sister's back through revenue patwari."
    plan = create_deterministic_fallback_plan(query)

    assert plan.primary_domain == "civil"
    assert "Revenue" in plan.competent_forum or "Civil Court" in plan.competent_forum
    assert any("LAND_REVENUE_1967" in p for p in plan.statutory_provisions)

    # Invariants: Zero criminal PPC 420 and zero SRA 12 specific performance
    assert not any("PPC_1860_SEC_420" in p for p in plan.statutory_provisions)
    assert not any("SRA_1877_SEC_12" in p for p in plan.statutory_provisions)
    assert not any("CRPC" in p for p in plan.statutory_provisions)


def test_adversarial_5_corporate_fraud():
    """Adversarial Query 5: 'fraud' in Corporate context must route to Companies Act, never petty cheating or SRA 12."""
    query = "Majority directors committed fraud by siphoning company assets and issuing shares to themselves without AGM approval."
    plan = create_deterministic_fallback_plan(query)

    assert plan.primary_domain == "corporate"
    assert "Company Bench" in plan.competent_forum or "Special Court" in plan.competent_forum
    assert any("COMPANIES_2017_SEC_286" in p for p in plan.statutory_provisions)

    # Invariants: Zero petty cheating PPC 420 and zero SRA 12 specific performance
    assert not any("PPC_1860_SEC_420" in p for p in plan.statutory_provisions)
    assert not any("SRA_1877_SEC_12" in p for p in plan.statutory_provisions)


def test_adversarial_6_penal_cheating_fraud():
    """Adversarial Query 6: Uncontextualized penal fraud must route to PPC 420, never SRA 12 or CPC 12(2)."""
    query = "Accused fraudulently induced complainant to pay Rs. 5 million promising imported solar panels and absconded."
    plan = create_deterministic_fallback_plan(query)

    assert plan.primary_domain == "criminal"
    assert any("PPC_1860_SEC_420" in p for p in plan.statutory_provisions) or any("PPC_1860_SEC_415" in p for p in plan.statutory_provisions)

    # Invariants: Zero civil specific performance SRA 12 and zero CPC 12(2) decree challenge
    assert not any("SRA_1877_SEC_12" in p for p in plan.statutory_provisions)
    assert not any("12(2)" in p for p in plan.statutory_provisions)
    assert not any("CPC_1908_SEC_12" in p for p in plan.statutory_provisions)


def test_adversarial_7_rent_recovery_possession():
    """Adversarial Query 7: 'recovery of possession' from tenant must route to rent, never banking or SRA 12."""
    query = "Landlord seeks recovery of possession and ejectment of tenant after expiry of tenancy lease agreement in Rawalpindi."
    plan = create_deterministic_fallback_plan(query)

    assert plan.primary_domain == "rent"
    assert "Rent" in plan.competent_forum
    assert any("PRPA_2009" in p for p in plan.statutory_provisions)

    # Invariants: Zero SRA 12, zero FIO banking, zero Limitation money recovery articles
    assert not any("SRA_1877_SEC_12" in p for p in plan.statutory_provisions)
    assert not any("FIO_2001" in p for p in plan.statutory_provisions)
    assert not any("LIMITATION_1908_ART_57" in p for p in plan.statutory_provisions)


def test_adversarial_8_banking_recovery_loan():
    """Adversarial Query 8: 'recovery of finance' must route to banking FIO 2001, never rent or SRA 12."""
    query = "Commercial bank filed suit for recovery of finance facility of Rs. 40 million against defaulting borrower company."
    plan = create_deterministic_fallback_plan(query)

    assert plan.primary_domain == "banking"
    assert "Banking Court" in plan.competent_forum
    assert any("FIO_2001_SEC_9" in p for p in plan.statutory_provisions)

    # Invariants: Zero SRA 12, zero PRPA rent, zero general Limitation money articles
    assert not any("SRA_1877_SEC_12" in p for p in plan.statutory_provisions)
    assert not any("PRPA_2009" in p for p in plan.statutory_provisions)
    assert not any("LIMITATION_1908_ART_57" in p for p in plan.statutory_provisions)


def test_adversarial_9_criminal_recovery_stolen_property():
    """Adversarial Query 9: 'recovery of stolen property' must route to criminal PPC/CrPC, never civil money recovery."""
    query = "Police effected recovery of stolen vehicle and cash from accused during criminal investigation under FIR."
    plan = create_deterministic_fallback_plan(query)

    assert plan.primary_domain == "criminal"
    assert any("PPC_1860_SEC_379" in p for p in plan.statutory_provisions) or any("PPC_1860_SEC_411" in p for p in plan.statutory_provisions)
    assert any("CRPC_1898_SEC_103" in p for p in plan.statutory_provisions) or any("CRPC_1898_SEC_154" in p for p in plan.statutory_provisions)

    # Invariants: Zero Limitation money recovery articles, zero banking FIO, zero SRA 12
    assert not any("LIMITATION_1908_ART_57" in p for p in plan.statutory_provisions)
    assert not any("FIO_2001" in p for p in plan.statutory_provisions)
    assert not any("SRA_1877_SEC_12" in p for p in plan.statutory_provisions)


def test_adversarial_10_civil_execution_arrest_debtor():
    """Adversarial Query 10: 'arrest of judgment debtor' in civil execution must route to CPC 55, never CrPC bail."""
    query = "Executing court issued warrant of arrest against judgment debtor under Section 55 CPC for non-satisfaction of money decree."
    plan = create_deterministic_fallback_plan(query)

    assert plan.primary_domain == "civil"
    assert "Executing Court" in plan.competent_forum or "Civil Court" in plan.competent_forum
    assert any("CPC_1908_SEC_55" in p for p in plan.statutory_provisions)
    assert any("CPC_1908_ORD_XXI" in p for p in plan.statutory_provisions) or any("CPC_1908_SEC_51" in p for p in plan.statutory_provisions)

    # Invariants: Zero CrPC 497/498 criminal bail, zero criminal procedure
    assert not any("CRPC_1898_SEC_497" in p for p in plan.statutory_provisions)
    assert not any("CRPC_1898_SEC_498" in p for p in plan.statutory_provisions)
    assert not any("CRPC_1898_SEC_496" in p for p in plan.statutory_provisions)
    assert "Bail" not in plan.procedural_remedy
