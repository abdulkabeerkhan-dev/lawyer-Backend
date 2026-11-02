import os
import sys
from typing import List, Dict, Any
from legal_ai.config import get_supabase_client
from core.structural_judgment_segmenter import StructuralJudgmentSegmenter

sb = get_supabase_client()
if not sb:
    print("Supabase client not initialized")
    sys.exit(1)

# Curated anchor citations
anchor_citations = [
    "2026 SCMR 941", "2006 YLR 2059", "2006 YLR 2289", "1967 PLD 97",
    "2021 SCMR 554", "2001 YLR 2537", "2005 PCRLJ 226", "1996 PCRLJ 207",
    "2019 CLC 1008", "2026 CLD 292", "1995 PLD 34"
]

records: List[Dict[str, Any]] = []
seen_cids = set()

for cit in anchor_citations:
    r = sb.table("full_judgments").select("id, case_id, case_title, neutral_citation, court_name, decision_date, full_text").eq("neutral_citation", cit).limit(1).execute()
    if not r.data:
        cid = cit.replace(" ", "_")
        r = sb.table("full_judgments").select("id, case_id, case_title, neutral_citation, court_name, decision_date, full_text").eq("case_id", cid).limit(1).execute()
    if r.data:
        rec = r.data[0]
        cid = rec["case_id"]
        if cid not in seen_cids:
            seen_cids.add(cid)
            records.append(rec)

# Sample additional cases across reporters: SCMR, CLC, PCRLJ, CLD, PLD, MLD, YLR
reporters = [
    ("SCMR", 10),
    ("CLC", 10),
    ("PCrLJ", 10),
    ("CLD", 5),
    ("MLD", 5),
    ("PLD", 5)
]

for rep, count in reporters:
    r = sb.table("full_judgments").select(
        "id, case_id, case_title, neutral_citation, court_name, decision_date, full_text"
    ).ilike("neutral_citation", f"%{rep}%").limit(count * 3).execute()
    
    added = 0
    for rec in (r.data or []):
        cid = rec["case_id"]
        ft = rec.get("full_text") or ""
        # Only take records with substantial text (> 100 words)
        if cid not in seen_cids and len(ft.split()) >= 100:
            seen_cids.add(cid)
            records.append(rec)
            added += 1
            if added >= count:
                break

print(f"Total pilot cases assembled: {len(records)}")

# Now run each through StructuralJudgmentSegmenter to verify parsing
domain_counts = {}
subdomain_counts = {}
total_pinecone_segments = 0

for rec in records:
    ft = rec.get("full_text") or ""
    res = StructuralJudgmentSegmenter.segment_judgment(ft, metadata=rec)
    dom = res["domain"]
    sub = res["subdomain"]
    domain_counts[dom] = domain_counts.get(dom, 0) + 1
    subdomain_counts[sub] = subdomain_counts.get(sub, 0) + 1
    total_pinecone_segments += len(res["pinecone_segments"])

print("\nDomain Distribution:")
for dom, cnt in sorted(domain_counts.items(), key=lambda x: -x[1]):
    print(f"  {dom}: {cnt}")

print("\nTop Subdomains:")
for sub, cnt in sorted(subdomain_counts.items(), key=lambda x: -x[1])[:10]:
    print(f"  {sub}: {cnt}")

print(f"\nTotal Pinecone vector payloads to generate: {total_pinecone_segments}")
