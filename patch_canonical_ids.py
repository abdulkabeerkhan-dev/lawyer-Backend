import os
import re
import uuid
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

sb_url = os.getenv("SUPABASE_URL")
sb_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

if not sb_url or not sb_key:
    print("Error: Supabase credentials not found in environment!")
    sys.exit(1)

supabase = create_client(sb_url, sb_key)

def generate_canonical_id(court: str, case_type: str, case_number: str, year: str) -> str:
    norm_court = str(court or "").strip().upper()
    if "SUPREME" in norm_court or "SC" in norm_court:
        c_code = "SC"
    elif "LAHORE" in norm_court or "LHC" in norm_court:
        c_code = "LHC"
    elif "SINDH" in norm_court or "SHC" in norm_court:
        c_code = "SHC"
    elif "PESHAWAR" in norm_court or "PHC" in norm_court:
        c_code = "PHC"
    elif "BALOCHISTAN" in norm_court or "BHC" in norm_court:
        c_code = "BHC"
    else:
        c_code = re.sub(r'[^A-Z0-9]', '', norm_court) or "CT"

    t_code = re.sub(r'[^A-Z0-9]', '', str(case_type or "").upper()) or "GEN"
    num_code = str(case_number or "").strip().replace("/", "-").replace(" ", "")
    num_code = re.sub(r'[^A-Z0-9\-]', '', num_code.upper()) or "0"
    yr_code = str(year or "").strip()

    return f"{c_code}_{t_code}_{num_code}_{yr_code}".strip("_")

JOURNAL_RE = r'(?:PLD|SCMR|PCrLJ|PCRLJ|CLC|MLD|YLR|CLD|PTD|PLC\s*\(CS\)|PLC|PLJ|NLR|GBLR|PTCL|ALD|SLR|ILR|SBLR)'

def extract_reported_citation(text: str) -> str:
    if not text:
        return ""
    m = re.search(r'\b((?:19|20)\d{2}\s+' + JOURNAL_RE + r'\s+\d+|PLD\s+(?:19|20)\d{2}\s+[A-Za-z\s]+\d+)\b', str(text), re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""

def patch_database():
    print("--- Patching Supabase Database Records with canonical_id ---")
    try:
        res = supabase.table("full_judgments").select("*").execute()
        records = res.data or []
        print(f"Retrieved {len(records)} records from full_judgments.")
    except Exception as e:
        print(f"Error selecting full_judgments: {e}")
        return

    updated_count = 0
    seen_canon = set()

    for row in records:
        rec_id = row.get("id") or row.get("case_id")
        court = row.get("court_name") or row.get("court") or "Supreme Court of Pakistan"
        case_id = row.get("case_id") or ""
        citation = row.get("neutral_citation") or ""
        title = row.get("case_title") or ""
        full_text = row.get("full_text") or ""
        decision_date = row.get("decision_date") or ""

        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', decision_date or citation or case_id or title)
        year_str = year_match.group(1) if year_match else "2026"

        # Try parsing docket / case_type / case_number
        docket_match = re.search(r'(Civil\s+Appeal|Civil\s+Petition|Const\s+Petition|Writ\s+Petition|Crl\s+Appeal|Cr\s+P|CP|CA|WP)\s*(?:No\.?)?\s*([\d\-\s\/]+)', case_id + " " + title, re.IGNORECASE)
        if docket_match:
            case_type = docket_match.group(1)
            case_num = docket_match.group(2)
        else:
            case_type = "GEN"
            case_num = case_id or "0"

        canon_id = generate_canonical_id(court, case_type, case_num, year_str)
        reported_cit = extract_reported_citation(citation + " " + title + " " + full_text[:500])

        payload = {
            "canonical_id": canon_id,
        }
        if reported_cit:
            payload["reported_citation"] = reported_cit

        try:
            supabase.table("full_judgments").update(payload).eq("id", rec_id).execute()
            updated_count += 1
        except Exception as ex:
            # Fallback update by case_id
            try:
                supabase.table("full_judgments").update(payload).eq("case_id", case_id).execute()
                updated_count += 1
            except Exception as ex2:
                print(f"Failed to update record {rec_id} / {case_id}: {ex2}")

    print(f"Completed! Updated {updated_count} records with canonical_id.")

if __name__ == "__main__":
    patch_database()
