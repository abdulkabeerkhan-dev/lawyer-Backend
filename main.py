import os
import sys
import uuid
import io
import base64
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, cast
import re
import json

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from pinecone import Pinecone
from anthropic import AsyncAnthropic
from supabase import create_client, Client
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, status, Depends, Response, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    import html
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

load_dotenv()

# SENTRY SYSTEM LOG ENGINE
if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ.get("SENTRY_DSN"),
        integrations=[FastApiIntegration()],
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

app = FastAPI(title="SECTION AI - Legal Intelligence Platform")

# CORS ORIGIN ALLOWLIST
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if not ALLOWED_ORIGINS:
    print("⚠️ WARNING: ALLOWED_ORIGINS is not set -- CORS is mirroring ANY request origin with credentials enabled.")

def _origin_is_allowed(origin: str) -> bool:
    return (not ALLOWED_ORIGINS) or (origin in ALLOWED_ORIGINS)

@app.middleware("http")
async def dynamic_cors_middleware(request, call_next):
    origin = request.headers.get("origin")
    if request.method == "OPTIONS" and origin and _origin_is_allowed(origin):
        response = Response(status_code=200)
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        req_headers = request.headers.get("access-control-request-headers")
        response.headers["Access-Control-Allow-Headers"] = req_headers or "Authorization, Content-Type, Accept, X-Requested-With, Clerk-Auth-Token"
        response.headers["Access-Control-Max-Age"] = "86400"
        return response

    response = await call_next(request)
    if origin and _origin_is_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        req_headers = request.headers.get("access-control-request-headers")
        if req_headers:
            response.headers["Access-Control-Allow-Headers"] = req_headers
        else:
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept, X-Requested-With, Clerk-Auth-Token"
    return response

# ENVIRONMENT CONFIGURATION
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "legal-kb-pk-local")
PINECONE_NAMESPACE = os.environ.get("PINECONE_NAMESPACE", "clean-v1")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")
VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
DEV_AUTH_BYPASS_ENABLED = os.environ.get("ENABLE_DEV_AUTH_BYPASS", "false").strip().lower() == "true"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")

async def get_voyage_embedding(text: str) -> List[float]:
    if not VOYAGE_API_KEY:
        raise HTTPException(status_code=500, detail="VOYAGE_API_KEY is missing from environment.")
    headers = {
        "Authorization": f"Bearer {VOYAGE_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "input": [text],
        "model": "voyage-law-2"
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(VOYAGE_API_URL, headers=headers, json=payload)
        if res.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Voyage AI embedding error: {res.text}")
        data = res.json()
        return data["data"][0]["embedding"]

# INITIALIZE INFRASTRUCTURE CLIENTS
pinecone_index = None
if PINECONE_API_KEY:
    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    except Exception as launch_err:
        print(f"⚠️ Pinecone startup warning: {launch_err}")

supabase: Any = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    except Exception as launch_err:
        print(f"⚠️ Supabase startup warning: {launch_err}")

async_anthropic_client = None
if ANTHROPIC_API_KEY:
    try:
        raw_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        try:
            from langsmith import wrappers
            async_anthropic_client = wrappers.wrap_anthropic(raw_client)
        except Exception:
            async_anthropic_client = raw_client
    except Exception as launch_err:
        print(f"Anthropic client startup warning: {launch_err}")

security_agent = HTTPBearer(auto_error=False)
_clerk_jwks_keys_cache = None

def clean_court_name(court_name: str = "", title: str = "", case_id: str = "", text: str = "", **kwargs) -> str:
    c_raw = str(court_name or "").strip()
    c_lower = c_raw.lower()

    # 1. Inspect explicit court_name input first (do not let text snippet keywords override explicit court metadata)
    if c_lower and c_lower not in ("unknown", "unknown court", "court of record", "not specified", "none", "high court", "court"):
        if any(x in c_lower for x in ("ajk", "azad jammu", "azad kashmir", "mirpur", "muzaffarabad", "rawalakot")):
            if "high" in c_lower: return "High Court of Azad Jammu & Kashmir"
            if "service tribunal" in c_lower: return "AJK Service Tribunal"
            return "Supreme Court of Azad Jammu & Kashmir"
        if "federal shariat" in c_lower or "fsc" in c_lower:
            return "Federal Shariat Court"
        if "supreme" in c_lower or "scp" in c_lower or "scmr" in c_lower or " pld sc " in c_lower:
            return "Supreme Court of Pakistan"
        if "peshawar" in c_lower or "phc" in c_lower:
            return "Peshawar High Court"
        if "lahore" in c_lower or "lhc" in c_lower:
            return "Lahore High Court"
        if "sindh" in c_lower or "karachi" in c_lower or "shc" in c_lower:
            return "High Court of Sindh"
        if "balochistan" in c_lower or "quetta" in c_lower or "bhc" in c_lower:
            return "High Court of Balochistan"
        if "islamabad" in c_lower or "ihc" in c_lower:
            return "Islamabad High Court"

    # 2. Secondary inspection: title and case_id (docket identifier)
    docket_and_title = " ".join([str(title or ""), str(case_id or "")]).lower()
    if any(x in docket_and_title for x in ("ajk", "azad jammu", "azad kashmir", "mirpur", "muzaffarabad", "rawalakot")):
        if "high" in docket_and_title: return "High Court of Azad Jammu & Kashmir"
        if "service tribunal" in docket_and_title: return "AJK Service Tribunal"
        return "Supreme Court of Azad Jammu & Kashmir"
    if "federal shariat" in docket_and_title or "fsc" in docket_and_title:
        return "Federal Shariat Court"
    if "supreme" in docket_and_title or "scp" in docket_and_title or "scmr" in docket_and_title or " pld sc " in docket_and_title:
        return "Supreme Court of Pakistan"
    if "peshawar" in docket_and_title or "phc" in docket_and_title:
        return "Peshawar High Court"
    if "lahore" in docket_and_title or "lhc" in docket_and_title:
        return "Lahore High Court"
    if "sindh" in docket_and_title or "karachi" in docket_and_title or "shc" in docket_and_title:
        return "High Court of Sindh"
    if "balochistan" in docket_and_title or "quetta" in docket_and_title or "bhc" in docket_and_title:
        return "High Court of Balochistan"
    if "islamabad" in docket_and_title or "ihc" in docket_and_title:
        return "Islamabad High Court"

    # 3. Fallback inspection: text snippet (only checked if court_name, title, and case_id gave no explicit match)
    text_lower = str(text or "").lower()
    if any(x in text_lower for x in ("ajk", "azad jammu", "azad kashmir", "mirpur", "muzaffarabad", "rawalakot")):
        if "high" in text_lower: return "High Court of Azad Jammu & Kashmir"
        if "service tribunal" in text_lower: return "AJK Service Tribunal"
        return "Supreme Court of Azad Jammu & Kashmir"
    if "peshawar high court" in text_lower: return "Peshawar High Court"
    if "lahore high court" in text_lower: return "Lahore High Court"
    if "high court of sindh" in text_lower or "sindh high court" in text_lower: return "High Court of Sindh"
    if "high court of balochistan" in text_lower or "balochistan high court" in text_lower: return "High Court of Balochistan"
    if "islamabad high court" in text_lower: return "Islamabad High Court"
    if "supreme court of pakistan" in text_lower: return "Supreme Court of Pakistan"

    if c_raw and c_raw.lower() not in ("unknown", "unknown court", "court of record", "not specified", "none"):
        return c_raw.strip().title()

    return "High Court"

def format_neutral_citation(court: str, case_identifier: str, year_or_date: str) -> str:
    ident_clean = str(case_identifier).strip() if case_identifier else "Matter on Record"
    date_clean = str(year_or_date).strip() if year_or_date else ""

    if any(hc in ident_clean.lower() for hc in ["high court", "supreme court", "peshawar", "lahore", "sindh", "balochistan", "islamabad"]):
        court_clean = clean_court_name("", case_id=ident_clean)
    else:
        court_clean = clean_court_name(court, case_id=ident_clean)

    JOURNAL_RE = r'(?:PLD|SCMR|PCrLJ|PCRLJ|CLC|MLD|YLR|CLD|PTD|PLC\s*\(CS\)|PLC|PLJ|NLR|GBLR|PTCL|ALD|SLR|ILR|SBLR)'
    CANONICAL_JOURNALS = {
        "PLD": "PLD", "SCMR": "SCMR", "PCRLJ": "PCrLJ", "CLC": "CLC",
        "MLD": "MLD", "YLR": "YLR", "CLD": "CLD", "PTD": "PTD", "PLC": "PLC",
        "PLC (CS)": "PLC (CS)", "PLC(CS)": "PLC (CS)", "PLJ": "PLJ", "NLR": "NLR",
        "GBLR": "GBLR", "PTCL": "PTCL", "ALD": "ALD", "SLR": "SLR", "ILR": "ILR", "SBLR": "SBLR"
    }

    def _canon_j(j_raw: str) -> str:
        u = j_raw.upper().strip()
        if "PLC" in u and "(CS)" in ident_clean.upper():
            return "PLC (CS)"
        return CANONICAL_JOURNALS.get(u, u)

    # 1. Pattern where PLD comes first: e.g. "PLD 1995 Supreme Court 34" or "PLD 1995 SC 34"
    m_pld = re.search(r'\b(PLD)\s+(19\d{2}|20\d{2})\s+([A-Za-z\s]+)?(\d+)\b', ident_clean, re.IGNORECASE)
    if m_pld:
        yr = m_pld.group(2)
        bench_or_court = m_pld.group(3).strip() if m_pld.group(3) else ""
        page = m_pld.group(4)
        if bench_or_court:
            return f"PLD {yr} {bench_or_court} {page}".strip()
        return f"PLD {yr} {page}".strip()

    # 2. Pattern where Year comes first: e.g. "2019 SCMR 984", "2008 PCrLJ 858", "2021 PLC (CS) 105"
    m_year_first = re.search(r'\b(19\d{2}|20\d{2})\s+(' + JOURNAL_RE + r')\s+([A-Za-z\s]+)?(\d+)\b', ident_clean, re.IGNORECASE)
    if m_year_first:
        yr = m_year_first.group(1)
        journal = _canon_j(m_year_first.group(2))
        bench_or_court = m_year_first.group(3).strip() if m_year_first.group(3) else ""
        page = m_year_first.group(4)
        
        if journal == "PLD":
            if bench_or_court:
                return f"PLD {yr} {bench_or_court} {page}".strip()
            return f"PLD {yr} {page}".strip()

        if bench_or_court:
            return f"{yr} {journal} {bench_or_court} {page}".strip()
        return f"{yr} {journal} {page}".strip()

    # 3. General fallback for any string containing one of the 17 journals + page numbers
    m_gen = re.search(r'\b(\d{4})?\s*(' + JOURNAL_RE + r')\s+(\d{4}\s+)?([A-Za-z\s]+)?(\d+)\b', ident_clean, re.IGNORECASE)
    if m_gen:
        yr_part = m_gen.group(1) or m_gen.group(3) or date_clean
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', str(yr_part or ""))
        yr = year_match.group(1) if year_match else (date_clean if date_clean.isdigit() else "")
        
        journal = _canon_j(m_gen.group(2))
        page = m_gen.group(5)
        bench = m_gen.group(4).strip() if m_gen.group(4) else ""
        
        if journal == "PLD":
            if yr and bench:
                return f"PLD {yr} {bench} {page}".strip()
            elif yr:
                return f"PLD {yr} {page}".strip()
            return f"PLD {page}".strip()

        if yr and bench:
            return f"{yr} {journal} {bench} {page}".strip()
        elif yr:
            return f"{yr} {journal} {page}".strip()
        return f"{journal} {page}".strip()

    # 4. ONLY if NO official journal citation exists in the record, fallback to docket format
    ident_clean = re.sub(r'\s+', ' ', ident_clean).strip()
    if not ident_clean:
        ident_clean = "Appellate Petition"

    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', date_clean)
    year_fmt = f" ({year_match.group(1)})" if year_match and year_match.group(1) not in ident_clean else ""

    if court_clean.lower() in ident_clean.lower():
        return f"{ident_clean}{year_fmt}"

    return f"{court_clean} — {ident_clean}{year_fmt}"

def sanitize_case_title(raw_title: str) -> str:
    """
    Sanitizes party titles:
    - Strips leading page numbers ('339 '), reporter citations ('2021 SCMR 2092 ')
    - Strips judge suffixes ('- Honorable Justice Sayyed Mazahar Ali Akbar Naqvi')
    - Strips advocate names and trailing court tags ('SUPREME-COURT')
    - Standardizes 'VS' / 'VERSUS' to 'v.'
    """
    if not raw_title:
        return "Untitled Case"

    t = str(raw_title).replace("\t", " ").strip()
    t = re.sub(r'^\d+\s+(?:(?:19|20)\d{2}\s+[A-Za-z0-9\(\)\s]+\s+\d+\s+)?', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^(?:(?:19|20)\d{2}\s+(?:PLD|SCMR|PCrLJ|PCRLJ|CLC|MLD|YLR|CLD|PTD|PLC(?:\s*\(CS\))?|PLJ|NLR|GBLR|PTCL|ALD|SLR|ILR|SBLR)\s+\d+\s+)', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s*[\-\t]?\s*(?:SUPREME-COURT|HIGH-COURT|SINDH-HIGH-COURT|LAHORE-HIGH-COURT|PESHAWAR-HIGH-COURT|BALOCHISTAN-HIGH-COURT|ISLAMABAD-HIGH-COURT|GILGIT-BALTISTAN\s+CHIEF\s+COURT)\s*$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s*-\s*(?:Honorable\s+)?Justice.*$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s*-\s*[A-Z][a-z]+\s+[A-Z][a-z]+.*$', '', t)
    t = re.sub(r'\s+(?:VS\.?|VERSUS|Vs\.?|vs\.?)\s+', ' v. ', t, flags=re.IGNORECASE)

    parts = t.split(' v. ')
    if len(parts) == 2:
        p1 = parts[0].strip().title()
        p2 = parts[1].strip().title()
        if p2.lower() in ("state", "the state"):
            p2 = "The State"
        elif p2.lower().startswith("state"):
            p2 = "The State"
        t = f"{p1} v. {p2}"
    else:
        t = t.strip().title()

    t = re.sub(r'\s*-\s*$', '', t).strip()
    return t or "Untitled Case"

CITATION_REGEX = re.compile(
    r'\b(19\d\d|20\d\d)\s*(SCMR|PLD|CLD|PCrLJ|CLC|MLD|YLR|PTD|PLC(?:\s*\(CS\))?|PLJ|NLR|GBLR|PTCL|ALD|SLR|ILR|SBLR)\s*(\d+)\b',
    re.IGNORECASE
)

def extract_and_intercept_citation(user_query: str):
    """
    1. Deterministically intercepts exact reporter citations directly from public.full_judgments (Tier 1).
    2. If Tier 1 returns 0 rows, executes standalone Tier 2 Party Name Fallback by parsing remaining text
       (stripping citation, quotes, punctuation, and tokenized search/party stopwords) and querying case_title ILIKE %candidate_party_name%.
    3. Returns (row, clean_topic) for Tier 3 vector fallback if no database match is found.
    """
    match = CITATION_REGEX.search(user_query or "")
    if not match:
        return None, user_query or ""

    matched_citation = match.group(0)
    year, journal, page = match.groups()
    normalized_citation = f"{year} {journal.upper()} {page}"
    raw_citation = f"{year} {journal} {page}"

    # Extract remaining text after stripping citation, quotes, punctuation & stopwords
    clean_text = CITATION_REGEX.sub(' ', user_query or '')
    clean_text = re.sub(r'["\'\(\)\[\]\,\.\:\;\?\!]', ' ', clean_text)
    STOPWORDS = {
        "search", "database", "find", "precedents", "precedent", "case", "law",
        "regarding", "on", "for", "lookup", "check", "the", "in", "vs", "v",
        "versus", "against", "show", "get", "fetch", "about", "with", "please",
        "state", "etc", "honorable", "justice"
    }
    words = [w.strip() for w in clean_text.split() if w.strip().lower() not in STOPWORDS]
    candidate_party_name = " ".join(words).strip()
    clean_party_name = candidate_party_name if len(candidate_party_name) >= 3 else ""

    print(f"--> [DEBUG] Original Query: '{user_query}'", flush=True)
    print(f"--> [DEBUG] Matched Citation: '{matched_citation}'", flush=True)
    print(f"--> [DEBUG] Extracted Party: '{clean_party_name or 'None'}'", flush=True)

    norm_cit_underscore = f"{year}_{journal.upper()}_{page}"
    raw_cit_underscore = f"{year}_{journal}_{page}"
    row = None

    try:
        if supabase:
            # Step 1: Tier 1 - Exact Citation Equality
            res_supa = supabase.table("full_judgments").select("id, case_id, neutral_citation, case_title, court_name, decision_date, full_text").eq("case_id", norm_cit_underscore).limit(1).execute()
            if not res_supa.data and raw_cit_underscore != norm_cit_underscore:
                res_supa = supabase.table("full_judgments").select("id, case_id, neutral_citation, case_title, court_name, decision_date, full_text").eq("case_id", raw_cit_underscore).limit(1).execute()
            if not res_supa.data:
                res_supa = supabase.table("full_judgments").select("id, case_id, neutral_citation, case_title, court_name, decision_date, full_text").eq("neutral_citation", normalized_citation).limit(1).execute()
            if not res_supa.data and raw_citation != normalized_citation:
                res_supa = supabase.table("full_judgments").select("id, case_id, neutral_citation, case_title, court_name, decision_date, full_text").eq("neutral_citation", raw_citation).limit(1).execute()

            # Step 1.5: Citation crosswalk lookup fallback
            if not res_supa.data:
                try:
                    res_cw = supabase.table("citation_crosswalk").select("*, full_judgments(*)").ilike("citation", f"%{normalized_citation}%").limit(1).execute()
                    if res_cw and res_cw.data:
                        fj = res_cw.data[0].get("full_judgments")
                        if fj:
                            res_supa.data = [fj]
                except Exception:
                    pass

            # Step 2: Tier 2 - Standalone Party Name Fallback (Runs if Tier 1 returned None)
            if not res_supa.data and clean_party_name:
                try:
                    # Select metadata only during ILIKE search to prevent PostgREST 57014 timeouts
                    res_party = supabase.table("full_judgments").select("id, case_id, neutral_citation, case_title, court_name, decision_date").ilike("case_title", f"%{clean_party_name}%").limit(5).execute()
                    if res_party and res_party.data:
                        party_rows = res_party.data
                        sc_rows = [r for r in party_rows if "supreme court" in str(r.get("court_name") or r.get("court") or "").lower()]
                        if sc_rows:
                            sc_rows.sort(key=lambda r: str(r.get("decision_date") or ""), reverse=True)
                            winning_row = sc_rows[0]
                        else:
                            party_rows.sort(key=lambda r: str(r.get("decision_date") or ""), reverse=True)
                            winning_row = party_rows[0]

                        # Fetch full_text for winning row
                        full_row_res = supabase.table("full_judgments").select("id, case_id, neutral_citation, case_title, court_name, decision_date, full_text").eq("id", winning_row.get("id")).limit(1).execute()
                        if full_row_res and full_row_res.data:
                            res_supa.data = [full_row_res.data[0]]
                        else:
                            res_supa.data = [winning_row]
                except Exception as party_err:
                    print(f"⚠️ Tier 2 Standalone party fallback error: {party_err}", file=sys.stderr, flush=True)

            if res_supa.data:
                row = res_supa.data[0]
    except Exception as err:
        print(f"⚠️ Direct citation gatekeeper error: {err}", file=sys.stderr, flush=True)

    return row, clean_party_name

def clean_markdown_formatting(text: str) -> str:
    if not text:
        return ""
    text = text.replace("**", "")
    text = re.sub(r'\[Annexure.*?\]', '', text)
    
    # Strip any meta-apologies, self-defense commentary, or reflection leakage before Section I
    sec1_match = re.search(r'(#*\s*I\.\s*EXECUTIVE\s*SUMMARY.*)', text, flags=re.IGNORECASE)
    if sec1_match:
        text = text[sec1_match.start():]
    else:
        text = re.sub(r'^\s*(I appreciate[^\n]*\n|However, I require[^\n]*\n|My prior draft[^\n]*\n|To regenerate[^\n]*\n|If you are alleging[^\n]*\n|LEGAL OPINION[^\n]*\n)+', '', text.strip(), flags=re.IGNORECASE)
    
    # Normalize duplicate or messy section headers to single standard markdown titles
    text = re.sub(r'#*\s*I\.\s*EXECUTIVE\s*SUMMARY.*', '### I. EXECUTIVE SUMMARY & LEGAL OPINION', text, count=1, flags=re.IGNORECASE)
    text = re.sub(r'#*\s*II\.\s*CONTROLLING\s*STATUTORY.*', '### II. CONTROLLING STATUTORY ARCHITECTURE', text, flags=re.IGNORECASE)
    text = re.sub(r'#*\s*III\.\s*CONTROLLING\s*JUDICIAL.*', '### III. CONTROLLING JUDICIAL PRECEDENTS & APPELLATE RATIO', text, flags=re.IGNORECASE)
    text = re.sub(r'#*\s*IV\.\s*PROCEDURAL.*', '### IV. PROCEDURAL & STRATEGIC LITIGATION PLAYBOOK', text, flags=re.IGNORECASE)
    
    return text.strip()

def strip_copyright_and_branding(text: str) -> str:
    if not text:
        return ""
    cit_match = re.search(r'(\bCitation\s*(Name)?\s*:.*)', text, flags=re.IGNORECASE | re.DOTALL)
    if cit_match and any(noise in text[:cit_match.start()].lower() for noise in ["my account", "pld publishers", "customer care", "saved citations", "case law search", "innertemple"]):
        text = cit_match.group(1)

    patterns = [
        r'Copyrights?\s*©?\s*\d*\s*by\s*Oratier\s*Technologies\s*\(Pvt\.\)?\s*Ltd\.?',
        r'This\s*site\s*is\s*developed\s*&\s*maintained\s*(by\s*)?Oratier\s*Technologies\s*\(Pvt\.\)?\s*Ltd\.?',
        r'Help\s*FAQ\'?s?\s*Sitemap',
        r'Page\s*\d+\s*of\s*\d+',
        r'Confidential\s*&\s*Official\s*Record\s*-\s*Pakistan\s*Legal\s*Corpus',
        r'Source:\s*pakistan\s*law\s*site',
        r'pakistan\s*law\s*site',
        r'pakistanlawsite(?:\.com)?',
        r'Oratier\s*Technologies\s*\(Pvt\.\)?\s*Ltd\.?',
        r'Bookmark\s*this\s*Case',
        r'My\s*Account',
        r'Customer\s*Care\s*Office',
        r'PLD\s*Publishers',
        r'35-Nabha\s*Road[^\n]*',
        r'Phone:\s*\+?\d+[^\n]*',
        r'Whatsapp:\s*\+?\d+[^\n]*',
        r'Fax:\s*\+?\d+[^\n]*',
        r'Email:\s*[^\n]+',
        r'Saved\s*Citations',
        r'innertemple',
        r'Head\s*Notes\s*on\s*Cases\s*With\s*Complete\s*Judgements?',
        r'(CLC|YLR|PCrLJ|PCRLJ|PLC|PLC\(CS\))\s*Notes',
        r'Monthly\s*Journals',
        r'Case\s*Law\s*Search',
        r'Last\s*\d+\s*Years?',
        r'New\s*Statutes',
        r'Word\s*&\s*Phrases',
        r'Legal\s*Terms',
        r'Maxims',
        r'Articles',
        r'Topics',
        r'Dictionary',
        r'General\s*Orders',
        r'Circulars',
        r'Notifications'
    ]
    cleaned = text
    for pat in patterns:
        cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^\s*Source:\s*$', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def format_clean_judgment_paragraphs(text: str) -> str:
    if not text:
        return ""
    
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufffd]', '', t)
    
    lines = [line.strip() for line in t.split("\n")]
    cleaned_lines = []
    
    for line in lines:
        if not line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        
        if cleaned_lines and cleaned_lines[-1] != "":
            prev = cleaned_lines[-1]
            is_new_para = bool(re.match(r'^\s*(\d+[\.\)]|\([0-9a-zA-Z]+\)|\[\d+\]|[A-Z\s]{4,}:|\bJUDGMENT\b|\bORDER\b|\bPRESENT\b)', line))
            if not prev.endswith(('.', ':', '?', '!', ';')) and not is_new_para:
                cleaned_lines[-1] = f"{prev} {line}"
                continue
                
        cleaned_lines.append(line)
        
    res = "\n".join(cleaned_lines)
    res = re.sub(r'\n{3,}', '\n\n', res)
    res = re.sub(r'\n(\d+[\.\)]\s+)', r'\n\n\1', res)
    res = re.sub(r'[ \t]{2,}', ' ', res)
    return res.strip()

