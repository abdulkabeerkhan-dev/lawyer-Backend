"""
Court External Fallback Pipeline & Verification Gatekeeper
Version: 1.0.0
Phase 4 Standard Component (Stages 4 - 7)

Handles:
- Stage 4: WAF-compliant HTTP Fetch with complete browser headers
- Stage 5: Clean PyMuPDF (fitz) text & metadata extraction (pypdf dropped)
- Stage 6: Deterministic Gate 1 to Gate 4 validation
- Stage 7: Strict Quarantine-Only Isolation (zero writes to full_judgments / Pinecone)
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import os
import re
import time
import json
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from dotenv import load_dotenv

# Primary extraction library
import fitz  # PyMuPDF (standardized, pypdf dropped)

# Secondary optional cross-check
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from core.case_type_registry import (
    canonicalize_case_type,
    extract_case_type_and_docket,
    CASE_TYPE_CANONICAL_MAP
)

# Load environment
ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")

supabase_client = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        from supabase import create_client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    except Exception as e:
        print(f"⚠️ Supabase init notice in fallback_pipeline: {e}")

# Whitelisted court domains (single source of truth)
WHITELISTED_COURT_DOMAINS = [
    "supremecourt.gov.pk",
    "lhc.gov.pk",
    "sys.lhc.gov.pk",
    "shc.gov.pk",
    "phc.gov.pk",
    "ihc.gov.pk",
    "balochistanhighcourt.gov.pk",
    "federalshariatcourt.gov.pk"
]

# Standard browser headers (validated in Stage 0 to bypass WAF)
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/pdf,text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1"
}

# Domain to Jurisdiction mapping for Gate 1
DOMAIN_COURT_MAP = {
    "supremecourt.gov.pk": ["Supreme Court of Pakistan", "Supreme Court", "SC"],
    "lhc.gov.pk": ["Lahore High Court", "LHC"],
    "sys.lhc.gov.pk": ["Lahore High Court", "LHC"],
    "shc.gov.pk": ["Sindh High Court", "High Court of Sindh", "SHC"],
    "phc.gov.pk": ["Peshawar High Court", "PHC"],
    "ihc.gov.pk": ["Islamabad High Court", "IHC"],
    "balochistanhighcourt.gov.pk": ["Balochistan High Court", "High Court of Balochistan", "BHC"],
    "federalshariatcourt.gov.pk": ["Federal Shariat Court", "FSC"]
}

LOCAL_QUARANTINE_DIR = r"D:\missing_gaps_verified\quarantine"
os.makedirs(LOCAL_QUARANTINE_DIR, exist_ok=True)
LOCAL_QUARANTINE_FILE = os.path.join(LOCAL_QUARANTINE_DIR, "quarantined_judgments.jsonl")


# ==============================================================================
# STAGE 4: HTTP FETCH WITH FULL BROWSER HEADERS
# ==============================================================================
def stage4_fetch_pdf(url: str, timeout: int = 20) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Stage 4: Fetches raw judgment PDF bytes via HTTP with complete browser headers.
    Returns (pdf_bytes, error_message).
    """
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()

    # Enforce domain whitelist at fetch-agent level
    if not any(domain == wd or domain.endswith("." + wd) for wd in WHITELISTED_COURT_DOMAINS):
        return None, f"Domain '{domain}' is not in WHITELISTED_COURT_DOMAINS"

    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw_bytes = resp.read()

            if not raw_bytes.startswith(b"%PDF-") and "pdf" not in content_type.lower():
                return None, f"Response is not a valid PDF (Content-Type: {content_type})"

            return raw_bytes, None
    except Exception as e:
        return None, f"Fetch error: {e}"


