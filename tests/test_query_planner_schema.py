"""
tests/test_query_planner_schema.py

Phase 4, Step 1: Unit Test Suite for StructuredLegalQueryPlan & Classification Engine.
Validates:
1. Pydantic StructuredLegalQueryPlan data contract conformance.
2. Legal domain isolation (quarantine of criminal cases in civil property/partition).
3. Legitimate cross-domain authority recognition (e.g. commercial fraud quashment vs contract breach).
4. Statutory provision extraction and canonicalization across Pakistani law.
5. Ambiguity detection and multi-branch clarification.
6. Full backward compatibility with legacy LegalQueryPlan callers.
Covers 27 representative queries across all legal domains.
"""

import pytest
from core.legal_query_planner import (
    StructuredLegalQueryPlan,
    LegalQueryPlan,
    SearchLane,
    PremiseCorrection,
    create_deterministic_fallback_plan
)


# ==============================================================================
# 1. PURE CIVIL PROPERTY & PARTITION (DOMAIN ISOLATION)
# ==============================================================================

def test_civil_partition_preliminary_decree():
    """CIV-PART-001: Order XX Rule 18 CPC partition without hotchpot."""
    q = "Whether a co-sharer in joint ancestral land can seek preliminary decree for partition under Order XX Rule 18 CPC without including the entire joint estate?"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "civil"
    assert "property" in plan.subdomains
    assert "partition" in plan.subdomains
    assert plan.allowed_domains_filter == ["civil"]
    assert plan.is_cross_domain_relevant is False
    assert any("order xx rule 18" in p.lower() for p in plan.statutory_provisions)
    assert any("partition act" in s.lower() for s in plan.governing_statutes)


def test_civil_partition_set_off_premise_correction():
    """CIV-PART-002: Order VIII Rule 6 CPC set-off inapplicability in partition."""
    q = "In a suit for partition of joint family property, can a defendant co-owner plead a money claim as a set-off under Order VIII Rule 6 CPC?"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "civil"
    assert plan.allowed_domains_filter == ["civil"]
    assert plan.is_cross_domain_relevant is False
    # Premise correction must be triggered for Order VIII Rule 6 CPC
    corrections = [pc for pc in plan.premise_corrections if "order viii" in str(pc.get("queried_provision", "")).lower()]
    assert len(corrections) >= 1
    assert corrections[0]["status"] == "LEGALLY_INAPPLICABLE_PREMISE"
    # Search lanes must include set-off inapplicability
    lane_ids = [l["lane"] for l in plan.search_lanes]
    assert "partition_set_off_inapplicability" in lane_ids


def test_civil_partition_local_commission():
    """CIV-PART-003: Appointment of local commission Order XXVI Rule 13 CPC."""
    q = "Procedure for appointment of local commission for partition of immovable commercial property by metes and bounds under Order XXVI Rule 13 CPC"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "civil"
    assert plan.allowed_domains_filter == ["civil"]
    assert any("order xxvi rule 13" in p.lower() for p in plan.statutory_provisions)
    assert "Civil Court / District Judge" in plan.competent_forum


def test_civil_partition_preemption_dwelling_house():
    """CIV-PART-004: Section 4 Partition Act 1893 buy-out of stranger."""
    q = "Right of pre-emption and buy-out valuation by co-sharer under Section 4 Partition Act 1893 when a stranger purchases a share in family dwelling house"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "civil"
    assert plan.allowed_domains_filter == ["civil"]
    assert any("section 4 partition act" in p.lower() for p in plan.statutory_provisions)


# ==============================================================================
# 2. BENAMI TRANSACTIONS (CIVIL PROPERTY CLASSIFICATION)
# ==============================================================================

def test_benami_partition_joint_property():
    """BEN-TRANS-001: Partition involving Benami transactions."""
    q = "Find Pakistani judgments regarding partition of jointly owned property involving Benami transactions."
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "civil"
    assert "benami" in plan.subdomains
    assert "property" in plan.subdomains
    assert plan.allowed_domains_filter == ["civil"]
    assert plan.is_cross_domain_relevant is False
    assert any("benami" in s.lower() for s in plan.governing_statutes)


def test_benami_statutory_bar_section_4():
    """BEN-TRANS-002: Section 4 Benami Transactions (Prohibition) Act 2017."""
    q = "Statutory bar on claiming benami ownership as a defence or suit under Section 4 of Benami Transactions (Prohibition) Act 2017"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "civil"
    assert "benami" in plan.subdomains
    assert plan.allowed_domains_filter == ["civil"]
    assert any("section 4" in p.lower() and "benami" in p.lower() for p in plan.statutory_provisions)
    # Must flag statutory bar correction
    corrections = [pc for pc in plan.premise_corrections if "benami" in str(pc.get("queried_statute", "")).lower()]
    assert len(corrections) >= 1
    assert corrections[0]["status"] == "STATUTORILY_BARRED_DEFENCE"