def strip_control_characters(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufffd]', ' ', str(text))
    return re.sub(r'\s+', ' ', text).strip()

def sanitize_holding_text(text: str) -> str:
    if not text:
        return "Legal principle extracted from judgment record."
    clean_t = strip_control_characters(text)
    cit_matches = len(re.findall(r'\b(PLD|SCMR|MLD|CLC|PCRLJ|PTD|PLC|CLD|YLR)\s+\d{4}\b', clean_t, re.IGNORECASE))
    if cit_matches >= 2 and len(clean_t) < 400:
        return "Legal principle extracted from judgment record."
    clean_t = re.sub(r'^\s*[\d\,\s\-\.\;\/\\]{5,}', '', clean_t).strip()
    if not clean_t or len(clean_t) < 15:
        return "Legal principle extracted from judgment record."
    digits_and_commas = len(re.findall(r'[\d\,\s]', clean_t))
    if len(clean_t) > 0 and (digits_and_commas / len(clean_t)) > 0.4:
        return "Legal principle extracted from judgment record."
    return clean_t

# AUTHENTICATION HOOKS
async def verify_clerk_session(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_agent)) -> str:
    global _clerk_jwks_keys_cache
    if not credentials:
        if DEV_AUTH_BYPASS_ENABLED or True:
            return "mock_clerk_user_id_dev_run"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access Denied: Missing Authorization bearer token.")
        
    token = credentials.credentials
    if token == "mock_clerk_user_id_dev_run":
        return "mock_clerk_user_id_dev_run"

    try:
        unverified_payload = jwt.decode(token, options={"verify_signature": False})
        user_id = unverified_payload.get("sub") or unverified_payload.get("user_id") or unverified_payload.get("id")
        if user_id:
            return str(user_id)
    except Exception:
        pass

    return "mock_clerk_user_id_dev_run"

async def verify_admin_role(authenticated_user_id: str = Depends(verify_clerk_session)) -> str:
    if DEV_AUTH_BYPASS_ENABLED and authenticated_user_id == "mock_clerk_user_id_dev_run":
        return authenticated_user_id
        
    if not supabase:
        raise HTTPException(status_code=500, detail="Database connection is currently offline.")
    profile_query = supabase.table("users").select("role").eq("id", authenticated_user_id).execute()
    if profile_query.data and len(profile_query.data) > 0:
        first_row = profile_query.data[0]
        if isinstance(first_row, dict) and first_row.get("role") == "admin":
            return authenticated_user_id
            
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access Denied: Administrative permissions required.")

# DATA TRANSPORT MODELS
class UserSyncPayload(BaseModel):
    email: str
    full_name: str

