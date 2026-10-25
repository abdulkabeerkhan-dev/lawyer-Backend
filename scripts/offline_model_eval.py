"""
scripts/offline_model_eval.py

Deterministic Offline Model Evaluation for Order 1.1 Item 8:
Runs the 6 benchmark test queries through:
  - Model A: claude-haiku-4-5-20251001 (Production Pinned)
  - Model B: claude-sonnet-5-5 (Claude Sonnet 5.5)

Evaluates:
  1. FIO Section 22 (Appeal to High Court - Disputed Provision)
  2. PPC Section 489-F (Dishonestly Issuing Cheque)
  3. PPC Section 420 (Cheating and Dishonestly Inducing Delivery)
  4. Cr.P.C. Section 497 (Bail in Non-Bailable Offences)
  5. FIO Section 10 (Leave to Defend in Banking Suits)
  6. CPC Order XXXIX Rule 2A (Ex-Parte Interim Injunction Duration)

Performs deterministic claim checks against retrieved statutory ground truth.
Saves outputs to data/offline_model_eval_results.json.
"""

import os
import sys
import json
import time
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(REPO_DIR, ".env"))

from anthropic import Anthropic

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MODELS = [
    {"id": "claude-haiku-4-5-20251001", "name": "Haiku 4.5 (Prod Pinned)"},
    {"id": "claude-sonnet-5-5", "name": "Sonnet 5.5"}
]

# Load retrieved provisions from unified statute files
UNIFIED_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")

def get_provision(fname, cid):
    with open(os.path.join(UNIFIED_DIR, fname), "r", encoding="utf-8") as f:
        data = json.load(f)
    for r in data:
        if r.get("canonical_id") == cid or cid.lower() in str(r.get("canonical_id", "")).lower():
            return r
    return {}

fio_s22 = get_provision("FIO_2001.json", "FIO_2001_SEC_22")
fio_s10 = get_provision("FIO_2001.json", "FIO_2001_SEC_10")
ppc_489f = get_provision("PPC_1860.json", "PPC_1860_SEC_489F")
ppc_420 = get_provision("PPC_1860.json", "PPC_1860_SEC_420")
ppc_415 = get_provision("PPC_1860.json", "PPC_1860_SEC_415")
crpc_497 = get_provision("CRPC_1898.json", "CRPC_1898_SEC_497")
cpc_o39_r2a = get_provision("CPC_1908.json", "CPC_1908_ORD_XXXIX_R_2A")
cpc_o39_r1 = get_provision("CPC_1908.json", "CPC_1908_ORD_XXXIX_R_1")
cpc_o39_r2 = get_provision("CPC_1908.json", "CPC_1908_ORD_XXXIX_R_2")

# Format disputed warning banner for FIO s.22
fio_s22_context = f"""[DISPUTED STATUTE WARNING]
The text of Section 22 of the Financial Institutions (Recovery of Finances) Ordinance, 2001 is currently tagged as DISPUTED in the statutory store due to divergent gazette layers and unverified amendments. Any reliance on specific sub-sections must be hedged with explicit notice to the advocate.
Official PDF Source: fio_2001.pdf (Pages 23-24)
Content Hash: {fio_s22.get('content_hash', 'N/A')}
Operative Text Layer:
{fio_s22.get('text', '')}"""

