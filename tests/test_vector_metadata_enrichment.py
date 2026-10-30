"""
tests/test_vector_metadata_enrichment.py

Comprehensive unit & regression tests for Phase 4, Step 3:
Vector Metadata Migration & Ingestion Enrichment.

Tests:
1. All supported Pakistani legal domains.
2. Ambiguous domain classification & graceful fallback.
3. Cross-domain contamination prevention.
4. Generic word exclusion (guarding against 'court', 'director', 'petition', 'appeal').
5. Multiple statutory provisions extraction.
6. Missing statutory references handling.
7. Bench-level hierarchy extraction (Supreme Court, High Court, District, Special Courts).
8. Existing metadata preservation (backward compatibility).
9. Legacy vector compatibility and normalization.
10. Pinecone metadata serialization & type validation.
11. Maximum metadata size handling (<40KB enforcement).
12. Mocked Pinecone vector upsert integration.
"""

import json
from unittest.mock import MagicMock
import pytest

from core.metadata_enrichment import (
    METADATA_SCHEMA_VERSION,
    ALL_LEGAL_DOMAINS,
    GENERIC_EXCLUSIONS,
    LegalChunkMetadata,
    classify_legal_text,
    extract_bench_level,
    enrich_chunk_metadata,
    validate_pinecone_metadata_types,
    sanitize_metadata_for_pinecone,
    enforce_pinecone_size_limit,
    is_enriched_vector,
    normalize_legacy_vector_metadata,
    canonicalize_domain_name,
)


def test_taxonomy_domain_alias_normalization():
    """Verify bidirectional normalization of domain variants (tax/taxation, labor/labour, etc.)."""
    assert canonicalize_domain_name("tax") == "taxation"
    assert canonicalize_domain_name("taxation") == "taxation"
    assert canonicalize_domain_name("revenue") == "taxation"
    assert canonicalize_domain_name("labor") == "labour"
    assert canonicalize_domain_name("labour") == "labour"
    assert canonicalize_domain_name("employment") == "labour"
    assert canonicalize_domain_name("ip") == "intellectual_property"
    assert canonicalize_domain_name("cyber") == "cybercrime"
    assert canonicalize_domain_name("env") == "environmental"
    assert canonicalize_domain_name("unknown_xyz") == "general_legal"
    assert canonicalize_domain_name("") == "general_legal"


# ==============================================================================
# 1. Domain Coverage Tests
# ==============================================================================

def test_all_supported_domains_classified():
    """Verify that every supported Pakistani legal domain can be deterministically identified."""
    test_cases = [
        # (domain, subdomain, sample_text)
        (
            "civil",
            "partition",
            "Suit for partition of joint agricultural land. Under Section 44 of the Transfer of Property Act 1882, a co-sharer cannot alienate a specific portion without partition."
        ),
        (
            "criminal",
            "pre_arrest_bail",
            "Petition under Section 498 Cr.P.C. for grant of pre-arrest bail in case FIR registered under Section 302 PPC. Petitioner claims false implication with malafide intent."
        ),
        (
            "constitutional",
            "high_court_writ",
            "Writ Petition under Article 199 of the Constitution of the Islamic Republic of Pakistan 1973 seeking a writ of mandamus against statutory regulatory authority."
        ),
        (
            "family",
            "khula",
            "Suit for dissolution of marriage on the ground of Khula and recovery of dower under Section 5 of the Family Courts Act 1964."
        ),
        (
            "banking",
            "leave_to_defend",
            "Suit for recovery of finance under Section 9 of the Financial Institutions (Recovery of Finances) Ordinance 2001 (FIO 2001). Defendant filed application for leave to defend under Section 10."
        ),
        (
            "corporate",
            "oppression_and_mismanagement",
            "Petition under Section 286 of the Companies Act 2017 alleging oppression of minority shareholders and illegal dilution of shares."
        ),
        (
            "rent",
            "eviction_personal_need",
            "Ejectment petition under Section 15 of the Punjab Rented Premises Act 2009 (PRPA 2009) on the ground of bona fide personal need of the landlord."
        ),
        (
            "taxation",
            "sales_tax",
            "Sales Tax Appeal under the Sales Tax Act 1990 against disallowance of input tax adjustment under Section 8 by the Federal Board of Revenue."
        ),
        (
            "service",
            "service_tribunal_appeal",
            "Appeal before the Federal Service Tribunal under Section 4 of the Service Tribunals Act 1973 regarding seniority and promotion under the Civil Servants Act 1973."
        ),
        (
            "labour",
            "industrial_dispute",
            "Industrial dispute under Section 33 of the Industrial Relations Act 2012 (IRA 2012) alleging unfair labour practice and illegal termination by employer."
        ),
        (
            "cybercrime",
            "peca_offence",
            "Prosecution under Section 20 of the Prevention of Electronic Crimes Act 2016 (PECA 2016) for offences against dignity of natural person via social media."
        ),
        (
            "intellectual_property",
            "trademark_copyright",
            "Suit for permanent injunction restraining infringement of trade mark and passing off under the Trade Marks Ordinance 2001."
        ),
        (
            "environmental",
            "environmental_protection",
            "Environmental Protection Order issued under Section 16 of the Pakistan Environmental Protection Act 1997 (PEPA 1997) against industrial discharge."
        ),
    ]

    for expected_domain, expected_subdomain, text in test_cases:
        domain, subdomain, provisions, confidence, source = classify_legal_text(text)
        assert domain == expected_domain, f"Expected domain '{expected_domain}', got '{domain}' for text: {text[:60]}"
        assert subdomain == expected_subdomain, f"Expected subdomain '{expected_subdomain}', got '{subdomain}'"
        assert confidence >= 0.80, f"Confidence {confidence} too low for clear statutory text"
        assert source == "statutory_explicit"
        assert len(provisions) >= 1


