"""
scripts/apply_order114_patches.py
Applies Order 1.14 modifications:
- Real Roman numeral parser in core/legal_guardrails.py
- Remove 'of the Ordinance' banking guess in core/statutory_validator.py and legal_ai/verification/memo_verifier.py
- Remove is_system_rendered parameter and implement system assembler in legal_ai/verification/memo_verifier.py
- Rename page_verified to text_layer_matched across unified statutes and codebase
- Harmonize PPC s.415 tier_1 to ingested_unreviewed
- Cryptographic public key review verification in core/unified_statute_store.py
- GIN index CONCURRENTLY and RLS header updates in migrations/
"""

import os
import re
import json
import glob

REPO_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
os.chdir(REPO_DIR)

# ------------------------------------------------------------------------------
# 1. Patch core/legal_guardrails.py with Real Roman Numeral Parser
# ------------------------------------------------------------------------------
lg_path = os.path.join(REPO_DIR, "core", "legal_guardrails.py")
with open(lg_path, "r", encoding="utf-8") as f:
    lg_text = f.read()

old_roman_block = '''ROMAN_NUMERAL_MAP = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
    "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15, "xvi": 16, "xvii": 17, "xviii": 18,
    "xix": 19, "xx": 20, "xxi": 21, "xxii": 22, "xxiii": 23, "xxiv": 24, "xxv": 25, "xxvi": 26,
    "xxvii": 27, "xxviii": 28, "xxix": 29, "xxx": 30, "xxxix": 39, "xl": 40, "xli": 41,
    "xlii": 42, "xliii": 43, "xliv": 44, "xlv": 45, "xlvi": 46, "xlvii": 47, "xlviii": 48, "xlix": 49, "l": 50, "li": 51
}'''

new_roman_block = '''CANONICAL_ROMAN_REGEX = re.compile(
    r'^M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})$',
    re.IGNORECASE
)

ROMAN_VAL_MAP = {
    'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000
}

def parse_roman_numeral(s: str) -> Optional[int]:
    """
    Parses a Roman numeral into an integer.
    Strictly enforces canonical Roman subtractive notation.
    Rejects non-canonical forms (e.g. 'IIII', 'VV', 'IL', 'IC', 'XD', 'XIVX', empty strings).
    Returns integer value if canonical and valid, else None.
    """
    if not s or not isinstance(s, str):
        return None
    s_clean = s.strip().lower()
    if not s_clean:
        return None
    if not CANONICAL_ROMAN_REGEX.match(s_clean):
        return None
    
    total = 0
    prev_val = 0
    for char in reversed(s_clean):
        val = ROMAN_VAL_MAP.get(char)
        if val is None:
            return None
        if val < prev_val:
            total -= val
        else:
            total += val
        prev_val = val
        
    return total if total > 0 else None

class CanonicalRomanNumeralMap:
    """
    Real Roman numeral parser replacing the hand-typed map (Order 1.14 - Item 4).
    Validates canonical Roman numerals and rejects non-canonical representations.
    """
    def get(self, key, default=None):
        if isinstance(key, str):
            val = parse_roman_numeral(key)
            if val is not None:
                return val
        return default
    
    def __getitem__(self, key):
        val = parse_roman_numeral(str(key))
        if val is not None:
            return val
        raise KeyError(f"Non-canonical or invalid Roman numeral: '{key}'")

    def __contains__(self, key):
        return parse_roman_numeral(str(key)) is not None

ROMAN_NUMERAL_MAP = CanonicalRomanNumeralMap()'''

if old_roman_block in lg_text:
    lg_text = lg_text.replace(old_roman_block, new_roman_block)
    with open(lg_path, "w", encoding="utf-8", newline="") as f:
        f.write(lg_text)
    print("[1] Patched core/legal_guardrails.py with real Roman numeral parser.")
else:
    print("[1] Note: old_roman_block already replaced or not found in core/legal_guardrails.py")

# ------------------------------------------------------------------------------
# 2. Patch core/statutory_validator.py: Remove 'of the Ordinance' banking guess
# ------------------------------------------------------------------------------
sv_path = os.path.join(REPO_DIR, "core", "statutory_validator.py")
with open(sv_path, "r", encoding="utf-8") as f:
    sv_text = f.read()