TEST_QUERIES = [
    {
        "id": 1,
        "title": "FIO Section 22 Appeal & Stay Requirements",
        "query": "What is the statutory procedure and limitation period for filing an appeal to the High Court under Section 22 of the Financial Institutions (Recovery of Finances) Ordinance, 2001, and what are the legal requirements for grant of stay of execution?",
        "statute_context": fio_s22_context,
        "claim_checks": [
            ("Mentions 30 days limitation", lambda m: "30" in m or "thirty" in m.lower()),
            ("Mentions High Court / Division Bench", lambda m: "high court" in m.lower()),
            ("Acknowledges disputed status or stay conditions", lambda m: "dispute" in m.lower() or "stay" in m.lower() or "deposit" in m.lower())
        ]
    },
    {
        "id": 2,
        "title": "PPC Section 489-F Dishonoured Cheque",
        "query": "What are the essential statutory ingredients to establish an offence under Section 489-F of the Pakistan Penal Code, 1860, and what punishment does it carry?",
        "statute_context": f"Statute: Pakistan Penal Code, 1860\nSection 489-F:\n{ppc_489f.get('text', '')}",
        "claim_checks": [
            ("Mentions dishonestly issuing cheque", lambda m: "dishonest" in m.lower() and "cheque" in m.lower()),
            ("Mentions repayment of loan or fulfilment of obligation", lambda m: "repayment" in m.lower() or "obligation" in m.lower() or "loan" in m.lower()),
            ("Mentions punishment up to 3 years or fine", lambda m: "3" in m or "three" in m.lower())
        ]
    },
    {
        "id": 3,
        "title": "PPC Section 420 Cheating & Dishonest Inducement",
        "query": "What are the essential ingredients of cheating under Section 415 and 420 PPC, and how does superior court jurisprudence distinguish between mere civil breach of contract and criminal cheating?",
        "statute_context": f"PPC Section 415:\n{ppc_415.get('text', '')}\n\nPPC Section 420:\n{ppc_420.get('text', '')}",
        "claim_checks": [
            ("Mentions fraudulent/dishonest inducement at inception", lambda m: "induce" in m.lower() or "inception" in m.lower() or "dishonest" in m.lower()),
            ("Distinguishes civil contract breach from criminal offence", lambda m: "civil" in m.lower() or "breach" in m.lower() or "contract" in m.lower()),
            ("Mentions delivery of property", lambda m: "property" in m.lower())
        ]
    },
    {
        "id": 4,
        "title": "Cr.P.C. Section 497 Bail Principles",
        "query": "Under what statutory circumstances may bail be granted or refused in non-bailable offences under Section 497 of the Code of Criminal Procedure, 1898, and what is the rule of further inquiry?",
        "statute_context": f"Cr.P.C. Section 497:\n{crpc_497.get('text', '')}",
        "claim_checks": [
            ("Mentions non-bailable offences", lambda m: "non-bailable" in m.lower() or "bailable" in m.lower()),
            ("Mentions prohibitory clause (death/life/10 years)", lambda m: "prohibitory" in m.lower() or "death" in m.lower() or "life" in m.lower() or "10" in m or "ten" in m.lower()),
            ("Mentions further inquiry under subsection (2)", lambda m: "further inquiry" in m.lower() or "497(2)" in m or "sub-section (2)" in m.lower())
        ]
    },
    {
        "id": 5,
        "title": "FIO Section 10 Leave to Defend",
        "query": "What is the procedure and mandatory timeline for filing an application for leave to defend in a banking suit under Section 10 of the Financial Institutions (Recovery of Finances) Ordinance, 2001?",
        "statute_context": f"FIO 2001 Section 10:\n{fio_s10.get('text', '')}",
        "claim_checks": [
            ("Mentions 30 days limitation for leave application", lambda m: "30" in m or "thirty" in m.lower()),
            ("Mentions summary procedure / banking court", lambda m: "banking court" in m.lower() or "leave to defend" in m.lower()),
            ("Mentions consequences of failure to obtain leave (deemed decree)", lambda m: "decree" in m.lower() or "admit" in m.lower() or "defense" in m.lower() or "defence" in m.lower())
        ]
    },
    {
        "id": 6,
        "title": "CPC Order XXXIX Rule 2A Ex-Parte Injunction Duration",
        "query": "What is the statutory duration of an interim injunction passed under Order XXXIX Rules 1 or 2 CPC in the absence of the defendant under Order XXXIX Rule 2A CPC?",
        "statute_context": f"CPC Order XXXIX Rule 1:\n{cpc_o39_r1.get('text', '')}\n\nCPC Order XXXIX Rule 2:\n{cpc_o39_r2.get('text', '')}\n\nCPC Order XXXIX Rule 2A:\n{cpc_o39_r2a.get('text', '')}",
        "claim_checks": [
            ("Mentions 15 days duration for ex-parte injunction", lambda m: "15" in m or "fifteen" in m.lower()),
            ("Mentions Order XXXIX Rule 2A", lambda m: "2a" in m.lower() or "rule 2a" in m.lower()),
            ("Mentions conditions for extension (failure of service / defence time)", lambda m: "service" in m.lower() or "extend" in m.lower() or "defence" in m.lower() or "defense" in m.lower())
        ]
    }
]

