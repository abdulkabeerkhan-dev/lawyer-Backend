"""
Phase 2A: Vector Indexing Pipeline for reindex_queue.json
Ingests judgment texts from Supabase full_judgments, chunks with token overlap,
embeds via voyage-law-2, and upserts vectors into Pinecone 'judgments' namespace.
"""

import os
import sys
import json
import time
import re
import random
import argparse
from typing import List, Dict, Any, Set, Tuple
import requests
import tiktoken
from dotenv import load_dotenv

WORKSPACE_DIR = r"c:\Users\kabeer\Documents\lawyer-Backend-master\lawyer-Backend-master"
ENV_PATH = os.path.join(WORKSPACE_DIR, ".env")
load_dotenv(dotenv_path=ENV_PATH)

from supabase import create_client
from pinecone import Pinecone

# Configurations
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-law-2")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "legal-kb-pk-local")
PINECONE_HOST = os.getenv("PINECONE_HOST")
PINECONE_NAMESPACE = "judgments"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

CHECKPOINT_PATH = os.path.join(WORKSPACE_DIR, "indexing_checkpoint.log")
REINDEX_QUEUE_PATH = os.path.join(WORKSPACE_DIR, "reindex_queue.json")
SKIPPED_STUBS_PATH = os.path.join(WORKSPACE_DIR, "skipped_stubs.csv")

# Tokenizer
tokenizer = tiktoken.get_encoding("cl100k_base")
MIN_CLEAN_TOKENS = 15



def load_checkpoint() -> Set[str]:
    """Load already indexed case_ids from checkpoint log."""
    completed: Set[str] = set()
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                cid = line.strip()
                if cid:
                    completed.add(cid)
    return completed


def append_checkpoint(case_ids: List[str]) -> None:
    """Append newly indexed case_ids to checkpoint log with immediate disk flush."""
    with open(CHECKPOINT_PATH, "a", encoding="utf-8") as f:
        for cid in case_ids:
            f.write(f"{cid}\n")
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass


def extract_year(date_str: str, case_id: str) -> int:
    """Extract integer year from date string or case_id."""
    for s in (date_str, case_id):
        if s:
            m = re.search(r"(?:^|[\D_])(19\d\d|20\d\d)(?:[\D_]|$)", str(s))
            if m:
                return int(m.group(1))
    return 0



