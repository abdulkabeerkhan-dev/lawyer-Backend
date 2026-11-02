import sys
from legal_ai.config import get_supabase_client

sb = get_supabase_client()
if not sb:
    print("Supabase client not initialized")
    sys.exit(1)

target_citations = [
    "2026 SCMR 941", "2006 YLR 2059", "2006 YLR 2289", "1967 PLD 97",
    "2021 SCMR 554", "2001 YLR 2537", "2005 PCRLJ 226", "1996 PCRLJ 207", "2019 CLC 1008",
    "2026 CLD 292", "1995 PLD 34"
]

print("Checking target benchmark citations in Supabase:")
for cit in target_citations:
    r = sb.table("full_judgments").select("case_id, neutral_citation, case_title, court_name").eq("neutral_citation", cit).execute()
    if r.data:
        rec = r.data[0]
        title = rec.get("case_title", "")[:40]
        print(f"  FOUND: {cit} -> {rec.get('case_id')} | {title}")
    else:
        cid = cit.replace(" ", "_")
        r2 = sb.table("full_judgments").select("case_id, neutral_citation, case_title, court_name").eq("case_id", cid).execute()
        if r2.data:
            rec = r2.data[0]
            title = rec.get("case_title", "")[:40]
            print(f"  FOUND by CID: {cid} -> {rec.get('neutral_citation')} | {title}")
        else:
            print(f"  NOT FOUND: {cit}")
