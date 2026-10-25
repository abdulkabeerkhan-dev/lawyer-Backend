import os
import glob

print("=== CHECKING EVIDENCE ARTIFACTS IN data/evidence/ ===")
for root, dirs, files in os.walk("data/evidence"):
    for f in files:
        fpath = os.path.join(root, f)
        print(f"{fpath} ({os.path.getsize(fpath)} bytes)")

print("\n=== CHECKING ANY OTHER OCR ARTIFACTS IN data/ ===")
for root, dirs, files in os.walk("data"):
    for f in files:
        if "ocr" in f.lower() or "page_" in f.lower() or "evidence" in f.lower():
            if not root.startswith("data\\evidence"):
                fpath = os.path.join(root, f)
                print(f"{fpath} ({os.path.getsize(fpath)} bytes)")