def test_benami_four_ingredients_pre2017():
    """BEN-TRANS-003: Pre-2017 4 essential ingredients of Benami."""
    q = "Four essential ingredients to prove benami transaction under pre-2017 law consideration possession custody of title deeds and motive"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "civil"
    assert "benami" in plan.subdomains
    assert plan.allowed_domains_filter == ["civil"]


def test_benami_husband_wife_advancement():
    """BEN-TRANS-004: Purchase by husband in name of wife (advancement presumption)."""
    q = "Whether property purchased by husband in name of wife is presumed to be benami or an advancement gift under Pakistani law"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "civil"
    assert "benami" in plan.subdomains
    assert plan.allowed_domains_filter == ["civil"]


# ==============================================================================
# 3. CRIMINAL & COMMERCIAL FRAUD (RELEVANT CROSS-DOMAIN AUTHORITY)
# ==============================================================================

def test_criminal_commercial_contract_fraud_cross_domain():
    """CRIM-FRAUD-001: Pre-arrest bail under 498 CrPC in FIR 406/420 PPC arising out of contract dispute."""
    q = "Pre-arrest bail under Section 498 CrPC in FIR registered under Sections 406 and 420 PPC arising out of commercial contract dispute"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "criminal"
    assert "civil" in plan.secondary_domains
    assert "commercial_fraud" in plan.subdomains
    # CRITICAL: Relevant cross-domain must allow BOTH criminal and civil retrieval
    assert plan.is_cross_domain_relevant is True
    assert "criminal" in plan.allowed_domains_filter
    assert "civil" in plan.allowed_domains_filter
    assert plan.cross_domain_reason is not None
    assert "mens_rea_at_inception" in plan.cross_domain_controlling_doctrines
    assert any("498" in p for p in plan.statutory_provisions)
    assert any("406" in p for p in plan.statutory_provisions)
    assert any("420" in p for p in plan.statutory_provisions)


def test_criminal_breach_of_trust_ingredients():
    """CRIM-FRAUD-002: Sections 405/406 PPC entrustment and dishonest misappropriation."""
    q = "Essential ingredients of criminal breach of trust under Section 405 PPC entrustment of property and dishonest misappropriation"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "criminal"
    assert any("405" in p or "406" in p for p in plan.statutory_provisions)


def test_criminal_quashment_fir_pending_civil_suit():
    """CRIM-FRAUD-003: Quashment of FIR under 561-A CrPC when civil suit is pending."""
    q = "Quashment of FIR under Section 561-A CrPC where civil suit for recovery on same agreement is already pending before civil court"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "criminal"
    assert "civil" in plan.secondary_domains
    assert plan.is_cross_domain_relevant is True
    assert "criminal" in plan.allowed_domains_filter
    assert "civil" in plan.allowed_domains_filter
    assert any("561" in p for p in plan.statutory_provisions)


def test_cheque_dishonour_section_489f_cross_domain():
    """CRIM-FRAUD-004: Cheque dishonour under 489-F PPC vs civil recovery."""
    q = "Dishonour of cheque issued as guarantee or security deposit whether offence under Section 489-F PPC is made out"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "criminal"
    assert "civil" in plan.secondary_domains
    assert plan.is_cross_domain_relevant is True
    assert "criminal" in plan.allowed_domains_filter
    assert "civil" in plan.allowed_domains_filter
    assert any("489-f" in p.lower() for p in plan.statutory_provisions)


# ==============================================================================
# 4. CONSTITUTIONAL & SERVICE LAW
# ==============================================================================

def test_constitutional_service_tribunal_article_212():
    """CONST-LAW-002: Ouster of High Court jurisdiction under Article 212 for civil servants."""
    q = "Ouster of High Court jurisdiction under Article 212 of Constitution in terms and conditions of civil servants Service Tribunal exclusive forum"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "constitutional"
    assert "service" in plan.secondary_domains
    assert plan.is_cross_domain_relevant is True
    assert "constitutional" in plan.allowed_domains_filter
    assert "service" in plan.allowed_domains_filter
    assert plan.employee_status_branching is not None
    assert any("212" in p for p in plan.statutory_provisions)
    assert any("Service Tribunals Act" in s for s in plan.governing_statutes)


