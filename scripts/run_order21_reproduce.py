"""
scripts/run_order21_reproduce.py

ORDER 2.1 - ITEM 1: Reproduce offline.
Runs the planner, retrieval list builder, and notice builder on the question text
using a recorded fake model response, printing each stage's output:
- Provisions the planner resolved (Act + section)
- Judgments listed
- Notices issued
"""

import os
import sys
import json
import uuid
import asyncio

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from core.legal_query_planner import create_deterministic_fallback_plan
from core.current_law_verifier import verify_current_law_for_provisions
from legal_ai.synthesis.memorandum_generator import filter_and_cap_authorities, sanitize_precedent_card
from main import get_query_job_status, jobs_store


def run_stage_planner(question_text: str):
    print("=" * 60)
    print("STAGE 1: PLANNER OUTPUT (Act + Section Resolution)")
    print("=" * 60)
    plan = create_deterministic_fallback_plan(question_text)
    print(f"Plan Governing Statutes: {plan.governing_statutes}")
    print(f"Plan Provisions: {plan.provisions}")
    print(f"Plan Legal Domain: {plan.legal_domain}")
    print(f"Plan Matter Type: {plan.matter_type}")

    verified_provisions = verify_current_law_for_provisions(plan.provisions, query_text=question_text)
    print(f"\nResolved Statutory Provisions ({len(verified_provisions)} total):")
    for vp in verified_provisions:
        print(f"  - Canonical ID: {vp['canonical_id']}")
        print(f"    Act Code:     {vp['act_code']}")
        print(f"    Display Name: {vp['display_name']}")
        print(f"    Stored Text:  {'PRESENT' if vp.get('text') else 'NO TEXT STORED (Heading only / missing)'}")
    return plan, verified_provisions


def run_stage_retrieval(plan, question_text: str):
    print("\n" + "=" * 60)
    print("STAGE 2: RETRIEVAL LIST BUILDER (Candidate Filtering)")
    print("=" * 60)
    # Recorded raw candidates from live query
    raw_candidates = [
        {
            "citation": "PLD 2025 Quetta 9",
            "case_title": "NAFEESA REHMAN VS The ELECTION TRIBUNAL BALOCHISTAN, QUETTA",
            "court": "High Court of Balochistan",
            "preview": "CITATION: PLD 2025 Quetta 9 TITLE: NAFEESA REHMAN VS The ELECTION TRIBUNAL BALOCHISTAN, QUETTA COURT: Honorable Justice Gul Hassan Tareen Before Muhammad Ejaz Swati and Gul Hassan Tareen JJ Elections Act (XXXIII of 2017) S. 104 Reserved seats for women in Assemblies",
            "holding": "Elections Act matter regarding reserved seats"
        },
        {
            "citation": "2025 PLC(CS) 1528",
            "case_title": "MUHAMMAD HASSAN MUSTAFA (Late) v. OIL AND GAS DEVELOPMENT COMPANY LIMITED (OGDCL)",
            "court": "Islamabad High Court",
            "preview": "CITATION: 2025 PLC(CS) 1528 TITLE: MUHAMMAD HASSAN MUSTAFA (Late) v. OIL AND GAS DEVELOPMENT COMPANY LIMITED COURT: Honorable Justice Muhammad Asif Service appeal under Service Tribunals Act",
            "holding": "Service appeal matter regarding pension and benefits"
        }
    ]

    sanitized = [sanitize_precedent_card(c) for c in raw_candidates]
    filtered = filter_and_cap_authorities(candidates=sanitized, query_plan=plan, query_text=question_text)
    print(f"Raw Candidates Count:      {len(raw_candidates)}")
    print(f"Filtered Candidates Count: {len(filtered)}")
    if filtered:
        print("Judgments Listed:")
        for fc in filtered:
            print(f"  - {fc.get('citation')}: {fc.get('case_title')}")
    else:
        print("Judgments Listed: NONE (Irrelevant election and service tribunal cases successfully excluded)")
    return filtered


def run_stage_notices(verified_provisions, judgments, question_text: str):
    print("\n" + "=" * 60)
    print("STAGE 3: NOTICE BUILDER (Withheld Output & Fallback)")
    print("=" * 60)
    job_id = str(uuid.uuid4())
    verified_statute_fallback = []
    for vp in verified_provisions:
        has_txt = bool(vp.get("text") and str(vp.get("text")).strip())
        verified_statute_fallback.append({
            "canonical_id": vp["canonical_id"],
            "display_name": vp["display_name"],
            "tier": vp.get("tier", "heading_only"),
            "has_text": has_txt,
            "text": vp.get("text") if has_txt else "no text available"
        })

    jobs_store[job_id] = {
        "status": "error",
        "stage": "verification_blocked",
        "error": "MEMORANDUM_VERIFICATION_FAILED",
        "error_category": "UNSOURCED_ANALYSIS",
        "safe_reason": "Direct narrative analysis was withheld to protect strict legal accuracy.",
        "retry_guidance": "Anchor legal assertions directly to verified gazettes or indexed precedents.",
        "unverified_citations": [],
        "query_text": question_text,
        "verified_statute_fallback": verified_statute_fallback,
        "verified_precedents_fallback": judgments,
        "user_id": "test_reproduce_user"
    }

    res = asyncio.run(get_query_job_status(job_id=job_id, authenticated_user_id="test_reproduce_user"))
    answer = res["result"]["answer"]
    print("Rendered Notice Output in UI:")
    print("-" * 50)
    print(answer)
    print("-" * 50)
    print(f"export_allowed: {res['result'].get('export_allowed')}")
    print(f"copy_allowed:   {res['result'].get('copy_allowed')}")
    return res


def main():
    fixture_path = os.path.join(REPO_DIR, "tests", "fixtures", "q_co1_live_output.txt")
    if os.path.exists(fixture_path):
        with open(fixture_path, "r", encoding="utf-8") as f:
            question_text = f.read().strip().split("\n\n")[0].strip()
    else:
        question_text = (
            "A director of a public unlisted company incorporated under the Companies Act, 2017 voted and "
            "participated in a board resolution approving a lucrative commercial contract between the company and a "
            "separate private firm in which the director's adult son held a 60% controlling beneficial interest. "
            "The director failed to disclose his son's material financial interest at the board meeting prior to voting. "
            "Two minority shareholders have challenged the validity of the contract under Section 205 and Section 207 of the Companies Act, 2017, "
            "seeking to void the transaction and hold the director personally liable for corporate losses. "
            "Under Pakistani company law and controlling apex precedents, is a contract entered into in violation of statutory disclosure and "
            "interested-director voting prohibitions automatically void ab initio, or is it merely voidable at the option of the company? "
            "What is the standard of fiduciary liability for an undisclosed interested director?"
        )

    print(f"INPUT QUESTION:\n{question_text}\n")
    plan, verified_provisions = run_stage_planner(question_text)
    judgments = run_stage_retrieval(plan, question_text)
    run_stage_notices(verified_provisions, judgments, question_text)


if __name__ == "__main__":
    main()
