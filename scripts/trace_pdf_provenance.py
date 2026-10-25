"""
scripts/trace_pdf_provenance.py

Traces how each PDF in data/official_pdfs/ arrived:
  - File system metadata (size, creation time, modification time)
  - Content SHA-256 hash
  - Transcript origin / download commands
"""

import os
import sys
import json
import hashlib
import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(REPO_DIR, "data", "official_pdfs")
TRANSCRIPT_PATH = r"C:\Users\AKK\.gemini\antigravity\brain\dac42a9b-42b9-4274-b78f-d69c94f06232\.system_generated\logs\transcript.jsonl"

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def main():
    print("=" * 110)
    print("ITEM 1: PROVENANCE AND ARRIVAL OF OFFICIAL STATUTE PDFS IN data/official_pdfs/")
    print("=" * 110)

    pdf_files = sorted(os.listdir(PDF_DIR))
    print(f"{'Filename':<35} | {'Bytes':<10} | {'Created':<22} | {'Last Modified':<22} | {'SHA256'[:20]}")
    print("-" * 110)

    for pf in pdf_files:
        if not pf.endswith(".pdf"):
            continue
        p = os.path.join(PDF_DIR, pf)
        sz = os.path.getsize(p)
        ctime = datetime.datetime.fromtimestamp(os.path.getctime(p)).strftime("%Y-%m-%d %H:%M:%S")
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M:%S")
        sha = sha256_file(p)
        print(f"{pf:<35} | {sz:<10} | {ctime:<22} | {mtime:<22} | {sha[:16]}...")

    print("\n" + "-" * 110)
    print("TRANSCRIPT AUDIT: EXACT DOWNLOAD / ACQUISITION COMMANDS")
    print("-" * 110)
    
    if os.path.exists(TRANSCRIPT_PATH):
        with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f):
                try:
                    step = json.loads(line)
                except Exception:
                    continue
                content_str = json.dumps(step)
                if any(k in content_str for k in ["download_real_bco", "find_and_download_statutes", "fetch_official_pdf_urls", "pakistancode.gov.pk/pdffiles"]):
                    step_idx = step.get("step_index", line_idx)
                    created_at = step.get("created_at", "N/A")
                    tool_calls = step.get("tool_calls", [])
                    for tc in tool_calls:
                        c_line = tc.get("CommandLine") or tc.get("CommandLine", "")
                        summary = tc.get("toolSummary", "")
                        if any(k in str(c_line) for k in ["download", "fetch", "official_pdfs"]):
                            print(f"[Step {step_idx} | {created_at}] {summary}")
                            print(f"  Command: {c_line}\n")
    print("=" * 110)

if __name__ == "__main__":
    main()
