"""
scripts/print_order1_1_memos.py

Prints the final prompts, retrieved contexts, and generated legal memoranda
for the 6 Order 1.1 benchmark provisions from data/offline_model_eval_results.json:
  1. FIO Section 22 (Appeal to High Court - DISPUTED RECORD)
  2. PPC Section 489-F (Dishonoured Cheque)
  3. PPC Section 420 (Cheating and Dishonest Inducement)
  4. Cr.P.C. Section 497 (Bail Principles in Non-Bailable Offences)
  5. FIO Section 10 (Leave to Defend in Banking Suits)
  6. CPC Order XXXIX Rule 2A (Ex-Parte Injunction Duration - 15 Days)
"""

import os
import sys
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_RESULTS_PATH = os.path.join(REPO_DIR, "data", "offline_model_eval_results.json")

SYSTEM_PROMPT = """You are a senior Pakistani legal research assistant generating an objective, accurate legal memorandum for an advocate of the High Court.
You MUST adhere strictly to the following rules:
1. Ground your answer strictly in the provided statutory text. If a provision is tagged as DISPUTED, prominently warn the advocate.
2. Quote exact numbers, days, and statutory thresholds without fabrication.
3. Structure your response into: (1) Executive Summary, (2) Statutory Framework, (3) Essential Ingredients & Analysis, (4) Practical Procedural Notes for Counsel."""

def main():
    if not os.path.exists(EVAL_RESULTS_PATH):
        print(f"Error: Eval results file not found at {EVAL_RESULTS_PATH}")
        sys.exit(1)

    with open(EVAL_RESULTS_PATH, "r", encoding="utf-8") as f:
        results = json.load(f)

    print("=" * 110)
    print("ORDER 1.1 ITEM 11: END-TO-END MEMOS & PROMPTS FOR 6 BENCHMARK QUERIES")
    print("Production Pinned Model: claude-haiku-4-5-20251001")
    print("=" * 110)

    for item in results:
        qid = item["query_id"]
        title = item["title"]
        query = item["query"]
        h_model = item["models"].get("claude-haiku-4-5-20251001", {})
        
        print("\n" + "#" * 110)
        print(f"BENCHMARK QUERY #{qid}: {title}")
        print("#" * 110)
        print(f"User Query:\n{query}\n")
        
        print("-" * 110)
        print(f"A. FINAL SYSTEM PROMPT SENT TO MODEL")
        print("-" * 110)
        print(SYSTEM_PROMPT.strip())
        
        print("\n" + "-" * 110)
        print(f"B. FINAL USER PROMPT ENVELOPE & RETRIEVED STATUTORY CONTEXT")
        print("-" * 110)
        # Re-construct user prompt preview
        if qid == 1:
            print("[DISPUTED STATUTE WARNING DISPLAYED TO MODEL & USER]")
            print("The statutory text of Section 22 of the Financial Institutions (Recovery of Finances) Ordinance, 2001")
            print("is tagged as DISPUTED in the statutory store due to divergent gazette layers and unverified amendments.")
            print("Official PDF Source: fio_2001.pdf (Pages 23-24) | Content Hash: 0e44ba269c53c464...")
        
        print(f"\nUser Prompt Body:")
        print(f"Query: {query}")
        print("\nRetrieved Statutory Material (injected verbatim from data/unified_statutes):")
        # Load from disk
        unified_dir = os.path.join(REPO_DIR, "data", "unified_statutes")
        if qid == 1:
            fname, cid = "FIO_2001.json", "FIO_2001_SEC_22"
        elif qid == 2:
            fname, cid = "PPC_1860.json", "PPC_1860_SEC_489F"
        elif qid == 3:
            fname, cid = "PPC_1860.json", "PPC_1860_SEC_420"
        elif qid == 4:
            fname, cid = "CRPC_1898.json", "CRPC_1898_SEC_497"
        elif qid == 5:
            fname, cid = "FIO_2001.json", "FIO_2001_SEC_10"
        elif qid == 6:
            fname, cid = "CPC_1908.json", "CPC_1908_ORD_XXXIX_R_2A"
        
        with open(os.path.join(unified_dir, fname), "r", encoding="utf-8") as f:
            u_data = json.load(f)
        target_rec = next((r for r in u_data if r.get("canonical_id") == cid), {})
        print(f"  [Canonical ID]: {target_rec.get('canonical_id')}")
        print(f"  [Tier]: {target_rec.get('tier')}")
        print(f"  [PDF Page]: {target_rec.get('page_number', 'N/A')}")
        print(f"  [Content Hash]: {target_rec.get('content_hash', 'N/A')}")
        print(f"  [Operative Text Preview]: {target_rec.get('text', '')[:300]}...")

        print("\n" + "-" * 110)
        print(f"C. GENERATED LEGAL MEMORANDUM (claude-haiku-4-5-20251001)")
        print(f"Latency: {h_model.get('latency_sec')}s | Length: {h_model.get('memo_length')} chars | Claim Score: {h_model.get('score')}")
        print("-" * 110)
        print(h_model.get("memo", "[No memo recorded]"))
        
        print("\n" + "-" * 110)
        print(f"D. DETERMINISTIC STATUTORY CLAIM CHECKS")
        print("-" * 110)
        for c in h_model.get("checks", []):
            mark = "PASS" if c["passed"] else "FAIL"
            print(f"  [{mark}] {c['check']}")
        print()

    print("=" * 110)
    print("END-TO-END MEMO AUDIT COMPLETE")
    print("=" * 110)

if __name__ == "__main__":
    main()