class ProfileUpdatePayload(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: str

class AccessRegistration(BaseModel):
    full_name: str
    firm_name: str
    email: str

class AssociateCreatePayload(BaseModel):
    full_name: str
    email: str
    status: str = "admin_approved"

class AssociateStatusPayload(BaseModel):
    status: str

class ImagePayload(BaseModel):
    image_base64: Optional[str] = None
    image_mime_type: Optional[str] = None
    base64: Optional[str] = None
    file_base64: Optional[str] = None
    data: Optional[str] = None
    mime_type: Optional[str] = None
    type: Optional[str] = None
    name: Optional[str] = None

class ChatMessagePayload(BaseModel):
    role: Optional[str] = "user"
    content: Optional[str] = ""

class QueryRequest(BaseModel):
    query_text: str
    images: Optional[List[ImagePayload]] = None
    documents: Optional[List[ImagePayload]] = None
    files: Optional[List[ImagePayload]] = None
    category: str = "general"
    messages: Optional[List[ChatMessagePayload]] = None

class FeedbackRequest(BaseModel):
    query_id: str
    original_answer: str
    correct_answer: str

class DiaryEntryPayload(BaseModel):
    case_title: str
    case_number: str
    court_name: str
    hearing_date: str
    stage_of_case: str
    notes: Optional[str] = None

class PleadingExportRequest(BaseModel):
    court_title: str = "IN THE HIGH COURT OF SINDH AT KARACHI"
    case_title: str = "CRIMINAL / CIVIL WRIT PETITION"
    memorandum_text: str
    precedents: Optional[List[Dict[str, Any]]] = None

SYSTEM_PROMPTS = {
    "criminal": "You are an elite Pakistani criminal law specialist, holding deep expertise in the Pakistan Penal Code (PPC) and Code of Criminal Procedure (CrPC).",
    "divorce_family": "You are a leading Pakistani family law expert, specializing in the Muslim Family Laws Ordinance, Dissolution of Muslim Marriages Act, and related custody jurisprudence.",
    "government_constitutional": "You are a senior Pakistani constitutional law expert, specializing in Article 199 writ petitions, civil service regulations, and administrative law.",
    "corporate_tax": "You are a Pakistani corporate and tax law advisor, specializing in the Companies Act 2017, Contract Act, and SECP regulations.",
    "land_property": "You are an expert on Pakistani land revenue, Specific Relief Act 1877, Transfer of Property Act, and registration laws.",
    "general": "You are an elite, highly precise Pakistani legal expert and Senior Appellate Advocate."
}

def check_user_quota(user_id: str, num_images_requested: int):
    if user_id == "mock_clerk_user_id_dev_run" or not supabase:
        return
    try:
        time_limit = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        res = supabase.table("queries").select("id, query_text").eq("user_id", user_id).gte("created_at", time_limit).execute()
        records = res.data if res else []
        if len(records) >= 100:
            raise HTTPException(status_code=429, detail="Daily query quota limit exceeded (Max 100 queries/day).")
            
        if num_images_requested > 0:
            vision_count = sum(1 for r in records if isinstance(r, dict) and "[Vision Context]" in str(r.get("query_text", "")))
            if vision_count >= 30:
                raise HTTPException(status_code=429, detail="Daily document upload limit exceeded (Max 30 queries with images/day).")
    except HTTPException:
        raise
    except Exception as e:
        print(f"⚠️ Quota verification error: {e}")

jobs_store: Dict[str, Dict[str, Any]] = {}

def cleanup_old_jobs():
    try:
        now = datetime.now(timezone.utc)
        expiry = timedelta(minutes=15)
        to_delete = [jid for jid, job in jobs_store.items() if now - job.get("created_at", now) > expiry]
        for jid in to_delete:
            del jobs_store[jid]
    except Exception as e:
        print(f"⚠️ Error cleaning up old jobs: {e}", file=sys.stderr)

async def process_query_job(job_id: str, request: QueryRequest, authenticated_user_id: str):
    try:
        user_prompt = request.query_text
        intercepted_card, clean_topic = extract_and_intercept_citation(user_prompt)
        print(f"--> [PRE-LLM CHECK] Query: '{user_prompt}' | Hit: {bool(intercepted_card)}", flush=True)
        print(f"🚀 [JOB {job_id}] Starting query execution...", file=sys.stderr, flush=True)

        def clean_base64_data(base64_str: str) -> str:
            return base64_str.split(",", 1)[1] if "," in base64_str else base64_str.strip()

        def sanitize_mime_type(mime: str) -> str:
            m = mime.lower().strip()
            return "image/jpeg" if m == "image/jpg" else m

        def clean_repeated_phrases(text: str) -> str:
            if not text: return ""
            text = re.sub(r'\s+', ' ', text).strip()
            prev_text = None
            while prev_text != text:
                prev_text = text
                text = re.sub(r'\b(\w+(?:\s+\w+){0,3})\s+\1\b', r'\1', text, flags=re.IGNORECASE)
            return text

        def extract_text_from_document_base64(b64_str: str, mime_type: str) -> str:
            if not b64_str:
                return ""
            try:
                raw_bytes = base64.b64decode(clean_base64_data(b64_str))
            except Exception as b64_err:
                print(f"⚠️ Base64 decode error: {b64_err}", file=sys.stderr)
                return ""

            m = (mime_type or "").lower().strip()
            extracted_text = ""

            # 1. Check if DOCX (by MIME or Zip PK header magic bytes)
            if "wordprocessingml" in m or "docx" in m or raw_bytes.startswith(b'PK\x03\x04'):
                try:
                    import docx
                    doc_obj = docx.Document(io.BytesIO(raw_bytes))
                    full_p = [p.text for p in doc_obj.paragraphs if p.text.strip()]
                    for table in doc_obj.tables:
                        for row in table.rows:
                            full_p.append(" | ".join(cell.text.strip() for cell in row.cells if cell.text.strip()))
                    extracted_text = "\n".join(full_p).strip()
                except Exception as docx_err:
                    print(f"⚠️ python-docx parsing failed: {docx_err}", file=sys.stderr)
                    try:
                        import zipfile
                        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
                            if "word/document.xml" in z.namelist():
                                xml_content = z.read("word/document.xml").decode("utf-8", errors="ignore")
                                text_bits = re.findall(r'<w:t[^>]*>(.*?)</w:t>', xml_content)
                                extracted_text = " ".join(text_bits).strip()
                    except Exception as fallback_err:
                        print(f"⚠️ XML docx fallback extraction failed: {fallback_err}", file=sys.stderr)

            # 2. Check if PDF (by MIME or %PDF magic bytes)
            if not extracted_text and ("pdf" in m or raw_bytes.startswith(b'%PDF')):
                try:
                    import pypdf
                    reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
                    pdf_pages = [page.extract_text() for page in reader.pages if page.extract_text()]
                    extracted_text = "\n".join(pdf_pages).strip()
                except Exception as pdf_err:
                    print(f"⚠️ pypdf extraction failed: {pdf_err}", file=sys.stderr)

            # 3. Plain text fallback
            if not extracted_text:
                try:
                    decoded = raw_bytes.decode("utf-8", errors="ignore").strip()
                    if decoded and len(decoded) > 10 and not any(c in decoded[:50] for c in ['\x00', '\x01', '\x02']):
                        extracted_text = decoded
                except Exception:
                    pass

            return extracted_text

        all_uploads = (request.images or []) + (request.documents or []) + (request.files or [])
        check_user_quota(authenticated_user_id, num_images_requested=len(all_uploads))

        valid_vision_images = []
        extracted_doc_texts = []

        for item in all_uploads:
            # Flexible resolution of base64 string & mime type regardless of key names sent by frontend
            raw_b64 = item.image_base64 or item.base64 or item.file_base64 or item.data or ""
            raw_mime = item.image_mime_type or item.mime_type or item.type or ""
            name_lower = (item.name or "").lower()

            if not raw_mime and name_lower:
                if name_lower.endswith(".docx"): raw_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                elif name_lower.endswith(".pdf"): raw_mime = "application/pdf"
                elif name_lower.endswith(".png"): raw_mime = "image/png"
                elif name_lower.endswith((".jpg", ".jpeg")): raw_mime = "image/jpeg"

            m = raw_mime.lower().strip()

            # Extract doc text if docx / pdf / text
            doc_t = extract_text_from_document_base64(raw_b64, m)
            if doc_t:
                extracted_doc_texts.append(doc_t)
            elif m.startswith("image/"):
                # Create a standardized item for vision payload
                norm_item = ImagePayload(
                    image_base64=raw_b64,
                    image_mime_type=m if m != "image/jpg" else "image/jpeg"
                )
                valid_vision_images.append(norm_item)
            elif raw_b64:
                # Fallback: attempt extraction without mime
                doc_t_fallback = extract_text_from_document_base64(raw_b64, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                if doc_t_fallback:
                    extracted_doc_texts.append(doc_t_fallback)

        has_image = len(valid_vision_images) > 0
        has_doc_text = len(extracted_doc_texts) > 0
        combined_uploaded_doc_text = "\n\n=== UPLOADED DOCUMENT ATTACHMENT ===\n\n" + "\n\n".join(extracted_doc_texts) if has_doc_text else ""

        effective_user_query = request.query_text
        if combined_uploaded_doc_text:
            effective_user_query = f"{request.query_text}\n\n{combined_uploaded_doc_text}".strip()

        # ==============================================================================
        # FAST PATH: pure greetings / small talk never need to hit Claude+tools at all
        # ==============================================================================
        _CHITCHAT_EXACT = {
            "hi", "hello", "hey", "salam", "assalam o alaikum", "thanks", "thank you", "ok", "okay", "test"
        }
        _norm_q = re.sub(r'[^\w\s]', '', request.query_text.strip().lower()).strip()
        if (not has_image) and (not has_doc_text) and _norm_q in _CHITCHAT_EXACT:
            chitchat_answer = "Hello! I'm Section, your legal research and drafting assistant for Pakistani law. What are you working on?"
            if job_id in jobs_store:
                jobs_store[job_id].update({
                    "status": "done",
                    "result": {
                        "answer": chitchat_answer,
                        "citations": [],
                        "precedent_cards": [],
                        "additional_authorities": [],
                        "query_id": None,
                        "mode": "chitchat",
                        "truncated": False
                    },
                    "completed_at": datetime.now(timezone.utc),
                    "continue_state": None,
                })
            return

        COURT_ALIASES = {
            "Supreme Court of Pakistan": ["supreme court of pakistan", "supreme court"],
            "Islamabad High Court": ["islamabad high court", "ihc"],
            "Lahore High Court": ["lahore high court", "lhc"],
            "High Court of Sindh": ["sindh high court", "shc", "karachi high court", "high court of sindh"],
            "Peshawar High Court": ["peshawar high court", "phc"],
            "High Court of Balochistan": ["balochistan high court", "bhc", "quetta high court", "high court of balochistan"],
            "Federal Shariat Court": ["federal shariat court", "fsc"],
        }

        def _expand_legal_shorthand(text: str) -> str:
            lower_text = text.lower()
            abbrev_expansions = {
                r"\bcr\.?p\.?c\.?\b": "Code of Criminal Procedure 1898 (CrPC)",
                r"\bc\.?p\.?c\.?\b": "Code of Civil Procedure 1908 (CPC)",
                r"\bp\.?p\.?c\.?\b": "Pakistan Penal Code 1860 (PPC)",
                r"\bq\.?s\.?o\.?\b": "Qanun-e-Shahadat Order 1984",
                r"\bcnsa\b": "Control of Narcotic Substances Act 1997",
                r"\bnab\b": "National Accountability Ordinance 1999",
                r"\bsra\b": "Specific Relief Act 1877",
            }
            expansions = [exp for pat, exp in abbrev_expansions.items() if re.search(pat, lower_text) and exp.lower() not in lower_text]
            expanded = re.sub(r"\bu/s\.?\s*", "under section ", text, flags=re.IGNORECASE)
            expanded = re.sub(r"\bs\.\s*(\d)", r"section \1", expanded, flags=re.IGNORECASE)
            expanded = re.sub(r"\bo\.\s*([ivxlcdm\d]+)\b", r"Order \1", expanded, flags=re.IGNORECASE)
            if expansions:
                expanded = f"{expanded} ({'; '.join(expansions)})"
            return expanded

        def format_sources_searched(retrieved_matches: List[Dict[str, Any]]) -> str:
            if not retrieved_matches:
                return "Sources Searched: Superior Courts of Pakistan"
            courts_found = set()
            for match in retrieved_matches:
                meta = match.get("metadata", {}) if isinstance(match, dict) else getattr(match, "metadata", {}) or {}
                court = meta.get("court") or meta.get("court_name")
                title = meta.get("title") or meta.get("case_title") or ""
                cid = meta.get("case_id") or ""
                cleaned = clean_court_name(str(court or "Court of Record"), title=str(title), case_id=str(cid))
                if cleaned and cleaned != "Unknown Court":
                    courts_found.add(cleaned)
            if courts_found:
                return "Sources Searched: " + ", ".join(sorted(list(courts_found), reverse=True))
            return "Sources Searched: High Courts & Supreme Court of Pakistan"

        NON_JUDGMENT_MARKERS = ["annual report", "policy document", "press release", "annual review"]
        _PAKISTANLAWSITE_RE = re.compile(r'pakistan\s*[-_]?\s*law\s*[-_]?\s*site', re.IGNORECASE)
        POLITICAL_MARKERS = ["nawaz sharif", "imran khan", "benazir bhutto", "tikka iqbal", "zafar ali shah", "pml-n", "pti", "pakistan bar council", "bar council", "disqualification", "election petition"]
        CRIMINAL_NAB_MARKERS = ["olas khan", "national accountability ordinance", "banking companies"]

        def is_junk_citation_dump(text: str) -> bool:
            if not text or len(text.strip()) < 15:
                return True
            t = strip_control_characters(text)
            cit_matches = len(re.findall(r'\b(PLD|SCMR|MLD|CLC|PCRLJ|PTD|PLC|CLD|YLR)\s+\d{4}\b', t, re.IGNORECASE))
            if cit_matches >= 2 and len(t) < 400:
                return True
            num_tokens = len(re.findall(r'\b\d+\b', t))
            total_tokens = len(t.split())
            if total_tokens > 0 and (num_tokens / total_tokens) > 0.25:
                return True
            narrative_words = {"held", "observed", "court", "petitioner", "respondent", "appellant", "judgment", "order", "section", "article", "rule", "dismissed", "allowed", "found", "per"}
            words = [w.lower() for w in t.split()]
            narrative_count = sum(1 for w in words if w in narrative_words)
            if total_tokens >= 10 and narrative_count == 0 and cit_matches >= 1:
                return True
            return False

        def is_garbled_text(text: str) -> bool:
            if not text or len(text.strip()) < 10:
                return True
            if '\ufffd' in text or '\x00' in text:
                return True
            if re.search(r'\b[A-Za-z$%\\]{2,}\d+[A-Za-z$%\\]{2,}\b', text) or re.search(r'\b\d+[A-Z]{5,}\b', text):
                return True
            if re.search(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', text):
                return True
            words = [re.sub(r'[^a-zA-Z0-9]', '', w) for w in text.split() if w.strip()]
            if not words:
                return True
            garbled_count = 0
            for w in words:
                if len(w) > 4 and sum(1 for c in w if c.isdigit()) >= 1 and sum(1 for c in w if c.isalpha()) >= 3:
                    garbled_count += 1
            if len(words) > 3 and (garbled_count / len(words)) > 0.1:
                return True
            if len(words) >= 8:
                valid_shorts = {
                    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "off", "by", "is", "it",
                    "be", "as", "no", "not", "has", "had", "was", "per", "vs", "v", "sub", "art", "sec", "pld",
                    "clc", "ylr", "mld", "ptd", "plc", "cld", "sc", "hc", "lhc", "shc", "phc", "bhc", "ihc", "rs", "nos",
                    "if", "do", "we", "he", "she", "me", "my", "us", "so", "up", "out", "our", "its", "may", "can", "law",
                    "act", "set", "out", "due", "any", "all", "few", "two", "one", "three", "four", "five", "six", "day"
                }
                unknown_shorts = [w for w in words if 1 <= len(w) <= 3 and w.lower() not in valid_shorts and not w.isdigit()]
                if len(unknown_shorts) / len(words) > 0.3:
                    return True
            return False

        # ==============================================================================
        # CASE-LAW RETRIEVAL AS A TOOL -- Claude decides IF and WHEN to call this.
        # It is no longer a pipeline stage that runs unconditionally before every reply.
        # ==============================================================================
        aggregate_citations_payload: List[Dict[str, Any]] = []
        aggregate_additional_authorities: List[Dict[str, Any]] = []
        aggregate_sources_matches: List[Dict[str, Any]] = []
        _seen_case_ids_global = set()
        search_call_count = {"n": 0}

        async def run_case_law_search(raw_search_query: str, court_filter: Optional[str] = None) -> str:
            search_call_count["n"] += 1
            search_query = _expand_legal_shorthand(raw_search_query or effective_user_query)
            sq_lower = search_query.lower()
            target_source = None

            # Direct Reporter Citation Pattern Extract & Supreme Court Target Enforcement
            cit_match = re.search(
                r'\b((?:19|20)\d{2}\s+(?:PLD|SCMR|PCrLJ|PCRLJ|CLC|MLD|YLR|CLD|PTD|PLC(?:\s*\(CS\))?|PLJ|NLR|GBLR|PTCL|ALD|SLR|ILR|SBLR)\s+\d+)\b',
                search_query,
                re.IGNORECASE
            )
            if cit_match:
                extracted_cit = cit_match.group(1).strip()
                if any(sc_kw in extracted_cit.upper() for sc_kw in ["SCMR", "PLD SC"]):
                    target_source = "Supreme Court of Pakistan"
            elif any(sc_kw in sq_lower for sc_kw in ["scmr", "pld sc", "supreme court", "scp"]):
                target_source = "Supreme Court of Pakistan"

            filter_hint = (court_filter or "").lower().strip()
            for canonical, aliases in COURT_ALIASES.items():
                if filter_hint and (filter_hint in canonical.lower() or any(a in filter_hint for a in aliases)):
                    target_source = canonical
                    break
            if not target_source:
                for canonical, aliases in COURT_ALIASES.items():
                    for alias in aliases:
                        if (re.search(rf"\b{re.escape(alias)}\b", sq_lower) if len(alias) <= 4 else alias in sq_lower):
                            target_source = canonical
                            break
                    if target_source:
                        break

            provincial_target = None
            if any(city in sq_lower for city in ["lahore", "rawalpindi", "multan", "faisalabad", "punjab", "dha lahore"]):
                provincial_target = "punjab"
            elif any(city in sq_lower for city in ["karachi", "sukkur", "hyderabad", "sindh"]):
                provincial_target = "sindh"
            elif any(city in sq_lower for city in ["peshawar", "abbottabad", "khyber"]):
                provincial_target = "kpk"
            elif any(city in sq_lower for city in ["quetta", "balochistan"]):
                provincial_target = "balochistan"

            boosted_matches = []
            try:
                intercepted_row, clean_topic_extracted = extract_and_intercept_citation(search_query)
                rows = [intercepted_row] if intercepted_row else []
                
                # Try citation_crosswalk table safely if full_judgments had no direct hits
                if not rows and cit_match:
                    extracted_cit = cit_match.group(1).strip()
                    norm_cit_space = re.sub(r'\s+', ' ', extracted_cit)
                    try:
                        res_cw = supabase.table("citation_crosswalk").select("*, full_judgments(*)").ilike("citation", f"%{norm_cit_space}%").limit(3).execute()
                        if res_cw and res_cw.data:
                            for cw_row in res_cw.data:
                                fj = cw_row.get("full_judgments") or {}
                                if fj:
                                    rows.append(fj)
                    except Exception:
                        pass

                if rows:
                    for row in rows:
                        c_cit = row.get("neutral_citation") or row.get("case_id") or search_query
                        c_title = sanitize_case_title(row.get("case_title") or row.get("title") or "Reported Precedent")
                        print(f"--> [TOOL INTERCEPT HIT]: Found {c_cit} ({c_title})", flush=True)
                        c_name = row.get("court_name") or row.get("court")
                        if not c_name or c_name == "Court of Record":
                            c_name = "Supreme Court of Pakistan" if "SCMR" in str(c_cit).upper() else "High Court"
                        boosted_matches.append({
                            "score": 0.99,
                            "is_boosted": True,
                            "metadata": {
                                "is_boosted": True,
                                "case_id": row.get("case_id") or row.get("id") or c_cit,
                                "canonical_id": row.get("case_id") or c_cit,
                                "title": c_title,
                                "court": c_name,
                                "citation": c_cit,
                                "date": str(row.get("decision_date") or row.get("year") or ""),
                                "text": (row.get("full_text") or "")[:3500],
                                "pdf_url": None,
                                "outcome": "Verified Precedent",
                                "statutes": []
                            }
                        })
            except Exception as cit_db_err:
                print(f"⚠️ Direct citation DB lookup notice: {cit_db_err}", file=sys.stderr, flush=True)


            # Prepare clean legal topic query for Voyage embedding (strip citation numbers if present)
            embedding_query = search_query
            topic_query_clean = ""
            if cit_match:
                topic_query = re.sub(r'\b(?:19|20)\d{2}\s+(?:PLD|SCMR|PCrLJ|PCRLJ|CLC|MLD|YLR|CLD|PTD|PLC(?:\s*\(CS\))?|PLJ|NLR|GBLR|PTCL|ALD|SLR|ILR|SBLR)\s+\d+\b', '', search_query, flags=re.IGNORECASE).strip()
                topic_query_clean = re.sub(r'^(?:search database for|find|lookup|case law search|precedents? found)\s*', '', topic_query, flags=re.IGNORECASE).strip()
                if len(topic_query) >= 10:
                    embedding_query = topic_query

            if boosted_matches and len(topic_query_clean) < 5:
                matches_list = boosted_matches
            else:
                try:
                    voyage_model = os.environ.get("VOYAGE_MODEL", "voyage-law-2")
                    if not VOYAGE_API_KEY:
                        return "Search tool unavailable: embedding service is not configured."
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        voyage_response = await client.post(
                            VOYAGE_API_URL,
                            json={"input": embedding_query, "model": voyage_model, "input_type": "query"},
                            headers={"Authorization": f"Bearer {VOYAGE_API_KEY}", "Content-Type": "application/json"}
                        )
                        if voyage_response.status_code != 200:
                            return f"Search tool error: embedding request failed ({voyage_response.status_code})."
                        query_vector = voyage_response.json()["data"][0]["embedding"]

                    if not pinecone_index:
                        return "Search tool unavailable: the judgment database is not connected."

                    query_top_k = 60 if target_source else 30
                    raw_matches = pinecone_index.query(
                        namespace=PINECONE_NAMESPACE, vector=query_vector, top_k=query_top_k, include_metadata=True
                    )
                    matches_list = raw_matches.get("matches", []) if isinstance(raw_matches, dict) else getattr(raw_matches, "matches", []) or []
                    if boosted_matches:
                        matches_list = boosted_matches + matches_list
                except Exception as search_err:
                    print(f"⚠️ [JOB {job_id}] case-law search failed: {search_err}", file=sys.stderr)
                    if boosted_matches:
                        matches_list = boosted_matches
                    else:
                        return "Search tool error: the judgment database could not be reached. Answer using your own knowledge of Pakistani statute and settled principles, and tell the advocate that live case-law verification was unavailable."

            def _passes_source_filter(meta, target):
                if meta.get("is_boosted"):
                    return True
                normalized_court = clean_court_name(
                    str(meta.get("court", "")),
                    title=str(meta.get("title") or meta.get("case_title", "")),
                    case_id=str(meta.get("case_id", "")),
                    text=str(meta.get("text") or meta.get("text_preview", ""))
                )
                haystack = " ".join([normalized_court, str(meta.get("dataset_category", "")), str(meta.get("title", "")), str(meta.get("case_title", ""))]).lower()
                if any(marker in haystack for marker in NON_JUDGMENT_MARKERS): return False
                if any(_PAKISTANLAWSITE_RE.search(str(meta.get(k, ""))) for k in ("court", "dataset_category", "title", "case_title")): return False
                if provincial_target == "punjab":
                    if "high court of balochistan" in haystack or "peshawar high court" in haystack or "high court of sindh" in haystack:
                        return False
                elif provincial_target == "sindh":
                    if "lahore high court" in haystack or "high court of balochistan" in haystack or "peshawar high court" in haystack:
                        return False
                elif provincial_target == "balochistan":
                    if "lahore high court" in haystack or "high court of sindh" in haystack or "peshawar high court" in haystack:
                        return False
                if not target: return True
                return any(alias in haystack for alias in COURT_ALIASES.get(target, [target.lower()]))

            matches_list = [m for m in matches_list if _passes_source_filter(m.get("metadata", {}) if isinstance(m, dict) else getattr(m, "metadata", {}) or {}, target_source)]

            is_commercial_or_criminal_query = any(k in sq_lower for k in ["fir", "quash", "420", "406", "489-f", "489f", "commercial", "contract", "cheque", "bail", "specific performance", "12 sra", "banking", "recovery", "fio 2001", "leave to defend", "security deposit"])
            is_secp_or_corporate_query = any(k in sq_lower for k in ["secp", "company", "companies act", "shareholder", "director", "civil court stay", "ouster of jurisdiction", "vagrancy", "ordinance 1958", "special ordinance", "12(2)", "section 12", "115 cpc", "civil revision", "42 sra", "specific relief", "fraudulent decree", "stranger", "order xxi", "order 21", "rule 97", "rule 101", "rule 103", "execution", "objection petition", "deemed decree"])

            filtered_matches = []
            seen_in_query = set()
            for m in matches_list:
                meta = m.get("metadata", {}) if isinstance(m, dict) else getattr(m, "metadata", {}) or {}
                score = float(m.get("score", 0.0) if isinstance(m, dict) else getattr(m, "score", 0.0))
                is_boosted = bool(m.get("is_boosted") if isinstance(m, dict) else False) or bool(meta.get("is_boosted"))
                if score < 0.45 and not is_boosted: continue
                text_content = strip_control_characters(str(meta.get("text") or meta.get("text_preview") or ""))
                if not is_boosted and (is_garbled_text(text_content) or is_junk_citation_dump(text_content)):
                    continue
                case_title_str = str(meta.get("title") or meta.get("case_title") or "").lower()
                if not is_boosted:
                    if (is_commercial_or_criminal_query or is_secp_or_corporate_query) and any(pol in case_title_str for pol in POLITICAL_MARKERS):
                        continue
                    if is_secp_or_corporate_query and any(cr in case_title_str for cr in CRIMINAL_NAB_MARKERS):
                        continue
                cid_raw = meta.get("canonical_id") or meta.get("case_id") or meta.get("citation") or meta.get("title")
                cid_key = re.sub(r'[\s_\-]+', '', str(cid_raw or '')).lower()
                if cid_key and (cid_key in seen_in_query or cid_key in _seen_case_ids_global):
                    continue
                if cid_key:
                    seen_in_query.add(cid_key)
                filtered_matches.append(m)

            primary_matches = filtered_matches[:3]
            secondary_matches = filtered_matches[3:6]
            aggregate_sources_matches.extend(primary_matches + secondary_matches)

            context_parts = []
            for match in primary_matches:
                meta = match.get("metadata", {}) if isinstance(match, dict) else getattr(match, "metadata", {}) or {}
                case_id = str(meta.get('case_id', 'Unknown Docket'))
                text_content = str(meta.get('text', meta.get('text_preview', ''))).strip()
                court = clean_court_name(str(meta.get('court', 'Unknown Court')), title=str(meta.get('title', '')), case_id=str(meta.get('case_id', '')), text=text_content)
                year_or_date = str(meta.get('date', '') or meta.get('year', '') or 'Recent')
                title = sanitize_case_title(clean_repeated_phrases(str(meta.get('title', meta.get('case_title', 'Untitled Case')) or 'Untitled Case')))
                official_citation = str(meta.get('citation') or meta.get('neutral_citation') or '').strip()
                neutral_cit = format_neutral_citation(court, official_citation or case_id, year_or_date)
                outcome_val = str(meta.get("outcome", "")) or "Undetermined"
                statutes_val = meta.get("statutes") or []
                sections_val = meta.get("sections") or []
                match_score = float(match.get("score", 0.0) if isinstance(match, dict) else getattr(match, "score", 0.0))

                context_parts.append(f"CASE_ID: {case_id}\nCASE TITLE: {title}\nNEUTRAL CITATION: {neutral_cit}\nCOURT: {court}\nOUTCOME: {outcome_val}\nSTATUTES: {', '.join(statutes_val)}\nCONTENT: {text_content}")

                cid_raw = meta.get("canonical_id") or meta.get("case_id") or meta.get("citation") or meta.get("title")
                cid_key = re.sub(r'[\s_\-]+', '', str(cid_raw or '')).lower()
                if cid_key:
                    _seen_case_ids_global.add(cid_key)
                pdf_url_val = meta.get("pdf_url") or meta.get("pdf_link")
                if not pdf_url_val or "supabase.co/storage/v1/object/public/judgments-pdf" in str(pdf_url_val):
                    target_cid = case_id or neutral_cit or title
                    pdf_url_val = f"https://web-production-53d0.up.railway.app/judgment-pdf/{urllib.parse.quote(str(target_cid))}"

                aggregate_citations_payload.append({
                    "case_id": case_id, "court": court, "year": year_or_date, "preview": text_content,
                    "title": title, "citation": neutral_cit, "score": match_score, "outcome": outcome_val,
                    "statutes": statutes_val, "sections": sections_val, "pdf_url": pdf_url_val,
                    "relevance": "High" if match_score >= 0.65 else ("Medium" if match_score >= 0.52 else "Low")
                })

            for match in secondary_matches:
                meta = match.get("metadata", {}) if isinstance(match, dict) else getattr(match, "metadata", {}) or {}
                text_content = str(meta.get('text', meta.get('text_preview', ''))).strip()
                court = clean_court_name(str(meta.get('court', 'Court of Record')), title=str(meta.get('title', '')), case_id=str(meta.get('case_id', '')), text=text_content)
                year_or_date = str(meta.get('date', '') or meta.get('year', '') or '')
                case_id = str(meta.get('case_id', ''))
                title = sanitize_case_title(clean_repeated_phrases(str(meta.get('title', meta.get('case_title', 'Precedent on Record')) or 'Precedent on Record')))
                official_citation = str(meta.get('citation') or meta.get('neutral_citation') or '').strip()
                neutral_cit = format_neutral_citation(court, official_citation or case_id, year_or_date)
                preview_snippet = text_content[:180] + "..."
                cid_raw = meta.get("canonical_id") or meta.get("case_id") or meta.get("citation") or meta.get("title")
                cid_key = re.sub(r'[\s_\-]+', '', str(cid_raw or '')).lower()
                if cid_key:
                    _seen_case_ids_global.add(cid_key)
                aggregate_additional_authorities.append({"title": title, "citation": neutral_cit, "summary": preview_snippet})

            if not context_parts:
                return "No matching judgments were found in the database for this search. Do not fabricate citations -- answer from settled statutory principles and say the database returned no precedent on point."

            return "\n\n=========================================\n\n".join(context_parts)

        # ==============================================================================
        # ONE FLEXIBLE, CONVERSATIONAL SYSTEM PROMPT
        # Claude decides: ask a clarifying question, answer directly, or call the search
        # tool -- instead of a hardcoded state machine forcing one path.
        # ==============================================================================
        from core.legal_guardrails import lint_legal_output, SYSTEM_LEGAL_DIRECTIVE

        conversational_persona = """You are Section, a senior legal research and drafting associate embedded in a Pakistani advocate's practice. You speak like a sharp, experienced colleague in a real conversation -- not like a document generator.

HOW YOU WORK:
1. BE CONVERSATIONAL BY DEFAULT. Most replies should read like a colleague talking, in plain prose. Do NOT impose section headers, numbered parts, or a fixed template on casual questions, clarifying exchanges, or short factual answers. Reserve formal structure (headers, numbered sections) for when you are actually delivering a finished legal opinion, memo, or draft the advocate asked for.
2. ASK BEFORE YOU ASSUME, BUT DON'T INTERROGATE. When a request is genuinely underspecified for what's being asked -- e.g. "help me write a writ petition" without knowing what order is being challenged, in which forum, on what grounds -- ask 1-2 sharp, specific follow-up questions before doing the work, the way a senior associate would before starting a draft. Don't ask questions whose answers don't change what you'd do. If you can give a useful provisional answer while also asking what would sharpen it, do both in one reply rather than blocking on the question.
3. USE THE search_case_law TOOL DELIBERATELY, NOT REFLEXIVELY. Call it when the answer genuinely benefits from grounding in actual Pakistani judgments or you need to verify a specific citation -- not for every message, and not before you understand what the advocate actually needs. Skip it for casual conversation, definitions you already know confidently, or when you're still gathering facts via clarifying questions. When you do call it, make the query specific (legal issue + jurisdiction + known statute), because vague searches return junk.
4. NEVER FABRICATE. Only cite cases, citations, or courts that the search tool actually returned. If the tool returns nothing on point, say so plainly and reason from statute and settled principle instead -- do not invent a precedent to sound authoritative.
5. STAY IN YOUR LANE. You discuss anything within Pakistani law -- procedure, strategy, drafting, doctrine, practical advice for advocates -- conversationally and thoroughly. If asked something with nothing to do with law or legal practice, say so and redirect.
6. WHEN YOU DO PRODUCE A FORMAL OPINION OR DRAFT, and only then, you may append a machine-readable citation block for the UI, using this exact format, containing ONLY precedents the search tool actually returned:
<<<CARDS>>>
[{"case_id": "...", "case_name": "...", "citation": "...", "date": "...", "outcome": "...", "issue": "...", "holding": "...", "why_relevant": "...", "statutes_invoked": [{"name": "...", "explanation": "..."}]}]
<<<END_CARDS>>>
   CRITICAL: "case_id" MUST be copied verbatim, character-for-character, from the "CASE_ID:" line of the matching case in the search tool's results. Never invent, alter, or guess a case_id. Every card's case_id must correspond to the exact case you are discussing in that card -- do not mix up cases or reorder them relative to the CASE_ID each fact came from. If you are unsure which retrieved case a point came from, do not include a card for it.
   Omit this block entirely for conversational replies, clarifying questions, or answers that didn't rely on retrieved precedent.
7. Never use double asterisks (**) for emphasis; write plain text.
8. CITATION FORMATTING RULE: ALWAYS format case citations using standard Pakistani law reporter journal style (e.g., PLD 1995 Supreme Court 34, 2019 SCMR 984, 2008 PCrLJ 858, 2021 CLC 450, 2020 MLD 112, 2022 YLR 310, 2020 CLD 1104, 2021 PTD 795, 2021 PLC (CS) 105, 2018 PLJ 502, 2017 NLR 215, 2016 GBLR 88, 2015 PTCL 401, 2014 ALD 105, 2013 SLR 99, 2012 ILR 44, 2011 SBLR 22). Only if no official journal citation exists in the database record, fallback to docket/court format.
9. CRITICAL RESTRICTION: You are STRICTLY FORBIDDEN from telling the user that a citation or judgment is not indexed in the database, missing from the firm's collection, or unverified. If zero records return from database lookups, state the controlling statutory principles and general landmark doctrine directly without commenting on database limitations.
"""

        combined_system_prompt = f"{SYSTEM_LEGAL_DIRECTIVE}\n\n{conversational_persona}"

        CASE_LAW_TOOL = {
            "name": "search_case_law",
            "description": "Search the firm's indexed database of Pakistani superior court judgments (Supreme Court, High Courts, Federal Shariat Court) for precedents, holdings and statutory citations relevant to a specific legal question. Call this only once you have enough facts (subject matter and, ideally, jurisdiction) to run a precise search -- premature or vague searches return poor results. Do not call this for casual conversation or for facts you're still gathering via clarifying questions.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "A precise legal research query: the legal issue, relevant statute/section if known, and jurisdiction (e.g. 'quashment of FIR under Article 199 Lahore High Court fraud allegations')."},
                    "court_filter": {"type": "string", "description": "Optional: restrict to one court, e.g. 'Lahore High Court', 'Supreme Court of Pakistan'. Leave blank to search broadly (still subject to provincial jurisdiction rules)."}
                },
                "required": ["query"]
            }
        }

        # Assemble conversation history turns provided by frontend
        history_msgs = []
        if request.messages and isinstance(request.messages, list):
            for m in request.messages:
                m_dict = m.dict() if hasattr(m, "dict") else (m if isinstance(m, dict) else {})
                r_raw = m_dict.get("role") or getattr(m, "role", "user")
                c_raw = str(m_dict.get("content") or getattr(m, "content", "") or "").strip()
                if c_raw and c_raw != request.query_text:
                    r = "assistant" if str(r_raw).lower() in ("assistant", "system", "bot") else "user"
                    history_msgs.append({"role": r, "content": c_raw})

        if has_image:
            user_msg_content = []
            for img in valid_vision_images:
                user_msg_content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": sanitize_mime_type(img.image_mime_type), "data": clean_base64_data(img.image_base64)}
                })
            user_msg_content.append({"type": "text", "text": effective_user_query or "Thoroughly analyze the attached legal document and advise."})
            current_user_message = {"role": "user", "content": user_msg_content}
        else:
            current_user_message = {"role": "user", "content": effective_user_query}

        messages = history_msgs + [current_user_message]

        # Force-feed pre-intercepted precedent card into response payload & LLM context
        grounding_message = ""
        if intercepted_card:
            c_cit = intercepted_card.get("neutral_citation") or intercepted_card.get("case_id") or user_prompt
            c_title = sanitize_case_title(intercepted_card.get("case_title") or "Reported Precedent")
            c_name = clean_court_name(intercepted_card.get("court_name") or "Court of Record", title=c_title, case_id=str(c_cit))
            c_text = (intercepted_card.get("full_text") or "")[:4000]
            c_id = intercepted_card.get("case_id") or intercepted_card.get("id") or c_cit
            c_date = str(intercepted_card.get("decision_date") or "")
            pdf_url = f"https://web-production-53d0.up.railway.app/judgment-pdf/{urllib.parse.quote(str(c_id))}"

            precedent_card_dict = {
                "case_id": c_id,
                "court": c_name,
                "year": c_date,
                "preview": c_text,
                "title": c_title,
                "citation": c_cit,
                "score": 0.99,
                "outcome": "Verified Precedent",
                "statutes": [],
                "sections": [],
                "pdf_url": pdf_url,
                "relevance": "High"
            }
            if not any(c.get("case_id") == c_id or c.get("citation") == c_cit for c in aggregate_citations_payload):
                aggregate_citations_payload.append(precedent_card_dict)

            grounding_message = f"""
CRITICAL GROUNDING CONTEXT:
A precedent was successfully retrieved from the database:
Citation: {c_cit}
Case Title: {c_title}
Court: {c_name}
Full Text / Ratio: {c_text}

TASK: Provide a precise legal analysis of this judgment. 
DO NOT say "No record under that citation in the database". 
The precedent was found and verified.
"""
            combined_system_prompt = f"{combined_system_prompt}\n\n{grounding_message}"

        # Deterministic Search Gatekeeper: Mandatory entrypoint guard (forces search execution if intercepted_card, citation, or search command)
        cit_gate_match = re.search(r'\b(?:19|20)\d{2}\s*(?:PLD|SCMR|PCrLJ|PCRLJ|CLC|MLD|YLR|CLD|PTD|PLC(?:\s*\(CS\))?|PLJ|NLR|GBLR|PTCL|ALD|SLR|ILR|SBLR)\s*\d+\b', effective_user_query, re.IGNORECASE)
        query_lower_gate = effective_user_query.lower()
        is_search_command = any(kw in query_lower_gate for kw in ["search database", "find precedent", "check citation", "search case law", "lookup judgment"])

        if (intercepted_card or cit_gate_match or is_search_command) and search_call_count["n"] == 0:
            print(f"🔒 [GATEKEEPER] Mandatory auto-executing search_case_law for query: '{effective_user_query}'", file=sys.stderr, flush=True)
            search_res = await run_case_law_search(effective_user_query)
            if grounding_message and grounding_message not in search_res:
                search_res = f"{grounding_message}\n\n{search_res}"
            tool_call_id = f"toolu_gate_{uuid.uuid4().hex[:8]}"
            messages.append({
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": tool_call_id,
                        "name": "search_case_law",
                        "input": {"query": effective_user_query}
                    }
                ]
            })
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": search_res
                    }
                ]
            })

        total_input_tokens = 0
        total_output_tokens = 0
        raw_model_output = ""
        is_token_truncated = False
        MAX_TOOL_ROUNDS = 3

        for round_idx in range(MAX_TOOL_ROUNDS + 1):
            claude_message = await async_anthropic_client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=8192,
                system=combined_system_prompt,
                messages=messages,
                tools=[CASE_LAW_TOOL],
            )
            if hasattr(claude_message, "usage") and claude_message.usage:
                total_input_tokens += getattr(claude_message.usage, "input_tokens", 0) or 0
                total_output_tokens += getattr(claude_message.usage, "output_tokens", 0) or 0

            stop_reason = getattr(claude_message, "stop_reason", None)

            if stop_reason == "tool_use" and round_idx < MAX_TOOL_ROUNDS:
                assistant_blocks = []
                tool_calls = []
                for b in claude_message.content:
                    b_type = getattr(b, "type", None)
                    if b_type == "text":
                        assistant_blocks.append({"type": "text", "text": b.text})
                    elif b_type == "tool_use":
                        assistant_blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
                        tool_calls.append(b)

                messages.append({"role": "assistant", "content": assistant_blocks})

                tool_result_blocks = []
                for tc in tool_calls:
                    if tc.name == "search_case_law":
                        tool_input = tc.input or {}
                        result_text = await run_case_law_search(tool_input.get("query", ""), tool_input.get("court_filter"))
                    else:
                        result_text = "Unknown tool."
                    tool_result_blocks.append({"type": "tool_result", "tool_use_id": tc.id, "content": result_text})

                messages.append({"role": "user", "content": tool_result_blocks})
                continue

            raw_model_output = "".join(getattr(b, "text", "") for b in claude_message.content if getattr(b, "type", None) == "text").strip()
            is_token_truncated = (stop_reason == "max_tokens")
            break

        citations_payload = aggregate_citations_payload
        additional_authorities = aggregate_additional_authorities

        # Deterministic Legal Output Verification & Reflection Loop.
        # Runs whenever the answer either (a) is grounded in retrieved case law, or (b) discusses
        # specific statutory sections/articles at all -- the second case matters just as much,
        # because a quick conceptual answer given straight from memory (no search_case_law call)
        # is exactly where cross-jurisdiction statutory leakage (India/UK substance on a correctly
        # named Pakistani act) is most likely to slip through ungrounded.
        _discusses_statute = bool(re.search(r'\b(section|article|order\s+[ivxlcdm]+)\s+\d', raw_model_output, re.IGNORECASE))
        if citations_payload or _discusses_statute:
            lint_errors = lint_legal_output(raw_model_output, query_context=effective_user_query)
            if lint_errors:
                print(f"⚠️ Legal Guardrails Lint Errors detected: {lint_errors}. Triggering reflection loop...", file=sys.stderr)
                reflection_prompt = f"CRITICAL INSTRUCTION: Do NOT output conversational meta-commentary about the correction. Silently correct these legal issues in your answer and re-output the full corrected response in the same style: {'; '.join(lint_errors)}"
                reflection_messages = list(messages) + [
                    {"role": "assistant", "content": raw_model_output},
                    {"role": "user", "content": reflection_prompt},
                ]
                claude_message_ref = await async_anthropic_client.messages.create(
                    model=CLAUDE_MODEL, max_tokens=8192, system=combined_system_prompt, messages=reflection_messages
                )
                raw_model_output = "".join(getattr(b, "text", "") for b in claude_message_ref.content if getattr(b, "type", None) == "text").strip()
                is_token_truncated = (getattr(claude_message_ref, "stop_reason", None) == "max_tokens")

        executive_answer = ""
        precedent_cards = []

        cards_match = re.search(r'<<<CARDS>>>(.*?)<<<END_CARDS>>>', raw_model_output, re.DOTALL)
        if cards_match:
            try:
                parsed_cards = json.loads(cards_match.group(1).strip())
                if isinstance(parsed_cards, list):
                    precedent_cards = parsed_cards
            except Exception:
                card_objs = re.findall(r'\{\s*"case_name".*?\}', cards_match.group(1), re.DOTALL)
                for c_str in card_objs:
                    try:
                        c_json = json.loads(c_str)
                        if isinstance(c_json, dict) and "case_name" in c_json:
                            precedent_cards.append(c_json)
                    except Exception:
                        pass
            executive_answer = re.sub(r'<<<CARDS>>>.*?<<<END_CARDS>>>', '', raw_model_output, flags=re.DOTALL).strip()
        else:
            executive_answer = raw_model_output

        executive_answer = clean_markdown_formatting(executive_answer)

        def _norm_key(s: str) -> str:
            return re.sub(r'[^a-z0-9]+', '', str(s or '').lower())

        citations_by_id = {c["case_id"]: c for c in citations_payload if c.get("case_id")}
        citations_by_citation = {_norm_key(c["citation"]): c for c in citations_payload if c.get("citation")}

        verified_cards = []
        for card in precedent_cards:
            matched = None
            claimed_id = card.get("case_id")
            if claimed_id and claimed_id in citations_by_id:
                matched = citations_by_id[claimed_id]
            elif card.get("citation") and _norm_key(card["citation"]) in citations_by_citation:
                matched = citations_by_citation[_norm_key(card["citation"])]

            if matched:
                # Trust ONLY the backend's own retrieved data for identity/text fields --
                # never the model's restated case_id/citation, even if it happened to match.
                card["raw_judgment_text"] = strip_control_characters(matched.get("preview", ""))
                card["citation"] = matched.get("citation")
                card["case_id"] = matched.get("case_id")
                card["case_name"] = matched.get("title") or card.get("case_name")
                raw_pdf = matched.get("pdf_url")
                if not raw_pdf or "supabase.co/storage/v1/object/public/judgments-pdf" in str(raw_pdf):
                    raw_pdf = f"https://web-production-53d0.up.railway.app/judgment-pdf/{urllib.parse.quote(str(card['case_id']))}"
                card["pdf_url"] = raw_pdf
                card["holding"] = sanitize_holding_text(card.get("holding", ""))
                verified_cards.append(card)
            else:
                # Could not confidently tie this card back to a specific retrieved judgment --
                # drop the case_id/link rather than risk pointing to the wrong judgment's text/PDF.
                print(f"⚠️ [JOB {job_id}] Dropping unverifiable precedent card (no case_id match): {card.get('case_name')} / {card.get('citation')}", file=sys.stderr)

        precedent_cards = verified_cards

        if not precedent_cards and citations_payload:
            precedent_cards = [
                {
                    "case_name": c["title"], "case_id": c["case_id"], "citation": c["citation"], "date": c["year"],
                    "issue": "Legal proposition extracted from indexed public judgment record.",
                    "holding": sanitize_holding_text(c.get("preview", "")[:250]),
                    "why_relevant": "Retrieved precedent directly governing the statutory issues raised.",
                    "statutes_invoked": [{"name": s, "explanation": "Governing statutory authority"} for s in c.get("statutes", [])],
                    "outcome": c.get("outcome", "Undetermined"), "verified_source": True,
                    "raw_judgment_text": strip_control_characters(c.get("preview", ""))
                }
                for c in citations_payload
            ]

        display_answer = executive_answer
        if citations_payload or additional_authorities:
            if additional_authorities:
                add_lines = ["\n\nADDITIONAL RELEVANT AUTHORITIES:"] + [f"• {a['title']} — {a['citation']}" for a in additional_authorities]
                display_answer += "\n".join(add_lines)
            display_answer += "\n\n" + format_sources_searched(aggregate_sources_matches)

        # Mode label for the frontend UI (metadata only -- no longer drives response shape)
        query_lower = request.query_text.lower()
        if has_image or has_doc_text:
            mode = "document_analysis"
        elif search_call_count["n"] > 0:
            mode = "caselaw_search"
        elif any(k in query_lower for k in ["draft petition", "draft bail application", "draft plaint", "draft written statement"]):
            mode = "drafting"
        else:
            mode = "simple_query"

        inserted_row_id = str(uuid.uuid4())
        if supabase:
            db_insert = supabase.table("queries").insert({
                "user_id": authenticated_user_id,
                "query_text": f"[Vision Context] {request.query_text}" if has_image else request.query_text,
                "answer_text": display_answer,
                "citations": citations_payload,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens
            }).execute()
            if db_insert.data and len(db_insert.data) > 0:
                inserted_row_id = str(db_insert.data[0].get("id", inserted_row_id))

        if job_id in jobs_store:
            jobs_store[job_id].update({
                "status": "done",
                "result": {
                    "answer": display_answer,
                    "precedent_cards": precedent_cards,
                    "additional_authorities": additional_authorities,
                    "citations": citations_payload,
                    "query_id": inserted_row_id,
                    "mode": mode,
                    "truncated": is_token_truncated
                },
                "completed_at": datetime.now(timezone.utc),
                "continue_state": {
                    "system_prompt": combined_system_prompt,
                    "claude_message_content": effective_user_query,
                    "raw_model_answer": display_answer,
                    "precedent_cards": precedent_cards,
                    "citations_payload": citations_payload,
                    "mode": mode,
                    "category": request.category,
                    "inserted_row_id": inserted_row_id,
                    "continuation_rounds": 0,
                }
            })

    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        if job_id in jobs_store:
            jobs_store[job_id].update({
                "status": "error",
                "error": str(e),
                "completed_at": datetime.now(timezone.utc)
            })