# ==============================================================================
# STAGE 5: EXTRACTION (FITZ / PYMUPDF STANDARDIZED)
# ==============================================================================
def stage5_extract_metadata_and_text(pdf_bytes: bytes, source_url: str) -> Dict[str, Any]:
    """
    Stage 5: Standardized text and metadata extraction using PyMuPDF (fitz).
    Extracts text, docket, court, date, parties, and computes OCR/text quality confidence.
    """
    result: Dict[str, Any] = {
        "raw_text": "",
        "court_name": None,
        "case_type": None,
        "docket_number": None,
        "case_title": None,
        "decision_date": None,
        "judge_names": None,
        "extracted_citation": None,
        "ocr_confidence": None,  # Explicitly None for native PDF layer
        "text_health_score": 0.0,
        "extraction_method": "PyMuPDF_fitz_v1.28",
        "page_count": 0,
    }

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        result["page_count"] = len(doc)
        pages_text = [page.get_text() for page in doc]
        full_text = "\n\n".join(pages_text).strip()
        result["raw_text"] = full_text

        # Calculate Gate 4 Text Health & Dictionary Density Score
        if full_text:
            printable_count = sum(1 for c in full_text if c.isprintable() and not (ord(c) > 127 and ord(c) < 160))
            char_ratio = printable_count / len(full_text)
            anchors = ["order", "judgment", "petition", "appeal", "court", "versus", "vs", "justice", "respondent"]
            anchor_hits = sum(1 for a in anchors if re.search(r"\b" + a + r"\b", full_text, re.IGNORECASE))
            anchor_score = min(1.0, anchor_hits / 5.0)
            health = round(0.5 * char_ratio + 0.5 * anchor_score, 3)
            result["text_health_score"] = health
        else:
            result["text_health_score"] = 0.0
        
        result["ocr_confidence"] = None  # Native PDF layer (not scanned OCR)

        p1_text = pages_text[0] if pages_text else ""
        lines = [line.strip() for line in p1_text.splitlines() if line.strip()]

        # 1. Resolve Court Name
        domain = urllib.parse.urlparse(source_url).netloc.lower()
        if "supremecourt" in domain:
            result["court_name"] = "Supreme Court of Pakistan"
        elif "lhc" in domain:
            result["court_name"] = "Lahore High Court"
        elif "shc" in domain:
            result["court_name"] = "High Court of Sindh"
        elif "phc" in domain:
            result["court_name"] = "Peshawar High Court"
        elif "ihc" in domain:
            result["court_name"] = "Islamabad High Court"
        elif "balochistan" in domain:
            result["court_name"] = "High Court of Balochistan"
        elif "shariat" in domain:
            result["court_name"] = "Federal Shariat Court"

        for line in lines[:10]:
            if re.search(r"supreme\s+court\s+of\s+pakistan", line, re.IGNORECASE):
                result["court_name"] = "Supreme Court of Pakistan"
                break
            elif re.search(r"lahore\s+high\s+court", line, re.IGNORECASE):
                result["court_name"] = "Lahore High Court"
                break
            elif re.search(r"high\s+court\s+of\s+sindh|sindh\s+high\s+court", line, re.IGNORECASE):
                result["court_name"] = "High Court of Sindh"
                break

        # 2. Extract Docket and Case Type
        for line in lines[:25]:
            m_cm = re.search(r'\bC\.?M\.?\s*(?:No\.?)?\s*(\d+[\w\/\-]*\s*(?:of\s*\d{4})?)', line, re.IGNORECASE)
            m_cp = re.search(r'\b(?:C\.?P\.?L?\.?A?\.?|Civil\s+Petition)\s*(?:No\.?)?\s*(\d+[\w\/\-]*\s*(?:of\s*\d{4})?)', line, re.IGNORECASE)
            m_wp = re.search(r'\b(?:W\.?P\.?|Writ\s+Petition)\s*(?:No\.?)?\s*(\d+[\w\/\-]*\s*(?:of\s*\d{4})?)', line, re.IGNORECASE)
            if m_cm:
                result["case_type"] = "CM"
                result["docket_number"] = re.sub(r'\s*of\s*', '/', m_cm.group(1)).replace(' ', '').strip()
                break
            elif m_cp:
                result["case_type"] = "CP"
                result["docket_number"] = re.sub(r'\s*of\s*', '/', m_cp.group(1)).replace(' ', '').strip()
                break
            elif m_wp:
                result["case_type"] = "WP"
                result["docket_number"] = re.sub(r'\s*of\s*', '/', m_wp.group(1)).replace(' ', '').strip()
                break
            elif re.search(r"\b(Civil|Criminal|Const|Writ|Petition|Appeal|Revision)\b", line, re.IGNORECASE) and re.search(r"\d+", line):
                ctype, docket = extract_case_type_and_docket(line)
                if docket:
                    result["case_type"] = ctype
                    result["docket_number"] = docket
                    break

        # 3. Extract Parties / Case Title
        for i, line in enumerate(lines[:35]):
            if re.search(r"^versus$|^vs\.?$|^v\.?$", line, re.IGNORECASE):
                raw_pet_lines = [l for l in lines[max(0, i-4):i] if not re.search(r'against|passed\s+by|tribunal|appeal\s+no|c\.?p\.?l?\.?a?\.?|order\s+sheet|writ\s+petition|department', l, re.IGNORECASE)]
                p_str = " ".join(raw_pet_lines).strip()
                p = re.split(r'Petitioner|Appellant|Applicant', p_str, flags=re.IGNORECASE)[0].strip()

                raw_resp_lines = lines[i+1:min(len(lines), i+6)]
                r_raw = " ".join(raw_resp_lines).strip()
                r = re.split(r'Respondent|Opposite|For the|S\.?No|Order with signature|Date of order|In Person|JUDGE', r_raw, flags=re.IGNORECASE)[0].strip()

                if ")" in p:
                    p = p.split(")")[-1].strip()
                p = re.sub(r'\(?Against\s+.*?\)?', '', p, flags=re.IGNORECASE).strip()
                p = re.sub(r'^(?:in\s+)?(?:writ\s+petition|civil\s+appeal|c\.?m\.?|c\.?p\.?l?\.?a?\.?)\s*(?:no\.?)?\s*[\d\w\/\-]+\s*(?:of\s*\d{4})?', '', p, flags=re.IGNORECASE).strip()
                p = re.sub(r'^(?:in\s+)', '', p, flags=re.IGNORECASE).strip()
                r = re.sub(r'\s+Proceeding\b', '', r, flags=re.IGNORECASE).strip()
                p = re.sub(r'^[\.…\s\-\?:]+|[\.…\s\-\?:]+$', '', p).strip()
                r = re.sub(r'^[\.…\s\-\?:]+|[\.…\s\-\?:]+$', '', r).strip()
                if p and r:
                    result["case_title"] = f"{p} v. {r}"
                    break

        # 4. Extract Decision Date (Bottom-Anchored to Signatures/Footer)
        footer = full_text[-2500:] if len(full_text) > 2500 else full_text
        date_val = None
        bottom_patterns = [
            r'(?:Islamabad|Lahore|Karachi|Peshawar|Quetta|Rawalpindi)[\.,\s\n]+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4})',
            r'(?:Islamabad|Lahore|Karachi|Peshawar|Quetta|Rawalpindi)[\.,\s\n]+(\d{1,2}[\./\-]\d{1,2}[\./\-]\d{2,4})',
            r'(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December),?\s+\d{4})[\s\n]+(?:Approved for Reporting|JUDGE|Chief Justice)',
            r'(\d{1,2}[\./\-]\d{1,2}[\./\-]\d{2,4})[\s\n]+(?:Approved for Reporting|JUDGE|Chief Justice)',
            r'(?:Announced|Decided|Signed)[\s\w]*?(?:on)?[\s:]+(\d{1,2}[\./\-]\d{1,2}[\./\-]\d{2,4})',
            r'(?:Announced|Decided|Signed)[\s\w]*?(?:on)?[\s:]+(\d{1,2}\s+[A-Za-z]+,?\s+\d{4})',
        ]
        for pat in bottom_patterns:
            m = re.search(pat, footer, re.IGNORECASE)
            if m:
                date_val = m.group(1).strip()
                break
        if not date_val:
            m_hearing = re.search(r'(?:Date of Hearing|Decided on|Order Date)\s*[:\-\n\s]+(\d{1,2}[\./\-]\d{1,2}[\./\-]\d{2,4}|\d{1,2}\s+[A-Za-z]+,?\s+\d{4})', full_text, re.IGNORECASE)
            if m_hearing:
                date_val = m_hearing.group(1).strip()
        if not date_val:
            m_order = re.search(r'\n\s*(\d{1,2}\.\d{1,2}\.\d{4})\s*\n\s*(?:Mr\.|Ms\.|Mian|Ch\.|Advocate)', full_text)
            if m_order:
                date_val = m_order.group(1).strip()
        result["decision_date"] = date_val

        # 5. Extract Judges / Bench
        present_match = re.search(r"(?:PRESENT|BEFORE)\s*:\s*([\s\S]*?)(?:(?:C\.?P|W\.?P|Civil|ORDER|Judgment|Versus|Petitioner))", p1_text, re.IGNORECASE)
        if present_match:
            judge_block = present_match.group(1).strip()
            judges = [line.strip() for line in judge_block.splitlines() if re.search(r"Justice|Mr\.|Mrs\.|Chief Justice", line, re.IGNORECASE)]
            if judges:
                result["judge_names"] = ", ".join(judges)
        if not result["judge_names"]:
            m_sig = re.search(r'\(([A-Z\s\.]+)\)\s*\n\s*(?:JUDGE|Chief Justice)', footer)
            if m_sig:
                result["judge_names"] = f"Mr. Justice {m_sig.group(1).strip().title()}"
        if not result["judge_names"]:
            m_sig2 = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+),?\s+J\.', full_text[:3000])
            if m_sig2:
                result["judge_names"] = f"{m_sig2.group(1)}, J."

        # 6. Extracted Citation
        url_filename = os.path.basename(source_url)
        cit_match = re.search(r"(\d{4}\s*[A-Za-z]+\s*\d+)", url_filename)
        if cit_match:
            result["extracted_citation"] = cit_match.group(1).replace("_", " ").upper()
        elif result.get("case_type") and result.get("docket_number"):
            result["extracted_citation"] = f"{result['case_type']} {result['docket_number']}"

    except Exception as e:
        result["ocr_confidence"] = 0.0
        result["extraction_method"] = f"fitz_error: {e}"

    return result


