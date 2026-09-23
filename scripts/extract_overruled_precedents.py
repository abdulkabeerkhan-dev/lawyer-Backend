import os
import re
import sys
import json
import asyncio
from typing import List, Dict, Any, Set
from dotenv import load_dotenv

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Load environment
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(REPO_DIR, ".env"))

from supabase import create_client, Client
from anthropic import AsyncAnthropic

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY (or SUPABASE_KEY) must be set in .env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY must be set in .env")

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
claude = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# Fast-pass regex patterns for doctrinal shifts and explicit overrulings
OVERRULE_PATTERNS = [
    re.compile(r"\[.*?overruled\]", re.IGNORECASE),
    re.compile(r"\b(?:is|are|was|were|stands?|must\s+be|hereby)\s+overruled\b", re.IGNORECASE),
    re.compile(r"\boverruled\s+by\b", re.IGNORECASE),
    re.compile(r"\b(?:we|constrained\s+to)\s+overrule\b", re.IGNORECASE),
    re.compile(r"\bdeclared\s+(?:to\s+be\s+)?(?:bad|no\s+longer)\s+law\b", re.IGNORECASE),
    re.compile(r"\b(?:not|no\s+longer|does\s+not\s+lay\s+down)\s+good\s+law\b", re.IGNORECASE),
    re.compile(r"\bwe\s+dissent\s+from\b", re.IGNORECASE),
]

SYSTEM_PROMPT = (
    "You are an expert Pakistani legal analyst reviewing excerpts from superior court judgments.\n"
    "Your objective is to identify if the excerpt states that a specific prior court decision or precedent "
    "was overruled, held to be bad law, held not to lay down good law, or expressly dissented from.\n\n"
    "If the excerpt DOES state that a specific precedent was overruled or declared bad law, return a strict JSON object:\n"
    "{\n"
    '  "overruled_citation": "<Citation of the overruled case, e.g. PLD 1958 SC 533 or PLD 1971 Kar 273>",\n'
    '  "overruled_case_name": "<Case name of the overruled case, e.g. State v. Dosso>",\n'
    '  "status": "<overruled | criticized_not_followed | distinguished>",\n'
    '  "doctrinal_note": "<Concise 1-2 sentence statement of why it was overruled or declared bad law>"\n'
    "}\n\n"
    "If the excerpt only mentions an overruling in abstract or no specific prior case is overruled, return an empty JSON object: {}."
)

def normalize_citation_to_case_id(citation: str) -> str:
    """Normalize citation like 'PLD 1958 SC 533' to canonical '1958_PLD_SC_533'."""
    if not citation:
        return ""
    cit = re.sub(r'[\(\)\[\],]', ' ', citation).strip()
    match = re.search(r'\b(19\d\d|20\d\d)\s+([A-Za-z]+)(?:\s+([A-Za-z]+))?\s+(\d+)\b', cit)
    if match:
        year, j1, j2, page = match.groups()
        if j2:
            return f"{year}_{j1.upper()}_{j2.upper()}_{page}"
        return f"{year}_{j1.upper()}_{page}"
    return re.sub(r'[^A-Za-z0-9]+', '_', cit).strip('_').upper()

async def extract_overruled_info(text_chunk: str) -> dict:
    """Send candidate excerpt to Claude for high-precision extraction."""
    try:
        response = await claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=400,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Analyze this judgment excerpt:\n\n{text_chunk}"}],
        )
        content = response.content[0].text.strip()
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1:
            data = json.loads(content[start:end+1])
            if data and data.get("overruled_citation"):
                return data
        return {}
    except Exception as e:
        print(f"[Extraction Error] {e}", file=sys.stderr)
        return {}

def extract_matching_excerpts(full_text: str) -> List[str]:
    """Finds paragraphs or surrounding windows matching overruling patterns."""
    if not full_text:
        return []

    paragraphs = re.split(r'\n\s*\n', full_text)
    matched_excerpts = []

    for para in paragraphs:
        para_clean = para.strip()
        if len(para_clean) < 30:
            continue
        for pattern in OVERRULE_PATTERNS:
            if pattern.search(para_clean):
                if len(para_clean) > 2000:
                    m = pattern.search(para_clean)
                    start = max(0, m.start() - 500)
                    end = min(len(para_clean), m.end() + 500)
                    matched_excerpts.append(para_clean[start:end])
                else:
                    matched_excerpts.append(para_clean)
                break

    return matched_excerpts

