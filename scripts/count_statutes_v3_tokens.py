import os
import sys
import json
import re
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(r"d:\lawyer-Backend")
load_dotenv(ROOT_DIR / ".env")

import voyageai

V3_STAGING_DIR = ROOT_DIR / "data" / "statutes_v3_staging"
REPORTS_DIR = ROOT_DIR / "reports"

def run_token_counting():
    print("=" * 70)
    print("COUNTING EXACT TOKENS FOR VOYAGE-4-LARGE EMBEDDING")
    print("=" * 70)

    api_key = os.environ.get("VOYAGE_API_KEY")
    vo = voyageai.Client(api_key=api_key)

    total_records = 0
    active_records = 0
    repealed_records = 0
    legacy_records = 0
    pc_active_records = 0

    all_texts_to_embed = []
    record_metadata = []

    for fpath in sorted(list(V3_STAGING_DIR.glob("*.json"))):
        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                recs = json.load(fp)
                if not isinstance(recs, list):
                    continue
                for r in recs:
                    total_records += 1
                    if not r.get("in_force", True) or r.get("provision_type") == "repeal_notice":
                        repealed_records += 1
                        continue

                    active_records += 1
                    src = r.get("source", "")
                    if src == "statutes_v2_legacy":
                        legacy_records += 1
                    else:
                        pc_active_records += 1

                    # Construct embedded text: title, section, heading inside embedded text
                    act_name = r.get("act_name", "")
                    sec = r.get("section", "")
                    hdg = r.get("heading", "")
                    txt = r.get("text", "")

                    embed_text = f"{act_name}\nSection {sec}: {hdg}\n\n{txt}".strip()
                    # Ensure willful normalization
                    embed_text = re.sub(r'\bwilful\b', 'willful', embed_text, flags=re.I)

                    all_texts_to_embed.append(embed_text)
                    record_metadata.append({
                        "canonical_id": r.get("canonical_id"),
                        "act_code": r.get("act_code"),
                        "section": sec,
                        "source": src
                    })
        except Exception as e:
            print(f"Error reading {fpath.name}: {e}")

    print(f"\nCorpus Inventory Summary:")
    print(f"  Total Staged Provisions   : {total_records:,}")
    print(f"  Repealed Provisions (Out) : {repealed_records:,}")
    print(f"  Total Active Provisions   : {active_records:,}")
    print(f"    - Pakistan Code Active  : {pc_active_records:,}")
    print(f"    - Statutes v2 Legacy    : {legacy_records:,}")

    print(f"\nTokenizing {len(all_texts_to_embed):,} active provisions with Voyage tokenizer...")

    batch_size = 1000
    total_tokens = 0
    for i in range(0, len(all_texts_to_embed), batch_size):
        batch = all_texts_to_embed[i:i+batch_size]
        cnt = vo.count_tokens(batch, model="voyage-4-large")
        total_tokens += cnt
        if (i // batch_size) % 5 == 0 or i + batch_size >= len(all_texts_to_embed):
            print(f"  Batch {i//batch_size + 1}/{(len(all_texts_to_embed)-1)//batch_size + 1} processed: {total_tokens:,} tokens cumulative")

    # Pricing: Voyage-4-Large is $0.12 per 1,000,000 tokens ($0.00012 per 1k)
    cost_per_million = 0.12
    estimated_cost = (total_tokens / 1_000_000.0) * cost_per_million

    print("\n" + "=" * 70)
    print("VOYAGE-4-LARGE TOKEN & COST REPORT")
    print("=" * 70)
    print(f"Model                  : voyage-4-large (1024-d, input_type='document')")
    print(f"Total Active Provisions: {active_records:,}")
    print(f"Total Exact Tokens     : {total_tokens:,}")
    print(f"Average Tokens/Record  : {total_tokens / active_records:.1f}")
    print(f"Rate                   : ${cost_per_million:.2f} per 1M tokens")
    print(f"Estimated Voyage Cost  : ${estimated_cost:.4f} USD")
    print("=" * 70)

    # Save to report file
    report = {
        "model": "voyage-4-large",
        "dimension": 1024,
        "total_provisions": total_records,
        "repealed_provisions_excluded": repealed_records,
        "active_provisions_to_embed": active_records,
        "pakistan_code_provisions": pc_active_records,
        "legacy_v2_provisions": legacy_records,
        "total_exact_tokens": total_tokens,
        "avg_tokens_per_record": round(total_tokens / active_records, 1),
        "rate_per_million_usd": cost_per_million,
        "estimated_voyage_cost_usd": round(estimated_cost, 4)
    }

    report_path = REPORTS_DIR / "voyage_embedding_cost_report.json"
    with open(report_path, "w", encoding="utf-8") as fp:
        json.dump(report, fp, indent=2)

    print(f"\nSaved cost report to {report_path}")

if __name__ == "__main__":
    run_token_counting()