SYSTEM_PROMPT = """You are a senior Pakistani legal research assistant generating an objective, accurate legal memorandum for an advocate of the High Court.
You MUST adhere strictly to the following rules:
1. Ground your answer strictly in the provided statutory text. If a provision is tagged as DISPUTED, prominently warn the advocate.
2. Quote exact numbers, days, and statutory thresholds without fabrication.
3. Structure your response into: (1) Executive Summary, (2) Statutory Framework, (3) Essential Ingredients & Analysis, (4) Practical Procedural Notes for Counsel."""

def run_evaluation():
    print("=" * 110)
    print("ORDER 1.1 ITEM 8: OFFLINE MODEL EVALUATION ON 6 BENCHMARK QUERIES")
    print("=" * 110)
    
    all_results = []
    
    for tq in TEST_QUERIES:
        print(f"\n{'='*50}\nQUERY #{tq['id']}: {tq['title']}\n{'='*50}")
        user_prompt = f"Query: {tq['query']}\n\nRetrieved Statutory Material:\n{tq['statute_context']}\n\nPlease generate the legal memorandum."
        
        q_record = {
            "query_id": tq["id"],
            "title": tq["title"],
            "query": tq["query"],
            "models": {}
        }
        
        for m in MODELS:
            m_id = m["id"]
            m_name = m["name"]
            print(f"\nEvaluating Model: {m_name} ({m_id})...")
            t0 = time.time()
            try:
                resp = client.messages.create(
                    model=m_id,
                    max_tokens=1500,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}]
                )
                dt = time.time() - t0
                memo_parts = []
                for b in resp.content:
                    if getattr(b, "type", "") == "text":
                        memo_parts.append(getattr(b, "text", ""))
                    elif hasattr(b, "text"):
                        memo_parts.append(b.text)
                memo_text = "\n".join(memo_parts).strip()
                
                # Run deterministic claim checks
                checks_passed = 0
                check_details = []
                for c_name, c_fn in tq["claim_checks"]:
                    passed = c_fn(memo_text)
                    if passed: checks_passed += 1
                    check_details.append({"check": c_name, "passed": passed})
                
                score_str = f"{checks_passed}/{len(tq['claim_checks'])}"
                print(f"  Generated memo: {len(memo_text)} chars in {dt:.2f}s | Claim Score: {score_str}")
                for cd in check_details:
                    status_mark = "PASS" if cd["passed"] else "FAIL"
                    print(f"    [{status_mark}] {cd['check']}")
                
                q_record["models"][m_id] = {
                    "model_id": m_id,
                    "model_name": m_name,
                    "latency_sec": round(dt, 2),
                    "memo_length": len(memo_text),
                    "score": score_str,
                    "checks": check_details,
                    "memo": memo_text
                }
            except Exception as e:
                print(f"  Error invoking {m_id}: {e}")
                q_record["models"][m_id] = {"error": str(e)}
        
        all_results.append(q_record)

    # Save results
    out_file = os.path.join(REPO_DIR, "data", "offline_model_eval_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n\nEvaluation Complete! Results saved to {out_file}")

    # Summary Table
    print("\n" + "=" * 110)
    print("OFFLINE MODEL EVALUATION SUMMARY TABLE")
    print("=" * 110)
    print(f"{'Q#':<4} | {'Query Title':<45} | {'Haiku 4.5 Score':<18} | {'Sonnet 5.5 Score':<18} | {'Haiku Sec':<10} | {'Sonnet Sec'}")
    print("-" * 110)
    for res in all_results:
        qid = res["query_id"]
        qtitle = res["title"][:43]
        h_score = res["models"].get("claude-haiku-4-5-20251001", {}).get("score", "ERR")
        s_score = res["models"].get("claude-sonnet-5-5", {}).get("score", "ERR")
        h_lat = str(res["models"].get("claude-haiku-4-5-20251001", {}).get("latency_sec", "N/A"))
        s_lat = str(res["models"].get("claude-sonnet-5-5", {}).get("latency_sec", "N/A"))
        print(f"{qid:<4} | {qtitle:<45} | {h_score:<18} | {s_score:<18} | {h_lat:<10} | {s_lat}")
    print("=" * 110)

if __name__ == "__main__":
    run_evaluation()