# ==============================================================================
# 2. Ambiguity & Generic Exclusions Tests
# ==============================================================================

def test_generic_words_do_not_trigger_domain():
    """Verify that generic words like 'court', 'director', 'petition', 'appeal' never trigger a domain."""
    generic_text = (
        "The learned counsel for the petitioner appeared before the court and filed an appeal. "
        "The director of the office stated that the order passed by the judge was according to law in Pakistan."
    )
    domain, subdomain, provisions, confidence, source = classify_legal_text(generic_text)
    assert domain == "general_legal"
    assert subdomain == "unspecified"
    assert provisions == []
    assert confidence < 0.50
    assert source == "unclassified"


def test_ambiguous_conflicting_signals_handling():
    """Verify that conflicting signals with equal weight yield general_legal without inventing domains."""
    conflicting_text = (
        "In a suit for partition under Section 44 of the Transfer of Property Act 1882, "
        "an FIR was registered under Section 498 Cr.P.C. for pre-arrest bail."
    )
    domain, subdomain, provisions, confidence, source = classify_legal_text(conflicting_text)
    # Both partition and pre-arrest bail match equally
    assert domain == "general_legal"
    assert subdomain == "ambiguous_cross_domain"
    assert "transfer_of_property_act_1882_section_44" in provisions
    assert "crpc_1898_section_498" in provisions
    assert confidence <= 0.50


def test_cross_domain_contamination_prevention():
    """Verify that pure civil property case does not get tagged with criminal, even if words like 'director' appear."""
    civil_text = (
        "Suit for partition of ancestral residential property. The managing director of the family firm "
        "testified as a witness regarding possession under Section 44 of the Transfer of Property Act."
    )
    domain, subdomain, provisions, confidence, source = classify_legal_text(civil_text)
    assert domain == "civil"
    assert domain != "criminal"
    assert domain != "corporate"
    assert "crpc" not in "".join(provisions).lower()


# ==============================================================================
# 3. Multiple Statutory Provisions & Reporter Heuristics
# ==============================================================================

def test_multiple_statutory_provisions_extracted():
    """Verify multiple statutory provisions are extracted without duplicates."""
    multi_text = (
        "Application for rejection of plaint under Order VII Rule 11 CPC in a suit for partition under "
        "Section 44 of the Transfer of Property Act 1882 and temporary injunction under Order XXXIX Rules 1 & 2 CPC."
    )
    domain, subdomain, provisions, confidence, source = classify_legal_text(multi_text)
    assert domain == "civil"
    assert "cpc_1908_order_vii_rule_11" in provisions
    assert "transfer_of_property_act_1882_section_44" in provisions
    assert "cpc_1908_order_xxxix_rule_1_2" in provisions
    # Ensure no duplicates
    assert len(provisions) == len(set(provisions))