def test_constitutional_precedent_article_189_201():
    """CONST-LAW-004: Binding effect of Supreme Court (Art. 189) and High Court (Art. 201)."""
    q = "Binding effect of Supreme Court judgments on all courts in Pakistan under Article 189 and High Court under Article 201"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "constitutional"
    assert any("189" in p for p in plan.statutory_provisions)
    assert any("201" in p for p in plan.statutory_provisions)
    assert plan.allowed_domains_filter == ["constitutional"]


# ==============================================================================
# 5. FAMILY LAW (STRICT DOMAIN ISOLATION)
# ==============================================================================

def test_family_khula_without_husband_consent():
    """FAM-INHER-001: Dissolution of marriage on ground of Khula without husband's consent."""
    q = "Right of Muslim wife to obtain dissolution of marriage on ground of Khula without husband's consent and surrender of dower"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "family"
    assert "khula" in plan.subdomains
    assert plan.allowed_domains_filter == ["family"]
    assert plan.is_cross_domain_relevant is False
    assert any("family courts act" in s.lower() for s in plan.governing_statutes)


def test_family_child_maintenance_father_obligation():
    """FAM-INHER-002: Father's obligation to maintain minor children under s.9 MFLO 1961."""
    q = "Statutory obligation of father to maintain minor children under Section 9 Muslim Family Laws Ordinance 1961 independent of mother's financial status"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "family"
    assert "maintenance" in plan.subdomains
    assert plan.allowed_domains_filter == ["family"]
    assert any("section 9" in p.lower() and "muslim family laws" in p.lower() for p in plan.statutory_provisions)


def test_family_custody_welfare_of_minor():
    """FAM-INHER-003: Custody of minor and welfare test under Guardians and Wards Act 1890."""
    q = "Custody of minor children and paramount consideration of welfare of minor under Section 17 and 25 Guardians and Wards Act 1890"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "family"
    assert "custody" in plan.subdomains
    assert plan.allowed_domains_filter == ["family"]


def test_female_inheritance_fraudulent_relinquishment():
    """FAM-INHER-004: Challenge by female heir to fraudulent relinquishment deed (Tamleek)."""
    q = "Challenge by female legal heir to fraudulent relinquishment deed or Tamleek depriving her of legal shari share in inheritance"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "civil"
    assert "family" in plan.secondary_domains
    assert plan.is_cross_domain_relevant is True
    assert "civil" in plan.allowed_domains_filter
    assert "family" in plan.allowed_domains_filter
    assert "protection_of_female_inheritance" in plan.cross_domain_controlling_doctrines


# ==============================================================================
# 6. RENT RESTRICTION (PRPA 2009 / SRPO)
# ==============================================================================

def test_rent_eviction_leave_to_defend_prpa():
    """MIX-STAT-001: Rent default eviction under PRPA 2009 and Section 22 leave to defend."""
    q = "Eviction of tenant on ground of default in rent under Punjab Rented Premises Act 2009 and mandatory leave to defend under Section 22"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "rent"
    assert "eviction" in plan.subdomains
    assert "rent" in plan.allowed_domains_filter
    assert "criminal" not in plan.allowed_domains_filter
    assert any("section 15" in p.lower() or "section 22" in p.lower() for p in plan.statutory_provisions)
    assert "Special Judge (Rent) / Rent Tribunal" in plan.competent_forum


def test_rent_eviction_with_bounced_cheque_cross_domain():
    """Rent eviction combined with bounced cheque FIR 489-F."""
    q = "Eviction of commercial tenant for non-payment of rent in Lahore and criminal FIR for bounced cheque under Section 489-F PPC"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "rent"
    assert "criminal" in plan.secondary_domains
    assert plan.is_cross_domain_relevant is True
    assert "rent" in plan.allowed_domains_filter
    assert "criminal" in plan.allowed_domains_filter


# ==============================================================================
# 7. BANKING RECOVERY (FIO 2001)
# ==============================================================================

def test_banking_recovery_appeal_deposit_fio():
    """MIX-STAT-002: 30-day limitation and mandatory 50% cash deposit under s.22 FIO 2001."""
    q = "Requirement of 30-day limitation and mandatory 50 percent cash deposit for appeal under Section 22 Financial Institutions Recovery of Finances Ordinance 2001"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "banking"
    assert "banking" in plan.allowed_domains_filter
    assert "criminal" not in plan.allowed_domains_filter
    assert any("section 22" in p.lower() and "financial institutions" in p.lower() for p in plan.statutory_provisions)
    assert "Banking Court" in plan.competent_forum


# ==============================================================================
# 8. CORPORATE OPPRESSION & MANAGEMENT
# ==============================================================================