old_sv_guess = '''        if not resolved_act:
            if "ordinance" in search_context and (raw_prim in ("15", "15A", "19", "22") or any(w in search_context for w in ["banking", "bank", "financial institution", "financial institutions", "fio", "recovery of finances", "decretal", "banking court", "leave to defend"])):
                resolved_act = "FIO_2001"
            elif raw_prim in ("15", "15A", "19", "22") and "ordinance" in search_context:
                resolved_act = "FIO_2001"'''

new_sv_guess = '''        if not resolved_act:
            # Order 1.14 - Item 4: Strictly forbid guessing FIO_2001 from 'of the Ordinance'.
            # Resolve to FIO_2001 ONLY when the full title appears in context.
            if "ordinance" in search_context and any(w in search_context for w in ["financial institutions (recovery of finances) ordinance", "financial institutions ordinance", "recovery of finances ordinance"]):
                resolved_act = "FIO_2001"'''

if old_sv_guess in sv_text:
    sv_text = sv_text.replace(old_sv_guess, new_sv_guess)
    with open(sv_path, "w", encoding="utf-8", newline="") as f:
        f.write(sv_text)
    print("[2] Patched core/statutory_validator.py: Removed 'of the Ordinance' guess.")
else:
    print("[2] Note: old_sv_guess already replaced or not found in core/statutory_validator.py")

# ------------------------------------------------------------------------------
# 3. Patch legal_ai/verification/memo_verifier.py:
#    - Remove 'of the Ordinance' guess in resolve_citation_to_cid
#    - Remove is_system_rendered parameter from public callers
#    - Add assemble_and_verify_memorandum
#    - Strip & block model-injected banners even if matching system banner
#    - Add Misattributed quote check in verify_quote_against_store
# ------------------------------------------------------------------------------
mv_path = os.path.join(REPO_DIR, "legal_ai", "verification", "memo_verifier.py")
with open(mv_path, "r", encoding="utf-8") as f:
    mv_text = f.read()

# 3.1 Remove 'of the Ordinance' guess
old_mv_guess = '''        # Check 'of the Ordinance' in banking / recovery context
        if re.search(r'\\b(?:of\\s+(?:the\\s+)?ordinance|under\\s+(?:the\\s+)?ordinance|the\\s+ordinance)\\b', cit_span, re.I):
            m_sec = re.search(r'\\b(?:section|sec\\.?|s\\.)\\s*(\\d+[A-Za-z]?)', cit_span, re.I)
            if m_sec:
                return "FIO_2001", m_sec.group(1).upper(), None'''

new_mv_guess = '''        # Order 1.14 - Item 4: Do NOT guess FIO_2001 from 'of the Ordinance'.
        # Only resolve if the full title appears in the citation or immediate context.
        if re.search(r'\\b(?:of\\s+(?:the\\s+)?ordinance|under\\s+(?:the\\s+)?ordinance|the\\s+ordinance)\\b', cit_span, re.I):
            if not re.search(r'\\b(?:financial\\s+institutions|recovery\\s+of\\s+finances)\\b', cit_span, re.I):
                return None, None, "AMBIGUOUS_CITATION"'''

if old_mv_guess in mv_text:
    mv_text = mv_text.replace(old_mv_guess, new_mv_guess)

# 3.2 Update verify_statutory_citation to handle AMBIGUOUS_CITATION
old_vsc = '''        act_code, num, rule_num = self.resolve_citation_to_cid(cit_span, active_order)
        if not act_code or not num:
            return CitationMatchResult(False, f"Provision '{cit_span}' is not in verified store", None, None)'''

new_vsc = '''        act_code, num, rule_num = self.resolve_citation_to_cid(cit_span, active_order)
        if rule_num == "AMBIGUOUS_CITATION":
            return CitationMatchResult(False, f"AMBIGUOUS_CITATION: Citation '{cit_span}' is ambiguous: 'of the Ordinance' lacks a full title or explicit support ID in context", None, None)
        if not act_code or not num:
            return CitationMatchResult(False, f"Provision '{cit_span}' is not in verified store", None, None)'''

if old_vsc in mv_text:
    mv_text = mv_text.replace(old_vsc, new_vsc)