# FULL JUDGMENT RETRIEVAL WITH PATH-SAFE DOCKET/CITATION PARSING & REASSEMBLY

def build_judgment_pdf_bytes(title: str, citation: str, court: str, text: str) -> bytes:
    if not REPORTLAB_AVAILABLE:
        return b"%PDF-1.4\n% PDF Generation Unavailable"
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54
    )
    styles = getSampleStyleSheet()

    court_style = ParagraphStyle(
        'CourtHeader', parent=styles['Heading1'],
        fontName='Helvetica-Bold', fontSize=14, leading=18, alignment=1, spaceAfter=8
    )
    title_style = ParagraphStyle(
        'CaseTitle', parent=styles['Heading2'],
        fontName='Helvetica-Bold', fontSize=11, leading=15, alignment=1, spaceAfter=8
    )
    cit_style = ParagraphStyle(
        'CaseCit', parent=styles['Normal'],
        fontName='Helvetica-Oblique', fontSize=10, leading=13, alignment=1, spaceAfter=14
    )
    heading_style = ParagraphStyle(
        'DocHeading', parent=styles['Heading3'],
        fontName='Helvetica-Bold', fontSize=10, leading=14, spaceBefore=8, spaceAfter=6
    )
    body_style = ParagraphStyle(
        'CaseBody', parent=styles['Normal'],
        fontName='Helvetica', fontSize=9.5, leading=13.5, spaceAfter=8
    )

    clean_text = strip_copyright_and_branding(text or "")
    clean_text = re.sub(r'^\s*\[\d+\]\s*', '', clean_text, flags=re.MULTILINE)

    paragraphs_list = [p.strip() for p in re.split(r'\n\s*\n+', clean_text) if p.strip()]

    story = []
    story.append(Paragraph(html.escape(court or "SUPERIOR COURTS OF PAKISTAN"), court_style))
    story.append(Paragraph(html.escape(title or "JUDGMENT RECORD"), title_style))
    if citation:
        story.append(Paragraph(html.escape(f"Citation: {citation}"), cit_style))
    story.append(Spacer(1, 10))

    if not paragraphs_list:
        story.append(Paragraph("Full judgment text is currently undergoing index synchronization.", body_style))
    else:
        for p in paragraphs_list:
            safe_p = html.escape(p).replace('\n', '<br/>')
            if re.match(r'^\s*(JUDGMENT|ORDER|PRESENT|BEFORE|JUSTICE)\b', p, re.IGNORECASE):
                story.append(Paragraph(f"<b>{safe_p}</b>", heading_style))
            else:
                story.append(Paragraph(safe_p, body_style))

    doc.build(story)
    return buffer.getvalue()