def test_corporate_oppression_section_286():
    """MIX-STAT-003: Minority shareholder oppression under Section 286 Companies Act 2017."""
    q = "Petition by minority shareholders for prevention of oppression and mismanagement under Section 286 Companies Act 2017 against solvent operational business"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "corporate"
    assert "corporate" in plan.allowed_domains_filter
    assert "criminal" not in plan.allowed_domains_filter
    assert any("section 286" in p.lower() for p in plan.statutory_provisions)


def test_corporate_director_misappropriation_crime_cross_domain():
    """Director misappropriation of corporate funds under Section 409 PPC."""
    q = "Director siphoning company funds and misappropriation of corporate shares under Section 409 PPC and Companies Act 2017"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "corporate"
    assert "criminal" in plan.secondary_domains
    assert plan.is_cross_domain_relevant is True
    assert "corporate" in plan.allowed_domains_filter
    assert "criminal" in plan.allowed_domains_filter


# ==============================================================================
# 9. CIVIL PROCEDURE CODE REMEDIES (SECTION 12(2) & ORDER XXI)
# ==============================================================================

def test_civil_section_12_2_fraud_decree():
    """MIX-STAT-004: Section 12(2) CPC challenge to decree obtained by fraud."""
    q = "Application under Section 12(2) CPC challenging decree obtained through fraud misrepresentation or lack of jurisdiction by a stranger"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "civil"
    assert plan.allowed_domains_filter == ["civil"]
    assert any("12(2)" in p for p in plan.statutory_provisions)


def test_civil_order_xxi_execution_objection():
    """MIX-STAT-005: Objection petition under Order XXI Rules 97-103 CPC."""
    q = "Objection petition under Order XXI Rules 97 to 103 CPC by third party stranger claiming independent right in execution of civil decree"
    plan = create_deterministic_fallback_plan(q)

    assert plan.primary_domain == "civil"
    assert plan.allowed_domains_filter == ["civil"]
    assert any("order xxi rule 97" in p.lower() for p in plan.statutory_provisions)


# ==============================================================================
# 10. AMBIGUITY DETECTION & CLARIFICATION HANDLING
# ==============================================================================

def test_ambiguous_appeal_limitation_query():
    """Ambiguous query: generic limitation period for appeal."""
    q = "What is the limitation period for filing an appeal in Pakistan?"
    plan = create_deterministic_fallback_plan(q)

    assert plan.is_ambiguous is True
    assert len(plan.ambiguity_reasons) >= 1
    assert len(plan.clarification_options) >= 3
    # Allowed domains must NOT be prematurely locked to single domain
    assert "civil" in plan.allowed_domains_filter
    assert "criminal" in plan.allowed_domains_filter
    assert "banking" in plan.allowed_domains_filter


def test_ambiguous_stay_order_query():
    """Ambiguous query: generic stay order request."""
    q = "How can a stay order be obtained in Pakistan?"
    plan = create_deterministic_fallback_plan(q)

    assert plan.is_ambiguous is True
    assert len(plan.ambiguity_reasons) >= 1
    assert any(opt["branch"] == "Civil Suit Temporary Injunction" for opt in plan.clarification_options)


# ==============================================================================
# 11. SCHEMA CONFORMANCE & BACKWARD COMPATIBILITY
# ==============================================================================

def test_backward_compatibility_and_schema_conformance():
    """Verifies that legacy callers expecting LegalQueryPlan dictionary access and attributes succeed."""
    q = "partition of family land among legal heirs in Lahore"
    plan = create_deterministic_fallback_plan(q)

    # 1. Type conformance
    assert isinstance(plan, StructuredLegalQueryPlan)
    assert isinstance(plan, LegalQueryPlan)

    # 2. Legacy attribute access
    assert isinstance(plan.legal_domain, list)
    assert "partition & property" in plan.legal_domain
    assert isinstance(plan.provisions, list)
    assert isinstance(plan.matter_type, list)
    assert plan.province == "Punjab"
    assert plan.forum == "Civil Court / District Judge"
    assert len(plan.binding_courts) >= 1
    assert "Lahore High Court" in plan.binding_courts[1]

    # 3. SearchLane object and dictionary indexing compatibility
    assert len(plan.search_lanes) >= 1
    first_lane = plan.search_lanes[0]
    assert isinstance(first_lane, SearchLane)
    assert isinstance(first_lane.lane_id, str)
    assert isinstance(first_lane.lane, str)
    # Critical: dict subscripting must work for legacy callers
    assert first_lane["lane"] == first_lane.lane_id
    assert first_lane["query"] == first_lane.query
    assert first_lane.get("lane") == first_lane.lane_id

    # 4. JSON serialization round-trip
    dumped = plan.model_dump()
    assert dumped["primary_domain"] == "civil"
    assert dumped["target_province"] == "Punjab"
    assert dumped["allowed_domains_filter"] == ["civil"]