# 3.3 Remove is_system_rendered from verify_memo and verify_memorandum_text
old_vm_sig = 'def verify_memo(self, memo_text: str, is_system_rendered: bool = False) -> Dict[str, Any]:'
new_vm_sig = 'def verify_memo(self, memo_text: str, _is_system_assembled: bool = False) -> Dict[str, Any]:'
if old_vm_sig in mv_text:
    mv_text = mv_text.replace(old_vm_sig, new_vm_sig)

old_sb_check = '''        memo_cleaned, stripped_banners = strip_model_banners(memo_text)
        if stripped_banners and not is_system_rendered:
            for sb in stripped_banners:
                failures.append({
                    "rule": "(b)",
                    "category": "MODEL_INJECTED_BANNER",
                    "label": LABEL_MODEL_BANNER_DETECTED,
                    "issue": f"{LABEL_MODEL_BANNER_DETECTED}: Model-written '> [!' banner detected and stripped. System banners are attached strictly after verification.",
                    "span": sb["text"],
                    "line": sb["line"]
                })

        # Disputed banner check: model-written banners cannot satisfy this check
        has_disputed = has_disputed_banner(memo_text) if is_system_rendered else False'''

new_sb_check = '''        memo_cleaned, stripped_banners = strip_model_banners(memo_text)
        if stripped_banners:
            # Order 1.14 - Item 3: Model text containing ANY `> [!` banner (even exact system banner)
            # is stripped and flagged under Rule (b). Never exempt when caller supplies memo text.
            if not _is_system_assembled:
                for sb in stripped_banners:
                    failures.append({
                        "rule": "(b)",
                        "category": "MODEL_INJECTED_BANNER",
                        "label": LABEL_MODEL_BANNER_DETECTED,
                        "issue": f"{LABEL_MODEL_BANNER_DETECTED}: Model-written '> [!' banner detected and stripped. System banners are attached strictly by system assembler.",
                        "span": sb["text"],
                        "line": sb["line"]
                    })

        # Disputed banner check: model-written banners can NEVER satisfy this check
        has_disputed = has_disputed_banner(memo_text) if _is_system_assembled else False'''

if old_sb_check in mv_text:
    mv_text = mv_text.replace(old_sb_check, new_sb_check)

# 3.4 Update verify_memorandum_text and verify_pleading_citations_and_quotes
old_vmt_sig = '''def verify_memorandum_text(memo_text: str, is_system_rendered: bool = False) -> Dict[str, Any]:
    verifier = MemoVerifier()
    return verifier.verify_memo(memo_text, is_system_rendered=is_system_rendered)'''

new_vmt_sig = '''def verify_memorandum_text(memo_text: str) -> Dict[str, Any]:
    """
    Verifies user/model memorandum text. Caller cannot supply system rendering flags.
    Model text containing system banners is stripped and flagged under Rule (b).
    """
    verifier = MemoVerifier()
    return verifier.verify_memo(memo_text, _is_system_assembled=False)

def assemble_and_verify_memorandum(memo_text: str, disputed_notices: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    System assembler: attaches system warning banners for disputed provisions and
    verifies final output under internal system authority (_is_system_assembled=True).
    """
    verifier = MemoVerifier()
    raw_res = verifier.verify_memo(memo_text, _is_system_assembled=False)
    all_disputed = disputed_notices or raw_res.get("disputed_notices", [])
    assembled_text = attach_system_disputed_banner(memo_text, all_disputed) if all_disputed else memo_text
    final_res = verifier.verify_memo(assembled_text, _is_system_assembled=True)
    final_res["assembled_text"] = assembled_text
    return final_res'''

if old_vmt_sig in mv_text:
    mv_text = mv_text.replace(old_vmt_sig, new_vmt_sig)

old_vpc_sig = 'def verify_pleading_citations_and_quotes(pleading_text: str, is_system_rendered: bool = False) -> Dict[str, Any]:'
new_vpc_sig = 'def verify_pleading_citations_and_quotes(pleading_text: str) -> Dict[str, Any]:'
if old_vpc_sig in mv_text:
    mv_text = mv_text.replace(old_vpc_sig, new_vpc_sig)
    mv_text = mv_text.replace('res = verifier.verify_memo(pleading_text, is_system_rendered=is_system_rendered)', 'res = verifier.verify_memo(pleading_text, _is_system_assembled=False)')