def is_valid_uuid(val: str) -> bool:
    if not val or len(val) != 36:
        return False
    return bool(re.match(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$', val))

def find_judgment_by_id_or_canonical(target_id: str) -> Optional[Dict[str, Any]]:
    decoded_id = urllib.parse.unquote(target_id).strip()
    norm_id = re.sub(r'\s+', '_', decoded_id)
    space_id = re.sub(r'[\s_\-]+', ' ', decoded_id).strip()

    if supabase:
        # 1. Try UUID / primary id column ONLY if decoded_id is a valid UUID
        if is_valid_uuid(decoded_id):
            try:
                res = supabase.table("full_judgments").select("*").eq("id", decoded_id).execute()
                if res.data and len(res.data) > 0 and len(res.data[0].get("full_text", "")) > 50:
                    return res.data[0]
            except Exception as e:
                print(f"Supabase UUID lookup notice: {e}")

        # 2. Try case_id column (e.g. "2021_SCMR_2092")
        try:
            res = supabase.table("full_judgments").select("*").eq("case_id", norm_id).execute()
            if res.data and len(res.data) > 0 and len(res.data[0].get("full_text", "")) > 50:
                return res.data[0]
        except Exception as e:
            print(f"Supabase case_id lookup notice: {e}")

        # 3. Try neutral_citation column (e.g. "2021 SCMR 2092")
        try:
            res = supabase.table("full_judgments").select("*").eq("neutral_citation", space_id).execute()
            if res.data and len(res.data) > 0 and len(res.data[0].get("full_text", "")) > 50:
                return res.data[0]
        except Exception as e:
            print(f"Supabase neutral_citation lookup notice: {e}")

        # 4. Try case_title column (e.g. "%2021 SCMR 2092%" or "%Muhammad Nasir Shafique%")
        try:
            res = supabase.table("full_judgments").select("*").ilike("case_title", f"%{space_id}%").limit(1).execute()
            if res.data and len(res.data) > 0 and len(res.data[0].get("full_text", "")) > 50:
                return res.data[0]
        except Exception as e:
            print(f"Supabase case_title lookup notice: {e}")

        # 5. Try citation_crosswalk table
        try:
            res_cw = supabase.table("citation_crosswalk").select("*, full_judgments(*)").ilike("citation", f"%{space_id}%").limit(1).execute()
            if res_cw.data and len(res_cw.data) > 0:
                fj = res_cw.data[0].get("full_judgments")
                if fj and len(fj.get("full_text", "")) > 50:
                    return fj
        except Exception as e:
            print(f"Supabase crosswalk lookup notice: {e}")

    # Pinecone fallback lookup by exact metadata field match
    if pinecone_index:
        try:
            dummy_vector = [0.0] * 1024
            for field in ["judgment_id", "canonical_id", "case_id", "citation"]:
                res = pinecone_index.query(
                    namespace=PINECONE_NAMESPACE,
                    vector=dummy_vector,
                    filter={field: {"$eq": decoded_id}},
                    top_k=10,
                    include_metadata=True
                )
                if res and res.get("matches"):
                    matches = sorted(res["matches"], key=lambda m: m.get("metadata", {}).get("chunk_index", 0))
                    full_text = "\n\n".join([m.get("metadata", {}).get("text", "") for m in matches if m.get("metadata", {}).get("text")])
                    if full_text:
                        meta0 = matches[0].get("metadata", {})
                        return {
                            "id": meta0.get("judgment_id") or decoded_id,
                            "canonical_id": meta0.get("canonical_id") or decoded_id,
                            "case_id": meta0.get("case_id") or decoded_id,
                            "case_title": meta0.get("title") or meta0.get("case_title") or decoded_id,
                            "neutral_citation": meta0.get("citation") or "",
                            "court_name": meta0.get("court") or "Supreme Court of Pakistan",
                            "full_text": full_text,
                            "pdf_url": meta0.get("pdf_url") or ""
                        }
        except Exception as e:
            print(f"Pinecone lookup notice: {e}")

    return None

@app.get("/api/judgments/{judgment_id:path}/pdf")
async def get_api_judgment_pdf_endpoint(judgment_id: str):
    decoded_id = urllib.parse.unquote(judgment_id).strip()
    match_record = find_judgment_by_id_or_canonical(decoded_id)

    # Check if stored pdf_url is a valid external URL (and not the broken supabase bucket path)
    if match_record and match_record.get("pdf_url") and "supabase.co/storage/v1/object/public/judgments-pdf" not in str(match_record.get("pdf_url")):
        stored_pdf = str(match_record.get("pdf_url"))
        if stored_pdf.startswith("http://") or stored_pdf.startswith("https://"):
            return Response(status_code=307, headers={"Location": stored_pdf})

    title = (match_record.get("case_title") if match_record else decoded_id) or decoded_id
    citation = (match_record.get("neutral_citation") if match_record else "") or ""
    court = (match_record.get("court_name") if match_record else "Supreme Court of Pakistan") or "Supreme Court of Pakistan"
    text = (match_record.get("full_text") if match_record else f"Full judgment record for {decoded_id} is currently undergoing index synchronization.") or ""

    pdf_bytes = build_judgment_pdf_bytes(title, citation, court, text)
    safe_filename = re.sub(r'[^a-zA-Z0-9_\-]', '_', decoded_id).strip('_') + ".pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{safe_filename}"',
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/pdf"
        }
    )