# ==============================================================================
# STAGE 6: VERIFICATION GATES (GATES 1 - 4)
# ==============================================================================
def stage6_verify_gates(record: Dict[str, Any], source_url: str) -> Dict[str, Any]:
    """
    Stage 6: Strict multi-gate evaluation.
    Gate 1: Domain-to-jurisdiction match
    Gate 2: Required non-null fields (court, case/docket, date, parties)
    Gate 3: Composite dedup key: [court_name] + [case_type canonical code] + [docket_number] + [decision_date]
    Gate 4: 70% hard-reject / 60-80% soft-flag-to-quarantine
    """
    gate_results = {
        "gate1_passed": False,
        "gate2_passed": False,
        "gate3_passed": False,
        "gate4_passed": False,
        "overall_valid": False,
        "rejection_reasons": []
    }

    # GATE 1: Domain-to-Jurisdiction Match
    domain = urllib.parse.urlparse(source_url).netloc.lower()
    court_name = record.get("court_name") or ""
    
    domain_matched = False
    for d_key, valid_courts in DOMAIN_COURT_MAP.items():
        if domain == d_key or domain.endswith("." + d_key):
            if any(vc.lower() in court_name.lower() for vc in valid_courts):
                domain_matched = True
                break

    gate_results["gate1_passed"] = domain_matched
    if not domain_matched:
        gate_results["rejection_reasons"].append(f"Gate 1 Failed: Domain '{domain}' does not match court '{court_name}'")

    # GATE 2: Required Non-Null Fields
    court = record.get("court_name")
    docket = record.get("docket_number")
    date_val = record.get("decision_date")
    title = record.get("case_title")

    has_all_required = bool(court and docket and date_val and title)
    gate_results["gate2_passed"] = has_all_required
    if not has_all_required:
        missing = []
        if not court: missing.append("court_name")
        if not docket: missing.append("docket_number")
        if not date_val: missing.append("decision_date")
        if not title: missing.append("case_title")
        gate_results["rejection_reasons"].append(f"Gate 2 Failed: Missing required fields: {', '.join(missing)}")

    # GATE 3: Composite Dedup Check
    # Key = [court_name] + [case_type canonical code] + [docket_number] + [decision_date]
    case_type = record.get("case_type") or "GEN"
    composite_key = f"{court}::{case_type}::{docket}::{date_val}"
    record["composite_key"] = composite_key

    is_duplicate = False
    if supabase_client and docket:
        try:
            res_q = supabase_client.table("quarantined_judgments").select("id").eq("extracted_court_name", court).eq("docket_number", docket).execute()
            if res_q.data:
                is_duplicate = True
        except Exception:
            pass

    # Check local quarantine file
    if not is_duplicate and os.path.exists(LOCAL_QUARANTINE_FILE):
        try:
            with open(LOCAL_QUARANTINE_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        if item.get("composite_key") == composite_key:
                            is_duplicate = True
                            break
        except Exception:
            pass

    gate_results["gate3_passed"] = not is_duplicate
    if is_duplicate:
        gate_results["rejection_reasons"].append(f"Gate 3 Failed: Duplicate entry detected for key '{composite_key}'")

    # GATE 4: Text Health & Dictionary Density Floor
    health = record.get("text_health_score", 0.0)
    if health < 0.70:
        gate_results["gate4_passed"] = False
        gate_results["rejection_reasons"].append(f"Gate 4 Hard Reject: Text Health Score {health:.1%} is below 70% threshold")
    elif 0.70 <= health < 0.80:
        gate_results["gate4_passed"] = True  # Soft flag into quarantine for review
    else:
        gate_results["gate4_passed"] = True

    gate_results["overall_valid"] = (
        gate_results["gate1_passed"] and
        gate_results["gate2_passed"] and
        gate_results["gate3_passed"] and
        gate_results["gate4_passed"]
    )

    return gate_results


# ==============================================================================
# STAGE 7: QUARANTINE ISOLATION (ZERO DIRECT PRODUCTION WRITES)
# ==============================================================================
def stage7_quarantine_record(record: Dict[str, Any], gate_results: Dict[str, Any], source_url: str) -> Dict[str, Any]:
    """
    Stage 7: Inserts the candidate judgment strictly into quarantine.
    Guarantees status='pending_review' and zero direct writes to full_judgments or Pinecone.
    """
    domain = urllib.parse.urlparse(source_url).netloc.lower()
    
    quarantine_payload = {
        "source_url": source_url,
        "source_domain": domain,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "extracted_citation": record.get("extracted_citation"),
        "extracted_case_title": record.get("case_title"),
        "extracted_court_name": record.get("court_name"),
        "extracted_date": record.get("decision_date"),
        "extracted_judge_names": record.get("judge_names"),
        "docket_number": record.get("docket_number"),
        "case_type": record.get("case_type"),
        "raw_text": record.get("raw_text"),
        "ocr_confidence": record.get("ocr_confidence"),  # Explicitly None for native PDFs
        "text_health_score": record.get("text_health_score"),
        "extraction_method": record.get("extraction_method"),
        "citation_format_valid": bool(record.get("extracted_citation")),
        "court_domain_match": gate_results.get("gate1_passed", False),
        "passes_min_confidence": bool((record.get("text_health_score") or 0.0) >= 0.80),
        "status": "pending_review",  # Strict enforcement: all incoming records quarantined
        "reviewed_by": None,
        "reviewed_at": None,
        "rejection_reason": "; ".join(gate_results.get("rejection_reasons", [])) if not gate_results.get("overall_valid") else None,
        "promoted_to_case_id": None,
        "composite_key": record.get("composite_key")
    }

    # 1. Attempt Supabase quarantine table insert
    inserted_to_supabase = False
    supabase_error = None
    if supabase_client:
        try:
            sb_data = {k: v for k, v in quarantine_payload.items() if k != "composite_key"}
            res = supabase_client.table("quarantined_judgments").insert(sb_data).execute()
            if res.data:
                inserted_to_supabase = True
                quarantine_payload["id"] = res.data[0].get("id")
        except Exception as e:
            supabase_error = str(e)

    # 2. Local JSONL Quarantine Staging (audit trail & backup)
    with open(LOCAL_QUARANTINE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(quarantine_payload) + "\n")

    quarantine_payload["inserted_to_supabase"] = inserted_to_supabase
    quarantine_payload["supabase_error"] = supabase_error
    quarantine_payload["local_staging_file"] = LOCAL_QUARANTINE_FILE

    return quarantine_payload


# ==============================================================================
# PIPELINE ORCHESTRATOR (STAGES 4 -> 5 -> 6 -> 7)
# ==============================================================================
def process_court_pdf_pipeline(url: str) -> Dict[str, Any]:
    """
    Executes end-to-end fallback pipeline for a single court PDF URL:
    Stage 4 (Fetch) -> Stage 5 (Extract) -> Stage 6 (Validate Gates) -> Stage 7 (Quarantine)
    """
    print(f"\n================================================================================")
    print(f"[PIPELINE START] Processing URL: {url}")
    print(f"================================================================================")

    # STAGE 4: Fetch
    print("--> [Stage 4] Fetching PDF with full browser headers...")
    pdf_bytes, err = stage4_fetch_pdf(url)
    if err or not pdf_bytes:
        print(f"❌ [Stage 4 FAILED] {err}")
        return {"status": "error", "stage": "Stage 4", "error": err}
    print(f"✅ [Stage 4 OK] Fetched {len(pdf_bytes):,} bytes.")

    # STAGE 5: Extract
    print("--> [Stage 5] Extracting text and metadata via PyMuPDF (fitz)...")
    record = stage5_extract_metadata_and_text(pdf_bytes, url)
    print(f"✅ [Stage 5 OK] Extracted:")
    print(f"    - Court: {record['court_name']}")
    print(f"    - Case Type: {record['case_type']}")
    print(f"    - Docket: {record['docket_number']}")
    print(f"    - Title: {record['case_title']}")
    print(f"    - Date: {record['decision_date']}")
    print(f"    - Judges: {record['judge_names']}")
    print(f"    - Confidence: {record['ocr_confidence']:.1%} ({record['page_count']} pages)")

    # STAGE 6: Gates
    print("--> [Stage 6] Evaluating Gates 1 through 4...")
    gates = stage6_verify_gates(record, url)
    print(f"    * Gate 1 (Domain Match): {'PASS' if gates['gate1_passed'] else 'FAIL'}")
    print(f"    * Gate 2 (Required Fields): {'PASS' if gates['gate2_passed'] else 'FAIL'}")
    print(f"    * Gate 3 (Composite Dedup): {'PASS' if gates['gate3_passed'] else 'FAIL'}")
    print(f"    * Gate 4 (Quality Floor): {'PASS' if gates['gate4_passed'] else 'FAIL'}")
    print(f"    * Overall Gate Status: {'VALID CANDIDATE' if gates['overall_valid'] else 'FLAGGED'}")

    # STAGE 7: Quarantine
    print("--> [Stage 7] Quarantining record (status='pending_review')...")
    q_res = stage7_quarantine_record(record, gates, url)
    print(f"✅ [Stage 7 OK] Record successfully quarantined!")
    print(f"    - Status: {q_res['status']}")
    print(f"    - Supabase Ingestion: {'YES (Table public.quarantined_judgments)' if q_res['inserted_to_supabase'] else 'Pending Dashboard DDL (Staged Locally)'}")
    print(f"    - Local Staging: {q_res['local_staging_file']}")

    return {
        "status": "success",
        "url": url,
        "extracted": record,
        "gates": gates,
        "quarantined": q_res
    }