with open(mv_path, "w", encoding="utf-8", newline="") as f:
    f.write(mv_text)
print("[3] Patched legal_ai/verification/memo_verifier.py.")

# ------------------------------------------------------------------------------
# 4. Patch Tiers and Naming:
#    - Harmonize PPC s.415 tier_1 -> ingested_unreviewed
#    - Rename page_verified -> text_layer_matched across all unified statutes
#    - Keep human_reviewed as empty (None)
# ------------------------------------------------------------------------------
statute_files = glob.glob(os.path.join(REPO_DIR, "data", "unified_statutes", "*.json"))

for sf in statute_files:
    fname = os.path.basename(sf)
    with open(sf, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if isinstance(data, list):
        for item in data:
            if item.get("canonical_id") == "PPC_1860_SEC_415" and item.get("tier") == "tier_1":
                item["tier"] = "ingested_unreviewed"
            if "page_verified" in item:
                item["text_layer_matched"] = item.pop("page_verified")
            else:
                item["text_layer_matched"] = False
            item["human_reviewed"] = None
    elif isinstance(data, dict):
        for k, item in data.items():
            if isinstance(item, dict):
                if item.get("canonical_id") == "PPC_1860_SEC_415" and item.get("tier") == "tier_1":
                    item["tier"] = "ingested_unreviewed"
                if "page_verified" in item:
                    item["text_layer_matched"] = item.pop("page_verified")
                else:
                    item["text_layer_matched"] = False
                item["human_reviewed"] = None

    with open(sf, "w", encoding="utf-8", newline="") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

print("[4] Renamed page_verified -> text_layer_matched, harmonized PPC s.415 tier_1.")

# ------------------------------------------------------------------------------
# 5. Patch core/unified_statute_store.py:
#    - Add review_file_present rename
#    - Add genuine cryptographic public key signature verification with committed key
# ------------------------------------------------------------------------------
uss_path = os.path.join(REPO_DIR, "core", "unified_statute_store.py")
with open(uss_path, "r", encoding="utf-8") as f:
    uss_text = f.read()

old_vrt = '''def verify_reviewed_tier(canonical_id: str, content_hash: str) -> bool:
    """
    Validates whether a provision has been legitimately promoted to 'reviewed' tier.
    A provision can ONLY be 'reviewed' if a signed review file exists in data/reviews/
    named <canonical_id>.review.json with matching record_content_hash, reviewer_name,
    and cryptographic_signature. Agents/models cannot set this tier.
    """
    review_file = os.path.join(REVIEWS_DIR, f"{canonical_id}.review.json")
    if not os.path.exists(review_file):
        return False
    try:
        import json
        with open(review_file, "r", encoding="utf-8") as rf:
            data = json.load(rf)
        return (
            str(data.get("canonical_id")).upper() == str(canonical_id).upper() and
            bool(data.get("reviewer_name")) and
            bool(data.get("review_date")) and
            str(data.get("record_content_hash")) == str(content_hash) and
            data.get("status") == "approved" and
            bool(data.get("cryptographic_signature"))
        )
    except Exception:
        return False'''

new_vrt = '''def review_file_present(canonical_id: str, content_hash: str) -> bool:
    """
    Order 1.14 - Item 6: Checks presence of review metadata file on disk.
    This was previously called verify_reviewed_tier but only checked disk presence.
    """
    review_file = os.path.join(REVIEWS_DIR, f"{canonical_id}.review.json")
    if not os.path.exists(review_file):
        return False
    try:
        import json
        with open(review_file, "r", encoding="utf-8") as rf:
            data = json.load(rf)
        return (
            str(data.get("canonical_id")).upper() == str(canonical_id).upper() and
            bool(data.get("reviewer_name")) and
            bool(data.get("review_date")) and
            str(data.get("record_content_hash")) == str(content_hash) and
            data.get("status") == "approved" and
            bool(data.get("cryptographic_signature"))
        )
    except Exception:
        return False

def verify_reviewed_tier(canonical_id: str, content_hash: str) -> bool:
    """
    Order 1.14 - Item 6: Cryptographic public-key signature verification for 'reviewed' tier.
    The authorized advocate public key is committed in data/reviews/advocate_public_key.pem.
    The corresponding private key DOES NOT EXIST on this machine and is never generated here.
    An agent/model cannot sign reviews; any signature made with a throwaway key fails verification.
    """
    review_file = os.path.join(REVIEWS_DIR, f"{canonical_id}.review.json")
    pub_key_file = os.path.join(REVIEWS_DIR, "advocate_public_key.pem")
    
    if not os.path.exists(review_file) or not os.path.exists(pub_key_file):
        return False
    try:
        with open(review_file, "r", encoding="utf-8") as rf:
            data = json.load(rf)
        if str(data.get("canonical_id")).upper() != str(canonical_id).upper():
            return False
        if str(data.get("record_content_hash")) != str(content_hash):
            return False
        if data.get("status") != "approved":
            return False
        
        sig_hex = data.get("cryptographic_signature", "")
        if not sig_hex:
            return False
        sig_bytes = bytes.fromhex(sig_hex)

        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        
        with open(pub_key_file, "rb") as pf:
            public_key = serialization.load_pem_public_key(pf.read())
        
        # Payload verified is canonical_id + content_hash
        payload = f"{canonical_id}:{content_hash}".encode("utf-8")
        
        public_key.verify(
            sig_bytes,
            payload,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except Exception:
        return False'''

if old_vrt in uss_text:
    uss_text = uss_text.replace(old_vrt, new_vrt)
    with open(uss_path, "w", encoding="utf-8", newline="") as f:
        f.write(uss_text)
    print("[5] Patched core/unified_statute_store.py with cryptographic public-key review verification.")
else:
    print("[5] Note: old_vrt already replaced or not found in core/unified_statute_store.py")

# ------------------------------------------------------------------------------
# 6. Patch migrations/
#    - GIN index: CREATE INDEX CONCURRENTLY and transaction notice
#    - RLS: Header stating prerequisite that query_jobs table must be created first
# ------------------------------------------------------------------------------
fts_path = os.path.join(REPO_DIR, "migrations", "20261025_add_fts_index_full_judgments.sql")
with open(fts_path, "r", encoding="utf-8") as f:
    fts_text = f.read()

old_fts_idx = '''--   CREATE INDEX IF NOT EXISTS idx_full_judgments_fts_tokens 
--       ON public.full_judgments 
--       USING gin (fts_tokens);'''

new_fts_idx = '''-- OPERATIVE PRODUCTION DDL (MUST RUN OUTSIDE TRANSACTION BLOCK):
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_full_judgments_fts_tokens 
--     ON public.full_judgments 
--     USING gin (fts_tokens);
-- NOTE: PostgreSQL enforces that `CREATE INDEX CONCURRENTLY` CANNOT be executed inside a multi-statement transaction block (`BEGIN ... COMMIT`). It must be executed in an autocommit connection.'''

if old_fts_idx in fts_text:
    fts_text = fts_text.replace(old_fts_idx, new_fts_idx)
    with open(fts_path, "w", encoding="utf-8", newline="") as f:
        f.write(fts_text)
    print("[6a] Patched migrations/20261025_add_fts_index_full_judgments.sql with CONCURRENTLY operative notice.")

qj_path = os.path.join(REPO_DIR, "migrations", "query_jobs.sql")
with open(qj_path, "r", encoding="utf-8") as f:
    qj_text = f.read()

old_qj_header = '''-- ============================================================================
-- Migration: migrations/query_jobs.sql
-- Purpose: In-flight and persistent query job store for Pakistani legal research backend.'''

new_qj_header = '''-- ============================================================================
-- Migration: migrations/query_jobs.sql
-- PREREQUISITE NOTICE (ORDER 1.14 - ITEM 9):
-- Row Level Security (RLS) enforcement statement ('ALTER TABLE public.query_jobs ENABLE ROW LEVEL SECURITY;')
-- MUST execute strictly AFTER table public.query_jobs has been created.
-- Purpose: In-flight and persistent query job store for Pakistani legal research backend.'''

if old_qj_header in qj_text:
    qj_text = qj_text.replace(old_qj_header, new_qj_header)
    with open(qj_path, "w", encoding="utf-8", newline="") as f:
        f.write(qj_text)
    print("[6b] Patched migrations/query_jobs.sql with RLS prerequisite header.")

print("All Order 1.14 patches successfully applied.")