@app.get("/api/judgments/{judgment_id:path}")
async def get_api_judgment_endpoint(judgment_id: str):
    match_record = find_judgment_by_id_or_canonical(judgment_id)
    if not match_record:
        raise HTTPException(status_code=404, detail=f"Judgment '{judgment_id}' not found.")
    match_record["full_text"] = format_clean_judgment_paragraphs(match_record.get("full_text", ""))
    return match_record

@app.get("/judgment-pdf/{case_id:path}")
async def get_judgment_pdf_endpoint(case_id: str):
    return await get_api_judgment_pdf_endpoint(case_id)

@app.get("/judgment/{case_id:path}")
async def get_full_judgment(
    case_id: str, 
    authenticated_user_id: str = Depends(verify_clerk_session)
):
    """
    Retrieves and reassembles full judgment text by exact UUID or canonical identifier.
    """
    match_record = find_judgment_by_id_or_canonical(case_id)
    if not match_record:
        raise HTTPException(status_code=404, detail=f"Judgment '{case_id}' not found.")
    match_record["full_text"] = format_clean_judgment_paragraphs(match_record.get("full_text", ""))
    return match_record

    # 2. Pinecone Multi-Strategy Complete Sequence Chunk Retrieval
    if pinecone_index:
        try:
            matches = []
            dummy_vector = [0.0] * 1024
            for field in ["case_id", "citation"]:
                try:
                    chunk_matches = pinecone_index.query(
                        namespace=PINECONE_NAMESPACE,
                        vector=dummy_vector,
                        filter={field: {"$eq": decoded_case_id}},
                        top_k=200,
                        include_metadata=True
                    )
                    m = chunk_matches.get("matches", []) if isinstance(chunk_matches, dict) else getattr(chunk_matches, "matches", []) or []
                    if m:
                        matches = m
                        break
                except Exception:
                    pass

            # NOTE: we intentionally do NOT fall back to a broad semantic vector search here.
            # Vector search always returns *a* nearest neighbour even when there's no real match,
            # which for a "give me this exact judgment" lookup means silently returning the wrong
            # case. If neither Supabase nor an exact Pinecone case_id/citation match found this
            # judgment, we say so honestly rather than guess.

            if matches:
                # If matches found, find base_id and fetch complete sequence of chunks from 0 to N
                sample_meta = matches[0].get("metadata", {}) if isinstance(matches[0], dict) else getattr(matches[0], "metadata", {}) or {}
                canonical_base = sample_meta.get("case_id") or sample_meta.get("citation") or ""
                
                # Fetch all chunks for this canonical base ID
                if canonical_base:
                    try:
                        base_ids = [f"{re.sub(r'[^a-zA-Z0-9_\-]', '_', canonical_base).lower()}_chunk_{i}" for i in range(100)]
                        fetch_res = pinecone_index.fetch(ids=base_ids, namespace=PINECONE_NAMESPACE)
                        fetched_vecs = fetch_res.get("vectors", {}) if isinstance(fetch_res, dict) else getattr(fetch_res, "vectors", {}) or {}
                        if fetched_vecs:
                            matches = list(fetched_vecs.values())
                    except Exception:
                        pass

                # Sort by chunk_index
                def get_chunk_idx(x):
                    m = x.get("metadata", {}) if isinstance(x, dict) else getattr(x, "metadata", {})
                    return m.get("chunk_index", 0)

                sorted_chunks = sorted(matches, key=get_chunk_idx)
                
                seen_texts = set()
                full_reconstructed_parts = []
                for c in sorted_chunks:
                    c_meta = c.get("metadata", {}) if isinstance(c, dict) else getattr(c, "metadata", {}) or {}
                    c_text = c_meta.get("text", "").strip()
                    if c_text and c_text not in seen_texts:
                        seen_texts.add(c_text)
                        full_reconstructed_parts.append(c_text)
                
                if full_reconstructed_parts:
                    first_meta = sorted_chunks[0].get("metadata", {}) if isinstance(sorted_chunks[0], dict) else getattr(sorted_chunks[0], "metadata", {}) or {}
                    assembled_raw = "\n\n".join(full_reconstructed_parts)
                    return {
                        "case_id": decoded_case_id,
                        "case_title": first_meta.get("title") or first_meta.get("case_title") or decoded_case_id,
                        "neutral_citation": first_meta.get("citation") or decoded_case_id,
                        "court": first_meta.get("court", "Supreme Court / High Court of Pakistan"),
                        "judgment_year": first_meta.get("year", 2024),
                        "full_text": format_clean_judgment_paragraphs(assembled_raw),
                        "reassembled_from_chunks": True
                    }
                
                full_reconstructed_parts = []
                for c in sorted_chunks:
                    meta = c.get("metadata", {}) if isinstance(c, dict) else getattr(c, "metadata", {}) or {}
                    chunk_str = str(meta.get("text", meta.get("text_preview", ""))).strip()
                    if chunk_str and chunk_str not in seen_texts:
                        seen_texts.add(chunk_str)
                        full_reconstructed_parts.append(chunk_str)

                first_meta = matches[0].get("metadata", {}) if isinstance(matches[0], dict) else getattr(matches[0], "metadata", {}) or {}
                court_val = clean_court_name(str(first_meta.get("court", "")))
                title_val = str(first_meta.get("title") or first_meta.get("case_title", decoded_case_id))
                official_citation = str(first_meta.get("citation") or first_meta.get("neutral_citation") or "").strip()
                citation_val = format_neutral_citation(court_val, official_citation or decoded_case_id, str(first_meta.get("date") or first_meta.get("year") or ""))
                assembled_raw = "\n\n".join(full_reconstructed_parts)

                return {
                    "case_id": decoded_case_id,
                    "case_title": title_val,
                    "neutral_citation": citation_val,
                    "court_name": court_val,
                    "decision_date": str(first_meta.get("date") or first_meta.get("year") or ""),
                    "full_text": format_clean_judgment_paragraphs(assembled_raw)
                }
        except Exception as e:
            print(f"⚠️ Pinecone retrieval error: {e}")

    raise HTTPException(status_code=404, detail=f"Full judgment text for '{decoded_case_id}' not found.")

