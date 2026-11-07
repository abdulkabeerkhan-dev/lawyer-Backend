"""
legal_ai/statutes/legal_unit_record.py

Standardized data model for verified legal units and parser coverage reporting.
Adheres to Section AI Design Principles:
- Structure first, search second. Every provision is an atomic, verified legal unit.
- Raw and clean data kept strictly distinct for verifiable provenance.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class LegalUnitRecord(BaseModel):
    """
    Atomic verified legal unit (Article, Section, Order, Rule).
    The model never supplies law; it can only select, quote, and explain
    these pre-verified records.
    """
    unit_id: str = Field(..., description="Globally unique canonical unit ID, e.g. 'limitation-act-1908:article:57'")
    statute_id: str = Field(..., description="Canonical statute code, e.g. 'limitation-act-1908'")
    statute_title: str = Field(..., description="Official statute title, e.g. 'Limitation Act, 1908'")
    jurisdiction: str = Field(default="federal", description="Jurisdiction: federal, punjab, sindh, etc.")
    unit_type: str = Field(..., description="Strict unit type: 'article', 'section', 'order', 'rule', 'schedule_row'")
    number: str = Field(..., description="Strict, cleaned unit number, e.g. '57', '64', '489-F'")
    parent: Optional[str] = Field(default=None, description="Structural parent, e.g. 'First Schedule, First Division: Suits, Part VI'")
    heading_description: str = Field(..., description="Clean heading or description of suit")
    period: Optional[str] = Field(default=None, description="Prescribed period of limitation, e.g. 'Three years'")
    trigger: Optional[str] = Field(default=None, description="Time from which period begins to run")
    text: str = Field(..., description="Full canonical clean text of the provision")
    footnotes: List[str] = Field(default_factory=list, description="Extracted, isolated footnotes")
    cross_references: List[str] = Field(default_factory=list, description="IDs of linked or cross-referenced statutes/provisions")
    caveats: List[str] = Field(default_factory=list, description="Explicit statutory caveats (e.g. Punjab loan override)")
    amended_to: Optional[str] = Field(default=None, description="Amendment history / last updated date")
    
    # Provenance and raw integrity (Layer 1 Invariant)
    source_url: str = Field(default="", description="Source URL or origin repository")
    retrieved_at: str = Field(default="", description="Timestamp when scraped or loaded")
    checksum: str = Field(..., description="SHA-256 hash of clean text")
    raw_row: Optional[Dict[str, Any]] = Field(default=None, description="Original unparsed CSV row or raw record for auditability")


class StatuteCoverageReport(BaseModel):
    """
    Audit ledger reporting coverage, sequential validation, and rejection reasons.
    Zero silent skips.
    """
    statute_id: str
    total_raw_rows: int = 0
    sections_parsed: int = 0
    articles_parsed: int = 0
    total_units_loaded: int = 0
    rejected_rows_count: int = 0
    rejections: List[Dict[str, Any]] = Field(default_factory=list, description="List of rejected rows and explicit reasons")
    sequence_integrity_verified: bool = False
    expected_range: str = ""
    notes: List[str] = Field(default_factory=list)