async def scan_corpus(target_candidates: int = 50, page_step: int = 20):
    """
    Two-pass extraction pipeline:
    1. Query candidate metadata matching 'overruled' in full-text search.
    2. Fetch each judgment's text individually (safe against network timeouts).
    3. Fast regex pass on candidate paragraphs.
    4. Claude Haiku structured extraction.
    5. Save output to data/pending_overruled_review.json.
    """
    print(f"[*] Starting targeted two-pass extraction on Supreme Court judgments...")
    print(f"[*] Target candidates to examine: {target_candidates}")
    print(f"[*] Claude model: {CLAUDE_MODEL}")
    
    output_path = os.path.join(REPO_DIR, "data", "pending_overruled_review.json")
    results = []
    seen_overruled: Set[str] = set()
    total_scanned = 0
    total_regex_hits = 0

    for offset in range(0, target_candidates, page_step):
        fetch_limit = min(page_step, target_candidates - offset)
        print(f"[*] Fetching metadata batch {offset} to {offset + fetch_limit - 1} from Supabase...")
        
        try:
            resp = supabase.table("full_judgments")\
                .select("id, case_id, case_title, neutral_citation, court_name")\
                .filter("full_text", "wfts", "overruled")\
                .eq("court_name", "Supreme Court of Pakistan")\
                .range(offset, offset + fetch_limit - 1)\
                .execute()
            rows = resp.data or []
        except Exception as e:
            print(f"[!] Supabase metadata error at offset {offset}: {e}", file=sys.stderr)
            break

        if not rows:
            print(f"[*] No more candidate rows at offset {offset}.")
            break

        for row in rows:
            total_scanned += 1
            case_id = row.get("case_id")
            # Fetch text for this specific case
            try:
                t_resp = supabase.table("full_judgments")\
                    .select("full_text")\
                    .eq("id", row["id"])\
                    .execute()
                if not t_resp.data:
                    continue
                full_text = t_resp.data[0].get("full_text") or ""
            except Exception as e:
                print(f"[!] Error fetching text for {case_id}: {e}", file=sys.stderr)
                continue

            excerpts = extract_matching_excerpts(full_text)
            if not excerpts:
                continue

            for excerpt in excerpts:
                total_regex_hits += 1
                extracted = await extract_overruled_info(excerpt)
                if not extracted or not extracted.get("overruled_citation"):
                    continue

                cit = extracted.get("overruled_citation", "").strip()
                case_name = extracted.get("overruled_case_name", "").strip()
                norm_case_id = normalize_citation_to_case_id(cit)
                
                dedup_key = f"{norm_case_id}_{extracted.get('status', 'overruled')}"
                if dedup_key in seen_overruled:
                    continue
                seen_overruled.add(dedup_key)

                record = {
                    "case_id": norm_case_id,
                    "citation": cit,
                    "case_name": case_name,
                    "status": extracted.get("status", "overruled"),
                    "superseded_by_case_id": row.get("case_id"),
                    "superseding_citation": row.get("neutral_citation") or row.get("case_id"),
                    "superseding_case_name": row.get("case_title"),
                    "doctrinal_note": extracted.get("doctrinal_note", ""),
                    "source_citation": row.get("neutral_citation") or row.get("case_id"),
                    "raw_excerpt": excerpt[:500] + ("..." if len(excerpt) > 500 else ""),
                    "annotated_by": "claude_regex_pipeline"
                }

                results.append(record)
                print(f"\n[+] DISCOVERED OVERRULED PRECEDENT:")
                print(f"    Overruled Case:  {case_name}")
                print(f"    Citation:        {cit}")
                print(f"    Status:          {record['status']}")
                print(f"    Superseded By:   {record['superseding_case_name']} ({record['superseding_citation']})")
                print(f"    Doctrinal Note:  {record['doctrinal_note']}")

                # Progressively save
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n[DONE] Scan complete.")
    print(f"       - Judgments analyzed: {total_scanned}")
    print(f"       - Regex hits examined: {total_regex_hits}")
    print(f"       - Discovered overruled precedents: {len(results)}")
    print(f"       - Output saved to: {output_path}")

if __name__ == "__main__":
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    asyncio.run(scan_corpus(target_candidates=target, page_step=20))