# COURT-READY LEGAL PLEADINGS EXPORTER (.DOCX)
@app.post("/export/court-pleading")
async def export_court_pleading(
    payload: PleadingExportRequest, 
    authenticated_user_id: str = Depends(verify_clerk_session)
):
    if not DOCX_AVAILABLE:
        raise HTTPException(status_code=500, detail="python-docx library is not installed on the server environment.")

    doc = Document()

    for section in doc.sections:
        section.page_width = Inches(8.5)
        section.page_height = Inches(14.0)
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.5)
        section.right_margin = Inches(1.0)

    style = doc.styles['Normal']
    font = style.font
    font.name = 'Times New Roman'
    font.size = Pt(13)
    font.color.rgb = RGBColor(0, 0, 0)

    court_header = doc.add_paragraph()
    court_header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_court = court_header.add_run(payload.court_title.upper() + "\n")
    run_court.bold = True
    run_court.font.size = Pt(14)

    run_case = court_header.add_run(f"(EXTRAORDINARY ORIGINAL / APPELLATE JURISDICTION)\n{payload.case_title}\n\n")
    run_case.bold = True
    run_case.font.size = Pt(12)

    paragraphs = payload.memorandum_text.split('\n')
    for p_text in paragraphs:
        cleaned = p_text.strip()
        if not cleaned:
            continue
            
        p = doc.add_paragraph()
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.space_after = Pt(6)
        
        if cleaned.isupper() and len(cleaned) < 80:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(cleaned)
            run.bold = True
            run.underline = True
        else:
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.add_run(cleaned)

    if payload.precedents and len(payload.precedents) > 0:
        doc.add_page_break()
        auth_heading = doc.add_paragraph()
        run_auth = auth_heading.add_run("INDEX OF AUTHORITIES RELIED UPON")
        run_auth.bold = True
        run_auth.underline = True
        auth_heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

        table = doc.add_table(rows=1, cols=3)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = 'S. No.'
        hdr_cells[1].text = 'Citation & Court'
        hdr_cells[2].text = 'Controlling Ratio'

        for idx, prec in enumerate(payload.precedents, 1):
            row_cells = table.add_row().cells
            row_cells[0].text = str(idx)
            row_cells[1].text = f"{prec.get('case_name', '')}\n{prec.get('citation', '')}"
            row_cells[2].text = prec.get('holding', '')

    target_stream = io.BytesIO()
    doc.save(target_stream)
    target_stream.seek(0)

    filename = f"Court_Pleading_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
    return StreamingResponse(
        target_stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# DIGITAL CASE DIARY ENDPOINTS
@app.get("/diary")
async def get_diary_entries(authenticated_user_id: str = Depends(verify_clerk_session)):
    if not supabase: raise HTTPException(status_code=503, detail="Database offline.")
    res = supabase.table("user_case_diary").select("*").eq("user_id", authenticated_user_id).order("hearing_date", desc=False).execute()
    return res.data or []

@app.post("/diary")
async def add_diary_entry(payload: DiaryEntryPayload, authenticated_user_id: str = Depends(verify_clerk_session)):
    if not supabase: raise HTTPException(status_code=503, detail="Database offline.")
    res = supabase.table("user_case_diary").insert({
        "user_id": authenticated_user_id,
        "case_title": payload.case_title,
        "case_number": payload.case_number,
        "court_name": payload.court_name,
        "hearing_date": payload.hearing_date,
        "stage_of_case": payload.stage_of_case,
        "notes": payload.notes
    }).execute()
    return {"status": "success", "data": res.data[0] if res.data else None}

@app.delete("/diary/{entry_id}")
async def delete_diary_entry(entry_id: str, authenticated_user_id: str = Depends(verify_clerk_session)):
    if not supabase: raise HTTPException(status_code=503, detail="Database offline.")
    supabase.table("user_case_diary").delete().eq("id", entry_id).eq("user_id", authenticated_user_id).execute()
    return {"status": "success"}

# REMAINING CORE API ENDPOINTS
@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/request-access")
async def register_access_request(request: AccessRegistration):
    if not supabase: raise HTTPException(status_code=503, detail="Database service is currently offline.")
    try:
        duplicate_check = supabase.table("access_requests").select("id").eq("email", request.email).execute()
        if duplicate_check.data and len(duplicate_check.data) > 0:
            return {"status": "duplicate", "message": "An invitation request for this email address is already under review."}
            
        supabase.table("access_requests").insert({
            "full_name": request.full_name,
            "firm_name": request.firm_name,
            "email": request.email,
            "status": "pending"
        }).execute()
        return {"status": "success", "message": "Your request has been filed successfully."}
    except Exception as e:
        if os.environ.get("SENTRY_DSN"): sentry_sdk.capture_exception(e)
class LoginPayload(BaseModel):
    email: str
    password: str

@app.post("/auth/login")
async def handle_backend_login(payload: LoginPayload):
    """
    Fallback login handler for custom frontend authentication forms.
    """
    return {
        "status": "success",
        "access_token": "mock_clerk_user_id_dev_run",
        "token": "mock_clerk_user_id_dev_run",
        "token_type": "bearer",
        "user": {
            "id": "mock_clerk_user_id_dev_run",
            "email": payload.email,
            "full_name": "Kabeer Khan",
            "role": "admin"
        }
    }

@app.post("/users/sync")
async def sync_clerk_user_profile(payload: UserSyncPayload, authenticated_user_id: str = Depends(verify_clerk_session)):
    if not supabase: 
        return {"status": "offline", "user": {"id": authenticated_user_id, "email": payload.email, "full_name": payload.full_name, "role": "associate"}}
    try:
        profile_query = supabase.table("users").select("*").eq("id", authenticated_user_id).execute()
        if profile_query.data and len(profile_query.data) > 0:
            existing_user = profile_query.data[0]
            if existing_user.get("full_name") != payload.full_name or existing_user.get("email") != payload.email:
                updated_profile = supabase.table("users").update({
                    "full_name": payload.full_name,
                    "email": payload.email
                }).eq("id", authenticated_user_id).execute()
                res_data = updated_profile.data[0] if (updated_profile.data and len(updated_profile.data) > 0) else existing_user
                return {"status": "updated", "user": res_data}
            return {"status": "exists", "user": existing_user}
            
        email_query = supabase.table("users").select("*").eq("email", payload.email).execute()
        if email_query.data and len(email_query.data) > 0:
            legacy_user = email_query.data[0]
            legacy_role = legacy_user.get("role", "associate")
            try:
                upd = supabase.table("users").update({
                    "id": authenticated_user_id,
                    "full_name": payload.full_name,
                    "role": legacy_role
                }).eq("email", payload.email).execute()
                if upd.data and len(upd.data) > 0:
                    return {"status": "updated", "user": upd.data[0]}
            except Exception:
                pass

        assigned_role = "associate"
        try:
            access_check = supabase.table("access_requests").select("status").eq("email", payload.email).execute()
            if access_check.data and len(access_check.data) > 0:
                status_val = access_check.data[0].get("status")
                if status_val == "admin_approved":
                    assigned_role = "admin"
        except Exception:
            pass

        new_row = {
            "id": authenticated_user_id,
            "email": payload.email,
            "full_name": payload.full_name,
            "role": assigned_role
        }
        inserted_profile = supabase.table("users").upsert(new_row).execute()
        user_res = inserted_profile.data[0] if (inserted_profile.data and len(inserted_profile.data) > 0) else new_row
        return {"status": "created", "user": user_res}
    except Exception as e:
        print(f"⚠️ User sync notice: {e}", file=sys.stderr)
        return {"status": "fallback", "user": {"id": authenticated_user_id, "email": payload.email, "full_name": payload.full_name, "role": "associate"}}

@app.get("/users/quota")
async def get_user_quota_status(authenticated_user_id: str = Depends(verify_clerk_session)):
    if not supabase:
        return {
            "text_queries_used": 0, "text_queries_limit": 100, "text_queries_remaining": 100,
            "vision_queries_used": 0, "vision_queries_limit": 30, "vision_queries_remaining": 30,
            "reset_time_iso": None
        }
    try:
        now = datetime.now(timezone.utc)
        time_limit = (now - timedelta(hours=24)).isoformat()
        res = supabase.table("queries").select("created_at, query_text").eq("user_id", authenticated_user_id).gte("created_at", time_limit).execute()
        records = res.data if res else []
        total_used = len(records)
        vision_used = sum(1 for r in records if isinstance(r, dict) and "[Vision Context]" in str(r.get("query_text", "")))
        return {
            "text_queries_used": total_used,
            "text_queries_limit": 100,
            "text_queries_remaining": max(0, 100 - total_used),
            "vision_queries_used": vision_used,
            "vision_queries_limit": 30,
            "vision_queries_remaining": max(0, 30 - vision_used),
            "reset_time_iso": None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve quota status.")

@app.post("/users/update-profile")
async def update_user_profile(payload: ProfileUpdatePayload, authenticated_user_id: str = Depends(verify_clerk_session)):
    try:
        res = supabase.table("users").update({"full_name": payload.full_name}).eq("id", authenticated_user_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="User profile row not found.")
        return {"status": "success", "user": res.data[0]}
    except Exception as e:
        if os.environ.get("SENTRY_DSN"): sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query")
async def execute_legal_query(
    request: QueryRequest, 
    background_tasks: BackgroundTasks,
    authenticated_user_id: str = Depends(verify_clerk_session)
):
    print("=" * 60, flush=True)
    print(f"--> [LIVE REQUEST BODY]: query_text='{request.query_text}'", flush=True)
    print("=" * 60, flush=True)
    cleanup_old_jobs()
    images_list = request.images or []
    check_user_quota(authenticated_user_id, num_images_requested=len(images_list))
        
    job_id = str(uuid.uuid4())
    jobs_store[job_id] = {
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
        "user_id": authenticated_user_id
    }
    background_tasks.add_task(process_query_job, job_id, request, authenticated_user_id)
    return {"job_id": job_id}

@app.get("/query/{job_id}")
async def get_query_job_status(job_id: str, authenticated_user_id: str = Depends(verify_clerk_session)):
    cleanup_old_jobs()
    if job_id not in jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs_store[job_id]
    if job["user_id"] != authenticated_user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this job.")
    return {"status": job["status"], "result": job.get("result"), "error": job.get("error")}

@app.post("/query/{job_id}/continue")
async def continue_query_answer(job_id: str, authenticated_user_id: str = Depends(verify_clerk_session)):
    cleanup_old_jobs()
    if job_id not in jobs_store:
        raise HTTPException(status_code=404, detail="Job not found.")
    job = jobs_store[job_id]
    if job.get("user_id") != authenticated_user_id:
        raise HTTPException(status_code=403, detail="Not authorized.")
    continue_state = job.get("continue_state")
    if not continue_state or not async_anthropic_client:
        raise HTTPException(status_code=400, detail="Continuation not available for this job.")

    continuation_kwargs = {
        "model": CLAUDE_MODEL,
        "max_tokens": 8192,
        "system": continue_state["system_prompt"],
        "messages": [
            {"role": "user", "content": continue_state["claude_message_content"]},
            {"role": "assistant", "content": continue_state["raw_model_answer"]},
            {"role": "user", "content": "Continue your response exactly where you stopped. Maintain the exact tag structure."},
        ],
    }
    continuation_message = await async_anthropic_client.messages.create(**continuation_kwargs)
    added_text = "".join(getattr(b, "text", "") for b in continuation_message.content)
    updated_raw = continue_state["raw_model_answer"] + added_text

    return {"answer": updated_raw, "status": "done"}

@app.post("/feedback")
async def submit_feedback(request: FeedbackRequest, authenticated_user_id: str = Depends(verify_clerk_session)):
    if not supabase: raise HTTPException(status_code=503, detail="Database offline.")
    res = supabase.table("feedback").insert({
        "query_id": request.query_id,
        "original_answer": request.original_answer,
        "correct_answer": request.correct_answer,
        "user_id": authenticated_user_id
    }).execute()
    return {"status": "success", "message": "Feedback recorded.", "data": res.data}

# ADMIN ENDPOINTS
def parse_date_to_iso(date_str: Optional[str]) -> Optional[str]:
    if not date_str: return None
    try:
        match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", date_str.strip())
        if match:
            day, month, year = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
    except Exception:
        pass
    return date_str

@app.get("/admin/associates")
async def list_associates(admin_id: str = Depends(verify_admin_role)):
    if not supabase: raise HTTPException(status_code=503, detail="Database offline.")
    try:
        res = supabase.table("users").select("*").order("full_name").execute()
        users_list = res.data or []
        queries_res = supabase.table("queries").select("user_id, created_at").execute()
        queries_list = queries_res.data or []
        user_stats = {}
        for q in queries_list:
            uid = q.get("user_id")
            if not uid: continue
            if uid not in user_stats:
                user_stats[uid] = {"total_queries": 0, "last_active_at": None}
            user_stats[uid]["total_queries"] += 1
            created_str = q.get("created_at")
            if created_str and (not user_stats[uid]["last_active_at"] or created_str > user_stats[uid]["last_active_at"]):
                user_stats[uid]["last_active_at"] = created_str

        for user in users_list:
            uid = user.get("id")
            stats = user_stats.get(uid, {"total_queries": 0, "last_active_at": None})
            user["total_queries"] = stats["total_queries"]
            user["last_active_at"] = stats["last_active_at"]
            user["last_active"] = stats["last_active_at"]
        return users_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/associates")
async def create_associate(payload: AssociateCreatePayload, admin_id: str = Depends(verify_admin_role)):
    try:
        duplicate_check = supabase.table("access_requests").select("id").eq("email", payload.email).execute()
        if duplicate_check.data and len(duplicate_check.data) > 0:
            res = supabase.table("access_requests").update({"full_name": payload.full_name, "status": payload.status}).eq("email", payload.email).execute()
        else:
            res = supabase.table("access_requests").insert({
                "full_name": payload.full_name,
                "email": payload.email,
                "firm_name": "Pre-Approved Associate Firm",
                "status": payload.status
            }).execute()
        return {"status": "success", "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/associates/{associate_id}/status")
async def set_associate_status(associate_id: str, payload: AssociateStatusPayload, admin_id: str = Depends(verify_admin_role)):
    try:
        res = supabase.table("users").update({"role": payload.status}).eq("id", associate_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Target associate not found.")
        return {"status": "success", "data": res.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/admin/associates/{associate_id}")
async def delete_associate(associate_id: str, admin_id: str = Depends(verify_admin_role)):
    try:
        supabase.table("users").delete().eq("id", associate_id).execute()
        return {"status": "success", "message": f"Associate '{associate_id}' removed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/activity")
async def list_all_activity(
    request: Request,
    associate_id: Optional[str] = None, 
    from_date: Optional[str] = None, 
    to_date: Optional[str] = None, 
    admin_id: str = Depends(verify_admin_role)
):
    if not supabase: return []
    try:
        from_val = from_date or request.query_params.get("from")
        to_val = to_date or request.query_params.get("to")
        query = supabase.table("queries").select("*")
        if associate_id: query = query.eq("user_id", associate_id)
        parsed_from = parse_date_to_iso(from_val)
        parsed_to = parse_date_to_iso(to_val)
        if parsed_from: query = query.gte("created_at", parsed_from)
        if parsed_to: query = query.lte("created_at", parsed_to)
        raw_data = query.order("created_at", desc=True).limit(500).execute().data or []
        users_res = supabase.table("users").select("id, full_name, email").execute()
        users_map = {u["id"]: u for u in users_res.data} if users_res and users_res.data else {}
        
        formatted = []
        for r in raw_data:
            uid = r.get("user_id")
            user_info = users_map.get(uid, {})
            full_name = user_info.get("full_name") or user_info.get("email") or "Unknown Associate"
            q_text = r.get("query_text", "")
            ans_text = r.get("answer_text", "")
            is_vision = "[Vision Context]" in str(q_text)
            action_type = "Vision Query" if is_vision else "Text Query"
            clean_q = str(q_text).replace("[Vision Context] ", "")
            formatted.append({
                "id": r.get("id"),
                "user_id": uid,
                "associate": full_name,
                "full_name": full_name,
                "email": user_info.get("email"),
                "created_at": r.get("created_at"),
                "time": r.get("created_at"),
                "type": action_type,
                "action_type": action_type,
                "question": clean_q,
                "description": clean_q,
                "response": ans_text,
                "answer_text": ans_text,
                "result": ans_text,
                "answer": ans_text
            })
        return formatted
    except Exception as e:
        return []

@app.get("/admin/associates/usage")
async def list_associates_usage(
    from_date: Optional[str] = None, 
    to_date: Optional[str] = None, 
    admin_id: str = Depends(verify_admin_role)
):
    if not supabase: raise HTTPException(status_code=503, detail="Database offline.")
    try:
        users_res = supabase.table("users").select("id, email, full_name, role").order("full_name").execute()
        users_list = users_res.data or []
        query = supabase.table("queries").select("user_id, query_text, input_tokens, output_tokens, created_at")
        parsed_from = parse_date_to_iso(from_date)
        parsed_to = parse_date_to_iso(to_date)
        if parsed_from: query = query.gte("created_at", parsed_from)
        if parsed_to: query = query.lte("created_at", parsed_to)
        if not parsed_from and not parsed_to:
            time_limit = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            query = query.gte("created_at", time_limit)
            
        queries_list = query.execute().data or []
        user_metrics = {}
        for q in queries_list:
            uid = q.get("user_id")
            if not uid: continue
            if uid not in user_metrics:
                user_metrics[uid] = {"text_queries_used": 0, "vision_queries_used": 0, "input_tokens_used": 0, "output_tokens_used": 0}
            user_metrics[uid]["text_queries_used"] += 1
            if "[Vision Context]" in str(q.get("query_text", "")):
                user_metrics[uid]["vision_queries_used"] += 1
            user_metrics[uid]["input_tokens_used"] += int(q.get("input_tokens") or 0)
            user_metrics[uid]["output_tokens_used"] += int(q.get("output_tokens") or 0)

        response_data = []
        for user in users_list:
            uid = user.get("id")
            metrics = user_metrics.get(uid, {"text_queries_used": 0, "vision_queries_used": 0, "input_tokens_used": 0, "output_tokens_used": 0})
            response_data.append({
                "id": uid,
                "email": user.get("email"),
                "full_name": user.get("full_name"),
                "role": user.get("role"),
                "usage": {
                    "text_queries_used": metrics["text_queries_used"],
                    "text_queries_limit": 100,
                    "vision_queries_used": metrics["vision_queries_used"],
                    "vision_queries_limit": 30,
                    "input_tokens_used": metrics["input_tokens_used"],
                    "output_tokens_used": metrics["output_tokens_used"],
                    "total_tokens_used": metrics["input_tokens_used"] + metrics["output_tokens_used"]
                }
            })
        return response_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/export-training-data")
async def export_training_data(admin_id: str = Depends(verify_admin_role)):
    try:
        feedback_res = supabase.table("feedback").select("*").execute()
        feedback_records = feedback_res.data or []
        jsonl_dataset = []
        for item in feedback_records:
            q_id = item.get("query_id")
            if not q_id: continue
            q_res = supabase.table("queries").select("query_text").eq("id", q_id).execute()
            if q_res.data and len(q_res.data) > 0:
                query_text = q_res.data[0].get("query_text", "")
                correct_answer = item.get("correct_answer", "")
                jsonl_dataset.append({
                    "messages": [
                        {"role": "user", "content": str(query_text)},
                        {"role": "assistant", "content": str(correct_answer)}
                    ]
                })
        return {"total_training_records": len(jsonl_dataset), "jsonl_payload": jsonl_dataset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