def test_reporter_citation_heuristics():
    """Verify specialized law reporters anchor domain when text has no direct statutory sections."""
    text_without_sections = "The accused was convicted and sentenced to imprisonment. Evidence of witnesses examined."
    
    # 1. PCrLJ (Pakistan Criminal Law Journal)
    d, s, p, conf, src = classify_legal_text(text_without_sections, citation="2022 PCrLJ 450")
    assert d == "criminal"
    assert src == "neutral_citation"

    # 2. CLD (Corporate Law Decisions)
    d, s, p, conf, src = classify_legal_text("Shareholders dispute regarding board resolutions.", citation="2021 CLD 120")
    assert d == "corporate"
    assert src == "neutral_citation"

    # 3. PTD (Pakistan Tax Decisions)
    d, s, p, conf, src = classify_legal_text("Assessment of revenue and disallowance of expenditure.", citation="2020 PTD 88")
    assert d == "taxation"
    assert src == "neutral_citation"


# ==============================================================================
# 4. Bench-Level Extraction Tests
# ==============================================================================

def test_bench_level_hierarchy_extraction():
    """Verify correct bench levels from court names, citations, and headers."""
    # Supreme Court
    assert extract_bench_level("Supreme Court of Pakistan") == "supreme_court"
    assert extract_bench_level("Supreme Court of AJK") == "supreme_court"
    assert extract_bench_level("", citation="2024 SCMR 120") == "supreme_court"
    assert extract_bench_level("", text_snippet="In the Apex Court of Pakistan") == "supreme_court"

    # High Courts
    assert extract_bench_level("Lahore High Court, Lahore") == "high_court"
    assert extract_bench_level("High Court of Sindh, Karachi") == "high_court"
    assert extract_bench_level("Peshawar High Court, Abbottabad Bench") == "high_court"
    assert extract_bench_level("High Court of Balochistan") == "high_court"
    assert extract_bench_level("Islamabad High Court") == "high_court"
    assert extract_bench_level("", citation="PLD 2021 Lah 45") == "high_court"

    # Special Courts & Tribunals
    assert extract_bench_level("Banking Court-I, Multan") == "special_court_or_tribunal"
    assert extract_bench_level("Federal Service Tribunal, Islamabad") == "special_court_or_tribunal"
    assert extract_bench_level("National Industrial Relations Commission (NIRC)") == "special_court_or_tribunal"
    assert extract_bench_level("Special Court (Control of Narcotic Substances)") == "special_court_or_tribunal"

    # District Courts
    assert extract_bench_level("District and Sessions Judge, Rawalpindi") == "district_court"
    assert extract_bench_level("Senior Civil Judge, Gujranwala") == "district_court"
    assert extract_bench_level("Judicial Magistrate 1st Class, Faisalabad") == "district_court"

    # Unknown
    assert extract_bench_level("Arbitration Board") == "unknown"


# ==============================================================================
# 5. Metadata Enrichment & Backward Compatibility Tests
# ==============================================================================

def test_enrich_chunk_preserves_existing_metadata():
    """Verify that existing metadata fields are preserved untouched."""
    base_meta = {
        "case_id": "2024_SCMR_500",
        "citation": "2024 SCMR 500",
        "court": "Supreme Court of Pakistan",
        "decision_date": "2024-03-15",
        "year": 2024,
        "title": "Mst. Aisha Bibi v. Muhammad Aslam",
        "pdf_url": "https://example.com/judgments/2024_scmr_500.pdf",
        "chunk_index": 2
    }
    chunk_text = (
        "Suit for partition under Section 44 of Transfer of Property Act 1882. "
        "A co-sharer in joint property cannot transfer specific khasra numbers prior to final decree of partition."
    )

    enriched = enrich_chunk_metadata(chunk_text, base_metadata=base_meta, document_id="2024_SCMR_500")

    # Verify existing fields preserved
    assert enriched["case_id"] == "2024_SCMR_500"
    assert enriched["citation"] == "2024 SCMR 500"
    assert enriched["court"] == "Supreme Court of Pakistan"
    assert enriched["year"] == 2024
    assert enriched["chunk_index"] == 2
    assert enriched["pdf_url"] == "https://example.com/judgments/2024_scmr_500.pdf"

    # Verify newly enriched fields
    assert enriched["metadata_schema_version"] == METADATA_SCHEMA_VERSION
    assert enriched["legal_domain"] == "civil"
    assert enriched["subdomain"] == "partition"
    assert "transfer_of_property_act_1882_section_44" in enriched["statutory_provisions"]
    assert enriched["bench_level"] == "supreme_court"
    assert enriched["classification_confidence"] >= 0.85
    assert enriched["classification_source"] == "statutory_explicit"
    assert enriched["source_document_id"] == "2024_SCMR_500"


