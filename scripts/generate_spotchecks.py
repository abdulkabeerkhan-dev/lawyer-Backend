"""
scripts/generate_spotchecks.py

ORDER 2.0 — STEP 6: HUMAN SPOT-CHECK SHEET GENERATOR (OFFLINE)
Picks 25 random records per Act using fixed seed (seed=42).
Writes reports/spotcheck/<ACT>.md with canonical_id, PDF page number, text_raw.
Renders the corresponding PDF pages to PNG into reports/spotcheck/pages/.
Zero model calls.
"""

import os
import sys
import json
import random
from typing import Dict, List, Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pypdfium2 as pdfium

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V2_DIR = os.path.join(REPO_DIR, "data", "statutes_v2")
PDF_DIR = os.path.join(REPO_DIR, "data", "official_pdfs")
SPOTCHECK_DIR = os.path.join(REPO_DIR, "reports", "spotcheck")
PAGES_DIR = os.path.join(SPOTCHECK_DIR, "pages")

os.makedirs(SPOTCHECK_DIR, exist_ok=True)
os.makedirs(PAGES_DIR, exist_ok=True)

FIXED_SEED = 42

ACT_PDF_MAP = {
    "BCO_1962": "banking_companies_ordinance_1962.pdf",
    "CONTRACT_1872": "contract_act_1872.pdf",
    "CPC_1908": "cpc_1908.pdf",
    "CRPC_1898": "crpc_1898.pdf",
    "FIO_2001": "fio_2001.pdf",
    "LIMITATION_1908": "limitation_act_1908.pdf",
    "PPC_1860": "ppc_1860.pdf",
    "REGISTRATION_1908": "registration_act_1908.pdf",
    "STAMP_1899": "stamp_act_1899.pdf",
    "TPA_1882": "transfer_of_property_act_1882.pdf",
}

def generate_spotchecks():
    print(f"Fixed Random Seed: {FIXED_SEED}")
    random.seed(FIXED_SEED)

    summary_table = []
    rendered_pages_set = set()

    for act, pdf_fname in sorted(ACT_PDF_MAP.items()):
        json_path = os.path.join(V2_DIR, f"{act}.json")
        if not os.path.exists(json_path):
            print(f"Skipping {act}: {json_path} does not exist.")
            continue

        with open(json_path, "r", encoding="utf-8") as f:
            records = json.load(f)

        sample_size = min(25, len(records))
        sampled = random.sample(records, sample_size)
        # Sort sampled by page_start
        sampled.sort(key=lambda r: (r.get("page_start", 0), r.get("canonical_id", "")))

        md_path = os.path.join(SPOTCHECK_DIR, f"{act}.md")
        lines = []
        lines.append(f"# Human Spot-Check Sheet: {act}")
        lines.append(f"Source PDF: `data/official_pdfs/{pdf_fname}`")
        lines.append(f"Random Sampling Seed: `{FIXED_SEED}` (Sample size: {sample_size} of {len(records)} provisions)")
        lines.append("")
        lines.append("Compare each extracted `text_raw` against the rendered page image in `pages/`.")
        lines.append("")

        pdf_path = os.path.join(PDF_DIR, pdf_fname)
        pdf = pdfium.PdfDocument(pdf_path)

        for idx, r in enumerate(sampled, 1):
            cid = r.get("canonical_id")
            p_start = r.get("page_start", 1)
            p_end = r.get("page_end", p_start)
            heading = r.get("heading", "")
            tier = r.get("tier", "")
            agreement = r.get("extractor_agreement", "")
            text_raw = r.get("text_raw", "")

            # Render page image if not already rendered
            img_fname = f"{act}_p{p_start}.png"
            img_path = os.path.join(PAGES_DIR, img_fname)
            if (act, p_start) not in rendered_pages_set:
                if 0 <= (p_start - 1) < len(pdf):
                    page = pdf[p_start - 1]
                    # Render at scale 2 for high clarity
                    pil_img = page.render(scale=2).to_pil()
                    pil_img.save(img_path)
                    rendered_pages_set.add((act, p_start))

            lines.append(f"## {idx}. {cid} — {heading}")
            lines.append(f"- **Section:** `{r.get('section')}`")
            lines.append(f"- **PDF Page:** {p_start} (Range: {p_start}–{p_end})")
            lines.append(f"- **Extractor Agreement:** `{agreement}` (Tier: `{tier}`)")
            lines.append(f"- **Rendered Page Image:** `pages/{img_fname}`")
            lines.append("")
            lines.append("```text")
            lines.append(text_raw)
            lines.append("```")
            lines.append("")
            lines.append("---")
            lines.append("")

        pdf.close()

        with open(md_path, "w", encoding="utf-8") as mf:
            mf.write("\n".join(lines))

        print(f"Wrote spot-check sheet for {act}: {md_path} ({sample_size} items)")
        summary_table.append((act, sample_size, len(records), len(rendered_pages_set)))

    print("\nSpot-check sheet generation complete.")
    print(f"Total page images rendered: {len(rendered_pages_set)}")

if __name__ == "__main__":
    generate_spotchecks()