def clean_portal_boilerplate(text: str) -> str:
    """Strip website scraper artifacts, navigation menus, and boilerplate headers."""
    if not text:
        return ""
    # Normalize non-breaking spaces
    text = text.replace("\xa0", " ")
    # Strip Case Description header artifacts
    text = re.sub(r"(?i)×\s*\n*\s*Case Description\s*", "", text)
    # Strip PLD navigation block
    text = re.sub(r"(?i)My Account\s*\nFeedback.*?(?:Bookmark this [Cc]ase\s*\n+|Citation Name:[^\n]+\n+)", "", text, flags=re.DOTALL)
    # Strip header artifacts
    text = re.sub(r"(?i)Citation Name:\s*[^\n]+", "", text)
    text = re.sub(r"(?i)Bookmark this [Cc]ase\s*", "", text)
    text = re.sub(r"(?i)Head Notes on Cases With Complete Judgements\s*", "", text)
    # Strip trailing next-case / PLD citation navigation line
    text = re.sub(r"\n+(?:PLD|SCMR|CLC|PCrLJ|PTD|MLD|YLR|CLD),\d{4},\d+,\d+.*$", "", text, flags=re.DOTALL)
    # Strip footer artifacts
    text = re.sub(r"(?i)Copyrights?\s*©?[^\n]*Oratier Technologies[^\n]*", "", text)
    text = re.sub(r"(?i)This site is developed\s*&?\s*maintained[^\n]*", "", text)
    text = re.sub(r"(?i)Help\s+FAQ\'?s\s+Sitemap", "", text)
    text = re.sub(r"(?i)Print this Judgment", "", text)
    text = re.sub(r"(?i)Download PDF", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    # Strip trailing "VS" / "versus" stub at the very end
    text = re.sub(r"(?i)\n+VS\.?\s*$", "", text).strip()
    return text



def resolve_court_metadata(citation: str, court_raw: str, case_title: str, case_id: str, text: str = "", raw_text: str = "") -> str:
    """Resolve canonical court name without generic 'Court of Record' placeholders."""
    cit_u = (citation or "").upper()
    cid_u = (case_id or "").upper()

    # --- 1. PORTAL LINE PRIORITY: Scraper Citation Name directly specifies court ---
    # Portal line takes precedence over all heuristics (e.g. FCC judgments published in SCMR or PLD)
    portal_line = ""
    if raw_text:
        search_raw = f"{raw_text[:2500]} {raw_text[-2500:]}"
        m_cit = re.search(r"(?i)Citation Name:\s*([^\n]+)", search_raw)
        if m_cit:
            portal_line = m_cit.group(1).upper()

    if portal_line:
        # Pre-partition / foreign jurisdictions in early PLD
        if any(k in portal_line for k in ["SUPREME-COURT-INDIA", "SUPREME COURT OF INDIA", "CALCUTTA", "ALLAHABAD", "BOMBAY", "MADRAS", "NAGPUR", "PATNA"]):
            return "UNRESOLVED"
        if "FEDERAL-CONSTITUTIONAL-COURT" in portal_line or "FEDERAL CONSTITUTIONAL COURT" in portal_line:
            return "Federal Constitutional Court"
        if "SUPREME-COURT-AZAD-KASHMIR" in portal_line or "SUPREME COURT AZAD KASHMIR" in portal_line:
            return "Supreme Court of Azad Jammu & Kashmir"
        if "HIGH-COURT-AZAD-KASHMIR" in portal_line or "HIGH COURT AZAD KASHMIR" in portal_line:
            return "High Court of Azad Jammu & Kashmir"
        if "SUPREME-COURT" in portal_line or "SUPREME COURT" in portal_line:
            return "Supreme Court of Pakistan"
        if "LAHORE-HIGH-COURT" in portal_line or "LAHORE" in portal_line:
            return "Lahore High Court"
        if "SINDH-HIGH-COURT" in portal_line or "KARACHI" in portal_line:
            return "High Court of Sindh"
        if "PESHAWAR-HIGH-COURT" in portal_line or "PESHAWAR" in portal_line:
            return "Peshawar High Court"
        if "BALOCHISTAN-HIGH-COURT" in portal_line or "QUETTA" in portal_line:
            return "High Court of Balochistan"
        if "ISLAMABAD-HIGH-COURT" in portal_line or "ISLAMABAD" in portal_line:
            return "Islamabad High Court"
        if "FEDERAL-SHARIAT-COURT" in portal_line:
            return "Federal Shariat Court"
        if "PRIVY-COUNCIL" in portal_line:
            return "Privy Council"
        if "FEDERAL-COURT" in portal_line:
            return "Federal Court of Pakistan"
        if "BOARD-OF-REVENUE" in portal_line or "REVENUE" in portal_line:
            return "Board of Revenue"

    # --- 1B. EARLY PRINT VOLUME HEADING PRIORITY ---
    # In early PLD volumes (1947-1980), the print section header explicitly states the bench:
    # e.g. "P L D 1967 Supreme Court 97" or "P L D 1958 Lahore 138"
    print_search = f"{citation} {case_id} {raw_text[:2500]} {text[:2500]}".upper()
    if re.search(r"(?i)(?:P\s*L\s*D|SCMR)\s+\d{4}\s+(?:Supreme\s+Court|SC)\b", print_search):
        return "Supreme Court of Pakistan"
    if re.search(r"(?i)(?:P\s*L\s*D)\s+\d{4}\s+(?:Lahore|Lah)\b", print_search):
        return "Lahore High Court"
    if re.search(r"(?i)(?:P\s*L\s*D)\s+\d{4}\s+(?:Karachi|Kar|Sindh)\b", print_search):
        return "High Court of Sindh"
    if re.search(r"(?i)(?:P\s*L\s*D)\s+\d{4}\s+(?:Peshawar|Pesh)\b", print_search):
        return "Peshawar High Court"
    if re.search(r"(?i)(?:P\s*L\s*D)\s+\d{4}\s+(?:Quetta|Qta)\b", print_search):
        return "High Court of Balochistan"
    if re.search(r"(?i)(?:P\s*L\s*D)\s+\d{4}\s+(?:Dacca|Dhaka)\b", print_search):
        return "Dhaka High Court"
    if re.search(r"(?i)(?:P\s*L\s*D)\s+\d{4}\s+(?:Federal\s+Court|FC)\b", print_search):
        return "Federal Court of Pakistan"
    if re.search(r"(?i)(?:P\s*L\s*D)\s+\d{4}\s+(?:Privy\s+Council|PC)\b", print_search):
        return "Privy Council"

    # --- 2. HARD CHECK: SCMR is Supreme Court of Pakistan (or AJ&K SC) ONLY ---
    # SCMR reports exclusively Supreme Court judgments.
    if "SCMR" in cit_u or "SCMR" in cid_u:
        combined_scmr_check = f"{citation} {court_raw} {case_title} {case_id} {raw_text[:400]}".upper()
        if any(k in combined_scmr_check for k in ["AJ&K", "AZAD KASHMIR", "AJK", "AZAD JAMMU"]):
            return "Supreme Court of Azad Jammu & Kashmir"
        return "Supreme Court of Pakistan"

    # --- 3. Build sanitized haystack for fallback resolution ---
    # Strip publisher address and phone numbers to eliminate the Nabha Road bug
    safe_text = re.sub(r"(?i)(?:35-?\s*Nabha\s*Road[^\n]*|PLD\s+Publishers[^\n]*|Customer\s+Care[^\n]*|info@pakistanlawsite\.com)", "", text[:400])
    haystack = f"{citation} {court_raw} {case_title} {case_id} {portal_line} {safe_text}".upper()
    haystack = re.sub(r"(?i)35-?\s*NABHA\s*ROAD[^\n]*", "", haystack)

    # Foreign / pre-partition jurisdictions in early PLD (keep neutral 1.0x)
    if any(k in haystack for k in ["SUPREME-COURT-INDIA", "SUPREME COURT OF INDIA", "CALCUTTA", "ALLAHABAD", "BOMBAY", "MADRAS", "NAGPUR", "PATNA"]):
        return "UNRESOLVED"

    # Federal Constitutional Court in fallback text
    if any(k in haystack for k in ["FEDERAL CONSTITUTIONAL COURT", "FEDERAL-CONSTITUTIONAL-COURT", "FCC"]):
        return "Federal Constitutional Court"

    # Azad Kashmir
    if any(k in haystack for k in ["AZAD JAMMU AND KASHMIR", "AZAD KASHMIR", "AJ&K", "AJK", "MUZAFFARABAD", "MIRPUR"]):
        if "SUPREME" in haystack:
            return "Supreme Court of Azad Jammu & Kashmir"
        return "High Court of Azad Jammu & Kashmir"

    # Supreme Court indicators
    if any(k in haystack for k in ["SUPREME COURT OF PAKISTAN", "SUPREME-COURT", "PLD SC", "PLD_SC_"]):
        return "Supreme Court of Pakistan"
    if "SUPREME COURT" in haystack and not any(k in haystack for k in ["HIGH COURT", "INDIA"]):
        return "Supreme Court of Pakistan"

    # Provincial High Courts
    if any(k in haystack for k in ["LAHORE-HIGH-COURT", "LAHORE HIGH COURT", "HIGH COURT LAHORE", "LHC", "_LAH_"]):
        return "Lahore High Court"
    if "LAHORE" in court_raw.upper() or "LAHORE" in case_title.upper():
        return "Lahore High Court"

    if any(k in haystack for k in ["KARACHI", "SINDH", "SHC", "_KAR_"]):
        return "High Court of Sindh"
    if any(k in haystack for k in ["PESHAWAR", "PHC", "_PESH_"]):
        return "Peshawar High Court"
    if any(k in haystack for k in ["QUETTA", "BALOCHISTAN", "BHC", "_QTA_"]):
        return "High Court of Balochistan"
    if any(k in haystack for k in ["ISLAMABAD", "IHC", "_ISL_"]):
        return "Islamabad High Court"
    if any(k in haystack for k in ["FEDERAL SHARIAT", "FSC"]):
        return "Federal Shariat Court"
    if any(k in haystack for k in ["DHAKA", "DACCA", "EAST BENGAL", "EAST PAKISTAN"]):
        return "Dhaka High Court"
    if any(k in haystack for k in ["PRIVY COUNCIL", "PRIVY-COUNCIL"]):
        return "Privy Council"
    if any(k in haystack for k in ["FEDERAL COURT", "FEDERAL-COURT"]):
        return "Federal Court of Pakistan"
    if any(k in haystack for k in ["BOARD OF REVENUE", "REVENUE DECISION", "WEST-PAKISTAN-BOARD"]):
        return "Board of Revenue"

    # Bare "LAHORE" match in body text only if associated with high court or bench
    if re.search(r'\b(?:AT|BENCH|CIRCUIT|IN)\s+LAHORE\b', haystack):
        return "Lahore High Court"

    if "SC" in cit_u:
        return "Supreme Court of Pakistan"

    return "UNRESOLVED"


def clean_or_extract_title(case_title: str, raw_text: str = "") -> str:
    """Cleans OCR digit intrusions and extracts fallback title if case_title is a leaked statutory header."""
    title = (case_title or "").strip()

    is_leaked = (
        not title or
        title in ("Reported Precedent", "Untitled Case", "Precedent on Record") or
        bool(re.match(r'^(?:s\.|section|art\.|article|order|o\.|rule|r\.|dated|form)\s*\d*', title, re.IGNORECASE))
    )

    if is_leaked and raw_text:
        m = re.search(r'(?:Bookmark this Case\s*|Citation Name:[^\n]*)\n+([A-Z0-9\s,\.\(\)\/-]+?\s+(?:VS|V\.)\s+[A-Z0-9\s,\.\(\)\/-]+?)(?:\n|Civil|Criminal|Constitution|Appellate|\Z)', raw_text[:2000], re.IGNORECASE)
        if m:
            extracted = m.group(1).strip()
            extracted = re.sub(r'\s*-\s*[A-Z\-]+(?:COURT|HIGH-COURT)[A-Z\-]*', '', extracted, flags=re.IGNORECASE)
            title = extracted

    # Clean intra-word OCR digit intrusions
    title = re.sub(r'(?<=[A-Za-z])1(?=[A-Za-z])', 'i', title)
    title = re.sub(r'(?<=[A-Za-z])1\b', 'i', title)
    title = re.sub(r'\b1(?=[A-Za-z]{3,})', '', title)
    title = re.sub(r'(?<=[A-Za-z])0(?=[A-Za-z])', 'o', title)
    title = re.sub(r'\s*-\s*(?:[A-Za-z\-]+(?:COURT|HIGH-COURT)|Lahore|Karachi|Peshawar|Quetta|Dhaka)[A-Za-z\-]*\s*$', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'^(?:Bookmark this Case|Citation Name:[^\n]*)\s*', '', title, flags=re.IGNORECASE).strip()
    return title or "Reported Precedent"



def classify_content_type(cleaned_text: str, token_count: int) -> str:
    """Classify judgment into 'full_text' vs 'headnote_only'."""
    txt_lower = cleaned_text.lower()
    full_markers = [
        "heard the learned counsel", "for the petitioner", "for the respondent",
        "for the appellant", "order of the court", "we have heard", "per curiam",
        "impugned judgment", "impugned order", "reappraisal of evidence",
        "appeal is allowed", "appeal is dismissed", "petition is dismissed",
        "leave to appeal is granted", "leave is refused", "judgment reserved",
        "announced in open court", "c.j.---", "j.---"
    ]
    has_marker = any(m in txt_lower for m in full_markers)
    if token_count >= 800 and has_marker:
        return "full_text"
    if token_count >= 1500:
        return "full_text"
    return "headnote_only"


def format_court_citation(raw_citation: str, court: str, year: int, case_id: str) -> str:
    """
    Construct standardized, court-qualified citation string.
    Ensures court abbreviation is properly represented (e.g. PLD 1958 SC 138, PLD 2026 FCC 94, 2026 SCMR 905).
    """
    raw_cit = (raw_citation or "").strip()
    c_upper = (court or "").upper()

    # If SCMR, it is Supreme Court of Pakistan unless AJK
    if "SCMR" in raw_cit.upper() or "SCMR" in case_id.upper():
        if "AZAD" in c_upper or "AJK" in c_upper:
            return f"{raw_cit} (AJ&K)"
        return raw_cit

    # If PLD, extract year and page
    if "PLD" in raw_cit.upper() or "PLD" in case_id.upper():
        # Check if already has court abbreviation (e.g. "PLD 1958 SC 138" or "PLD 2024 Lah 295")
        if re.search(r'\bPLD\s+(?:19|20)\d{2}\s+[A-Za-z&]+\s+\d+\b', raw_cit, re.IGNORECASE):
            return raw_cit

        m_page = re.search(r'\b(\d+)\s*$', raw_cit) or re.search(r'_(\d+)$', case_id)
        page = m_page.group(1) if m_page else ""
        y = year if (year and year > 1900) else extract_year(raw_cit, case_id)

        c_tag = ""
        if "FEDERAL CONSTITUTIONAL COURT" in c_upper: c_tag = "FCC"
        elif "SUPREME COURT OF AZAD" in c_upper or "AJK SC" in c_upper: c_tag = "AJ&K SC"
        elif "HIGH COURT OF AZAD" in c_upper or "AJK HC" in c_upper: c_tag = "AJ&K HC"
        elif "SUPREME COURT" in c_upper: c_tag = "SC"
        elif "LAHORE" in c_upper: c_tag = "Lah"
        elif "SINDH" in c_upper or "KARACHI" in c_upper: c_tag = "Kar"
        elif "PESHAWAR" in c_upper: c_tag = "Pesh"
        elif "BALOCHISTAN" in c_upper or "QUETTA" in c_upper: c_tag = "Quetta"
        elif "ISLAMABAD" in c_upper: c_tag = "Isl"
        elif "FEDERAL SHARIAT" in c_upper: c_tag = "FSC"
        elif "DHAKA" in c_upper or "DACCA" in c_upper or "EAST" in c_upper: c_tag = "Dacca"
        elif "PRIVY COUNCIL" in c_upper: c_tag = "PC"
        elif "FEDERAL COURT" in c_upper: c_tag = "FC"
        elif "BOARD OF REVENUE" in c_upper or "REVENUE" in c_upper: c_tag = "Rev"

        if c_tag and page and y:
            return f"PLD {y} {c_tag} {page}"
        if page and y:
            return f"{y} PLD {page}"

    return raw_cit or case_id


def chunk_judgment_text(
    text: str,
    citation: str,
    title: str,
    target_tokens: int = 512,
    overlap_tokens: int = 64
) -> List[Tuple[str, int]]:
    """
    Split text into 512-token segments with 64-token overlap.
    Prepends context header '[citation | title]' to each chunk.
    Returns list of (chunk_text, token_count).
    """
    if not text:
        return []

    tokens = tokenizer.encode(text)
    if not tokens:
        return []

    header_text = f"[{citation} | {title}]\n\n"
    header_tokens = tokenizer.encode(header_text)
    max_body_tokens = max(100, target_tokens - len(header_tokens))

    chunks: List[Tuple[str, int]] = []
    step = max_body_tokens - overlap_tokens
    if step <= 0:
        step = max_body_tokens

    for start_idx in range(0, len(tokens), step):
        body_slice = tokens[start_idx : start_idx + max_body_tokens]
        if not body_slice:
            break
        body_text = tokenizer.decode(body_slice)
        chunk_full_text = header_text + body_text
        chunk_token_count = len(header_tokens) + len(body_slice)
        chunks.append((chunk_full_text, chunk_token_count))

        if start_idx + max_body_tokens >= len(tokens):
            break

    return chunks


def embed_batch_with_retry(
    texts: List[str],
    max_retries: int = 15,
    initial_delay: float = 3.0
) -> List[List[float]]:
    """
    Call Voyage API to embed batch of texts (max 64 per batch)
    with exponential backoff on HTTP 429 rate limits.
    """
    headers = {
        "Authorization": f"Bearer {VOYAGE_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "input": texts,
        "model": VOYAGE_MODEL,
        "input_type": "document"
    }

    delay = initial_delay
    for attempt in range(max_retries):
        try:
            resp = requests.post(VOYAGE_API_URL, json=payload, headers=headers, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                return [item["embedding"] for item in data["data"]]
            elif resp.status_code in (429, 500, 502, 503, 504):
                print(f"  [Voyage HTTP {resp.status_code}] Rate limited/unavailable. Retrying in {delay:.1f}s (attempt {attempt+1}/{max_retries})...", flush=True)
                time.sleep(delay)
                delay = min(delay * 1.5, 60.0)
            else:
                raise RuntimeError(f"Voyage API Error {resp.status_code}: {resp.text}")
        except requests.exceptions.RequestException as e:
            print(f"  [Voyage Network Error] {e}. Retrying in {delay:.1f}s (attempt {attempt+1}/{max_retries})...", flush=True)
            time.sleep(delay)
            delay = min(delay * 1.5, 60.0)

    raise RuntimeError(f"Failed to embed batch with Voyage API after {max_retries} attempts.")


def upsert_pinecone_with_retry(
    pinecone_index: Any,
    vectors_payload: List[Dict[str, Any]],
    namespace: str,
    max_retries: int = 15,
    initial_delay: float = 3.0
) -> None:
    """Upsert vectors into Pinecone with retry backoff."""
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            pinecone_index.upsert(vectors=vectors_payload, namespace=namespace)
            return
        except Exception as e:
            print(f"  [Pinecone Upsert Warning] {e}. Retrying in {delay:.1f}s (attempt {attempt+1}/{max_retries})...", flush=True)
            time.sleep(delay)
            delay = min(delay * 1.5, 60.0)

    raise RuntimeError(f"Failed to upsert to Pinecone after {max_retries} attempts.")


def run_pipeline(limit: int = 100, is_dry_run: bool = True, stratified_200: bool = False, pause_at: int = 0):
    print("=" * 70)
    if pause_at > 0:
        mode_str = f"PRODUCTION RUN (PAUSING AT {pause_at:,} JUDGMENTS FOR SPOT CHECK)"
    elif stratified_200:
        mode_str = "STRATIFIED DRY RUN (200 JUDGMENTS: 25/DECADE)"
    elif is_dry_run:
        mode_str = f"DRY RUN ({limit} JUDGMENTS)"
    else:
        mode_str = f"FULL PRODUCTION RUN ({limit} JUDGMENTS)"
    print(f"PHASE 2A VECTOR INDEXING: {mode_str}")
    print("=" * 70)

    # Initialize skipped_stubs.csv if not exists
    if not os.path.exists(SKIPPED_STUBS_PATH):
        with open(SKIPPED_STUBS_PATH, "w", encoding="utf-8") as sf:
            sf.write("case_id,citation,token_count\n")

    # 1. Initialize Clients
    if not VOYAGE_API_KEY:
        raise ValueError("Missing VOYAGE_API_KEY in environment.")
    if not PINECONE_API_KEY:
        raise ValueError("Missing PINECONE_API_KEY in environment.")
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise ValueError("Missing Supabase credentials in environment.")

    print(f"Embedding Model: {VOYAGE_MODEL} (1024 dims)")
    print(f"Pinecone Index: {PINECONE_INDEX_NAME} (Namespace: '{PINECONE_NAMESPACE}')")
    print(f"Supabase Host: {SUPABASE_URL}")

    sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    pc = Pinecone(api_key=PINECONE_API_KEY)
    pinecone_index = None
    for attempt in range(5):
        try:
            if PINECONE_HOST:
                pinecone_index = pc.Index(PINECONE_INDEX_NAME, host=PINECONE_HOST)
            else:
                pinecone_index = pc.Index(PINECONE_INDEX_NAME)
            break
        except Exception as init_err:
            print(f"Warning: Pinecone connection attempt {attempt+1} failed ({init_err}). Retrying in 2s...")
            time.sleep(2.0)
    if not pinecone_index:
        raise RuntimeError("Failed to connect to Pinecone index.")

    # 2. Load Reindex Queue & Checkpoint
    if not os.path.exists(REINDEX_QUEUE_PATH):
        raise FileNotFoundError(f"Missing reindex queue at {REINDEX_QUEUE_PATH}")

    with open(REINDEX_QUEUE_PATH, "r", encoding="utf-8") as f:
        full_queue: List[str] = json.load(f)

    checkpoint = load_checkpoint()
    print(f"Total case_ids in queue: {len(full_queue):,}", flush=True)
    print(f"Already completed in checkpoint: {len(checkpoint):,}", flush=True)

    unprocessed = [cid for cid in full_queue if cid not in checkpoint]
    print(f"Remaining unprocessed case_ids: {len(unprocessed):,}", flush=True)

    if not unprocessed:
        print("All case_ids in queue are already completed!", flush=True)
        return

    # Slice for this run
    if pause_at > 0:
        batch_target = unprocessed[:pause_at]
        print(f"\nTargeting next {len(batch_target):,} judgments (Pausing at {pause_at:,} for spot check)...", flush=True)
    elif stratified_200:
        random.seed(42)
        decades = {
            "1950s": [c for c in unprocessed if re.search(r"195\d", c)],
            "1960s": [c for c in unprocessed if re.search(r"196\d", c)],
            "1970s": [c for c in unprocessed if re.search(r"197\d", c)],
            "1980s": [c for c in unprocessed if re.search(r"198\d", c)],
            "1990s": [c for c in unprocessed if re.search(r"199\d", c)],
            "2000s": [c for c in unprocessed if re.search(r"200\d", c)],
            "2010s": [c for c in unprocessed if re.search(r"201\d", c)],
            "2020s": [c for c in unprocessed if re.search(r"202\d", c)],
        }
        batch_target = []
        for dec_name, dec_cids in decades.items():
            sample = random.sample(dec_cids, min(25, len(dec_cids)))
            batch_target.extend(sample)
        print(f"Stratified sample created: {len(batch_target)} cases across 8 decades (25/decade).", flush=True)
    else:
        batch_target = unprocessed[:limit]
        print(f"\nTargeting next {len(batch_target):,} judgments for processing...", flush=True)

    # Performance & Content Metrics
    total_judgments_processed = 0
    total_chunks_created = 0
    total_tokens_embedded = 0
    stubs_skipped = 0
    content_type_counts = {"headnote_only": 0, "full_text": 0}
    court_resolved_counts: Dict[str, int] = {}
    supabase_backfilled_count = 0
    voyage_api_calls = 0
    total_voyage_time = 0.0
    total_pinecone_time = 0.0
    total_fetch_time = 0.0

    t_start = time.time()

    # Process in batches of 25 judgments from Supabase
    SUPABASE_CHUNK_SIZE = 25
    for i in range(0, len(batch_target), SUPABASE_CHUNK_SIZE):
        sub_batch_ids = batch_target[i : i + SUPABASE_CHUNK_SIZE]

        for sub_retry_idx in range(10):
            try:
                # 3. Fetch from Supabase
                t_f0 = time.time()
                res = sb.table("full_judgments").select(
                    "id, case_id, neutral_citation, case_title, court_name, decision_date, full_text"
                ).in_("case_id", sub_batch_ids).execute()
                total_fetch_time += (time.time() - t_f0)

                rows = res.data or []
                if not rows:
                    print(f"Warning: No Supabase rows returned for sub-batch {sub_batch_ids[:3]}...", flush=True)
                    break

                # Map rows
                row_dict = {r["case_id"]: r for r in rows if r.get("case_id")}

                # 4. Chunk each judgment
                batch_chunks: List[Dict[str, Any]] = []
                successful_case_ids: List[str] = []

                for cid in sub_batch_ids:
                    item = row_dict.get(cid)
                    if not item:
                        continue

                    raw_text = (item.get("full_text") or "").strip()
                    cleaned_text = clean_portal_boilerplate(raw_text)
                    tok_count = len(tokenizer.encode(cleaned_text))

                    # Stub filter: <50 tokens
                    if tok_count < MIN_CLEAN_TOKENS:
                        stubs_skipped += 1
                        successful_case_ids.append(cid)
                        with open(SKIPPED_STUBS_PATH, "a", encoding="utf-8") as sf:
                            sf.write(f'"{cid}","{item.get("neutral_citation") or cid}",{tok_count}\n')
                        continue

                    supabase_id = str(item.get("id"))
                    case_title = clean_or_extract_title(item.get("case_title"), raw_text)
                    raw_court = (item.get("court_name") or "").strip()
                    raw_cit = (item.get("neutral_citation") or cid).strip()
                    court = resolve_court_metadata(
                        citation=raw_cit,
                        court_raw=raw_court,
                        case_title=case_title,
                        case_id=cid,
                        text=cleaned_text[:2500],
                        raw_text=raw_text
                    )
                    court_resolved_counts[court] = court_resolved_counts.get(court, 0) + 1

                    # Auto-backfill Supabase if court was missing/unidentified and now resolved
                    if raw_court in ("", "Court not identified", "Court of Record") and court != "Court of Record":
                        try:
                            sb.table("full_judgments").update({"court_name": court, "court_name_raw": raw_court}).eq("case_id", cid).execute()
                            supabase_backfilled_count += 1
                        except Exception:
                            pass

                    # Chunking
                    c_type = "headnote_only" if tok_count < 300 else "full_text"
                    content_type_counts[c_type] = content_type_counts.get(c_type, 0) + 1

                    judgment_chunks = chunk_judgment_text(cleaned_text, raw_cit, case_title)
                    num_chunks = len(judgment_chunks)

                    for chunk_idx, (chk_text, chk_tok_count) in enumerate(judgment_chunks):
                        chk_id = f"{cid}#c{chunk_idx+1}"
                        batch_chunks.append({
                            "id": chk_id,
                            "text": chk_text,
                            "tokens": chk_tok_count,
                            "metadata": {
                                "case_id": cid,
                                "canonical_id": cid,
                                "supabase_id": supabase_id,
                                "citation": raw_cit,
                                "title": case_title,
                                "court": court,
                                "court_name": court,
                                "court_normalized": court,
                                "date": str(item.get("decision_date") or "")[:4],
                                "year": str(item.get("decision_date") or "")[:4],
                                "chunk_index": chunk_idx,
                                "total_chunks": num_chunks,
                                "content_type": c_type,
                                "token_count": chk_tok_count
                            }
                        })

                    successful_case_ids.append(cid)

                if not batch_chunks:
                    append_checkpoint(successful_case_ids)
                    break

                # 5. Embed with Voyage (Max 64 per batch)
                VOYAGE_BATCH_SIZE = 64
                all_embeddings: List[List[float]] = []

                for c_idx in range(0, len(batch_chunks), VOYAGE_BATCH_SIZE):
                    chunk_slice = batch_chunks[c_idx : c_idx + VOYAGE_BATCH_SIZE]
                    texts_to_embed = [c["text"] for c in chunk_slice]
                    tokens_in_slice = sum(c["tokens"] for c in chunk_slice)

                    t_v0 = time.time()
                    embs = embed_batch_with_retry(texts_to_embed)
                    call_time = time.time() - t_v0

                    total_voyage_time += call_time
                    voyage_api_calls += 1
                    total_tokens_embedded += tokens_in_slice
                    all_embeddings.extend(embs)

                # 6. Upsert to Pinecone (Max 100 per upsert)
                PINECONE_BATCH_SIZE = 100
                vectors_to_upsert = []
                for chk_obj, emb in zip(batch_chunks, all_embeddings):
                    vectors_to_upsert.append({
                        "id": chk_obj["id"],
                        "values": emb,
                        "metadata": chk_obj["metadata"]
                    })

                for p_idx in range(0, len(vectors_to_upsert), PINECONE_BATCH_SIZE):
                    p_slice = vectors_to_upsert[p_idx : p_idx + PINECONE_BATCH_SIZE]
                    t_p0 = time.time()
                    upsert_pinecone_with_retry(pinecone_index, p_slice, namespace=PINECONE_NAMESPACE)
                    total_pinecone_time += (time.time() - t_p0)

                # 7. Checkpoint
                append_checkpoint(successful_case_ids)
                total_judgments_processed += len(successful_case_ids)
                total_chunks_created += len(batch_chunks)
                now_elapsed = time.time() - t_start
                pct = (total_judgments_processed / max(len(batch_target), 1)) * 100.0
                sec_per_item = now_elapsed / max(total_judgments_processed, 1)
                remaining_sec = sec_per_item * (len(batch_target) - total_judgments_processed)
                eta_str = f"{remaining_sec / 3600.0:.2f}h" if remaining_sec >= 3600 else f"{remaining_sec / 60.0:.1f}m"

                print(
                    f"[{pct:5.1f}%] Processed {total_judgments_processed:5d}/{len(batch_target):5d} judgments "
                    f"| Chunks: {total_chunks_created:6d} "
                    f"| Rate: {total_judgments_processed / max(now_elapsed, 0.001):.2f} j/s "
                    f"| Elapsed: {now_elapsed / 60.0:5.1f}m "
                    f"| ETA: {eta_str}",
                    flush=True
                )
                break
            except Exception as batch_err:
                print(f"[WARN] [Sub-Batch Error] {batch_err}. Re-establishing connections and retrying in 20s (attempt {sub_retry_idx+1}/10)...", flush=True)
                time.sleep(20.0)
                try:
                    pc = Pinecone(api_key=PINECONE_API_KEY)
                    if PINECONE_HOST:
                        pinecone_index = pc.Index(PINECONE_INDEX_NAME, host=PINECONE_HOST)
                    else:
                        pinecone_index = pc.Index(PINECONE_INDEX_NAME)
                    sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
                except Exception as rec_err:
                    print(f"  [Reconnect Warning] {rec_err}", flush=True)

    total_elapsed = time.time() - t_start

    print("\n" + "=" * 70)
    print("PHASE 2A RUN COMPLETED -- PERFORMANCE & LATENCY REPORT")
    print("=" * 70)
    print(f"Total Judgments Processed   : {total_judgments_processed:,}")
    print(f"Stubs Skipped (<50 tokens)  : {stubs_skipped:,}")
    print(f"Total Chunks Vectorized     : {total_chunks_created:,} vectors")
    print(f"Avg Chunks / Processed Jdg  : {total_chunks_created / max(total_judgments_processed - stubs_skipped, 1):.2f}")
    print(f"Total Tokens Embedded       : {total_tokens_embedded:,} tokens")
    print(f"Content Type Breakdown      : {content_type_counts}")
    print(f"Resolved Courts Breakdown   : {court_resolved_counts}")
    print(f"Supabase Courts Backfilled  : {supabase_backfilled_count}")
    print(f"Supabase Fetch Time         : {total_fetch_time:.2f}s ({total_fetch_time / max(total_judgments_processed, 1):.3f}s / judgment)")
    print(f"Voyage Embedding Time       : {total_voyage_time:.2f}s ({voyage_api_calls} API calls, {total_voyage_time / max(voyage_api_calls, 1):.3f}s / call)")
    print(f"Pinecone Upsert Time        : {total_pinecone_time:.2f}s")
    print(f"Total Elapsed Time          : {total_elapsed:.2f}s")
    print(f"Overall Throughput          : {total_judgments_processed / max(total_elapsed, 0.001):.2f} judgments/s | {total_chunks_created / max(total_elapsed, 0.001):.2f} chunks/s")

    # Extrapolation for remaining judgments
    remaining = len(unprocessed) - total_judgments_processed
    if total_judgments_processed > 0 and remaining > 0:
        sec_per_judgment = total_elapsed / total_judgments_processed
        est_remaining_sec = sec_per_judgment * remaining
        est_hours = est_remaining_sec / 3600.0
        print("\n--- Extrapolation for Remaining Queue (Full Run) ---")
        print(f"Remaining Judgments         : {remaining:,}")
        print(f"Estimated Total Vectors     : {int(remaining * (total_chunks_created / max(total_judgments_processed - stubs_skipped, 1))):,}")
        print(f"Estimated Time to Complete  : {est_hours:.2f} hours ({est_remaining_sec / 60:.1f} minutes)")

    print("\n[OK] Local checkpoint updated in indexing_checkpoint.log.")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 2A Vector Indexer")
    parser.add_argument("--limit", type=int, default=100, help="Number of judgments to process in this run")
    parser.add_argument("--stratified-200", action="store_true", help="Run stratified dry run with 25 cases from each of 8 decades")
    parser.add_argument("--pause-at", type=int, default=0, help="Pause after processing this number of judgments for spot check")
    parser.add_argument("--production", action="store_true", help="Set flag for continuous production run")
    args = parser.parse_args()

    run_pipeline(limit=args.limit, is_dry_run=(not args.production and args.pause_at == 0), stratified_200=args.stratified_200, pause_at=args.pause_at)