def test_legacy_vector_compatibility_and_normalization():
    """Verify legacy vectors lacking Step 3 metadata are detected and normalized."""
    legacy_meta = {
        "case_id": "1995_SCMR_100",
        "court": "Supreme Court of Pakistan",
        "text_preview": "Order of the court on leave to appeal."
    }

    assert not is_enriched_vector(legacy_meta)

    normalized = normalize_legacy_vector_metadata(legacy_meta)
    assert normalized["case_id"] == "1995_SCMR_100"
    assert normalized["metadata_schema_version"] == "0.0_legacy"
    assert normalized["legal_domain"] == "general_legal"
    assert normalized["subdomain"] == "unspecified"
    assert normalized["statutory_provisions"] == []
    assert normalized["bench_level"] == "supreme_court"
    assert normalized["classification_confidence"] == 0.0
    assert normalized["classification_source"] == "unclassified"


# ==============================================================================
# 6. Pinecone Constraints & Size Limit Tests
# ==============================================================================

def test_pinecone_metadata_type_validation():
    """Verify Pinecone type validation enforces primitive types and string lists."""
    valid_meta = {
        "text": "Valid legal text",
        "count": 5,
        "score": 0.85,
        "is_active": True,
        "tags": ["criminal", "bail", "498"]
    }
    is_valid, err = validate_pinecone_metadata_types(valid_meta)
    assert is_valid, f"Expected valid, got: {err}"

    # Invalid: nested dictionary
    invalid_nested = {"meta": {"nested": "value"}}
    is_valid, err = validate_pinecone_metadata_types(invalid_nested)
    assert not is_valid
    assert "unsupported type" in err

    # Invalid: list of ints
    invalid_list = {"numbers": [1, 2, 3]}
    is_valid, err = validate_pinecone_metadata_types(invalid_list)
    assert not is_valid
    assert "non-string items" in err


def test_metadata_sanitization_for_pinecone():
    """Verify arbitrary metadata is cleanly sanitized into Pinecone-supported types."""
    dirty_meta = {
        "text": "Some text",
        "nested_dict": {"key": "val"},
        "int_list": [1, 2, 3],
        "none_val": None
    }
    sanitized = sanitize_metadata_for_pinecone(dirty_meta)

    # Check that None is dropped
    assert "none_val" not in sanitized
    # Check nested dict is JSON stringified
    assert isinstance(sanitized["nested_dict"], str)
    # Check int_list converted to string list
    assert sanitized["int_list"] == ["1", "2", "3"]

    # Must pass validation
    is_valid, _ = validate_pinecone_metadata_types(sanitized)
    assert is_valid


def test_maximum_metadata_size_handling():
    """Verify metadata exceeding 38KB is safely truncated to prevent Pinecone 40KB rejects."""
    # Generate 50KB of text
    huge_text = "Partition dispute co-sharer Section 44 Transfer of Property Act. " * 800
    assert len(huge_text.encode('utf-8')) > 45000

    meta = {
        "case_id": "huge_case_001",
        "legal_domain": "civil",
        "subdomain": "partition",
        "text": huge_text,
        "text_preview": huge_text[:200]
    }

    guarded = enforce_pinecone_size_limit(meta, max_bytes=38000)
    serialized_bytes = len(json.dumps(guarded).encode('utf-8'))
    assert serialized_bytes <= 38000
    assert "[truncated for Pinecone size limit]" in guarded["text"]
    assert guarded["legal_domain"] == "civil"
    assert guarded["case_id"] == "huge_case_001"


# ==============================================================================
# 7. Mocked Pinecone Upsert Test
# ==============================================================================

def test_mocked_pinecone_upsert_with_enriched_chunk():
    """Verify that enriched metadata can be upserted to a mocked Pinecone index without errors."""
    mock_index = MagicMock()
    mock_index.upsert.return_value = {"upserted_count": 1}

    chunk_text = "Petition for leave to appeal under Article 185(3) of Constitution of Pakistan 1973."
    base_meta = {"citation": "2023 SCMR 100", "court": "Supreme Court of Pakistan"}
    enriched_meta = enrich_chunk_metadata(chunk_text, base_metadata=base_meta, document_id="2023_SCMR_100")

    # Verify metadata is Pinecone-compliant
    is_valid, err = validate_pinecone_metadata_types(enriched_meta)
    assert is_valid, f"Pinecone validation failed: {err}"

    # Upsert to mock
    vector = {
        "id": "2023_SCMR_100_chunk_0",
        "values": [0.1] * 1024,
        "metadata": enriched_meta
    }
    res = mock_index.upsert(vectors=[vector], namespace="judgments")

    assert res["upserted_count"] == 1
    mock_index.upsert.assert_called_once_with(vectors=[vector], namespace="judgments")
