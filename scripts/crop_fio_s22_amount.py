"""
scripts/crop_fio_s22_amount.py

Renders Page 23 of data/official_pdfs/fio_2001.pdf at high resolution (300 DPI),
locates the exact occurrence of 'such amount' in Section 22(3) proviso,
crops the snippet showing the exact punctuation character,
and saves the image to the artifacts directory.
"""

import os
import sys
import pypdfium2 as pdfium
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_PATH = os.path.join(REPO_DIR, "data", "official_pdfs", "fio_2001.pdf")
ARTIFACT_DIR = r"C:\Users\AKK\.gemini\antigravity\brain\dac42a9b-42b9-4274-b78f-d69c94f06232"

def main():
    print("=" * 100)
    print("GENERATING HIGH-RES CROP AROUND 'such amount' IN FIO S.22(3) PROVISO")
    print("=" * 100)

    pdf = pdfium.PdfDocument(PDF_PATH)
    page = pdf[22] # 0-indexed Page 23
    tp = page.get_textpage()
    text = tp.get_text_range()

    target = "such amount"
    idx = text.find(target)
    if idx == -1:
        print("ERROR: Target 'such amount' not found on Page 23")
        return

    # Extract 30 characters after target
    snippet_len = len(target) + 30
    rects = []
    for c_idx in range(idx - 10, idx + snippet_len):
        try:
            box = tp.get_charbox(c_idx)
            # box is (left, bottom, right, top)
            rects.append(box)
        except Exception as e:
            pass

    min_l = min(b[0] for b in rects)
    max_r = max(b[2] for b in rects)
    min_b = min(b[1] for b in rects)
    max_t = max(b[3] for b in rects)

    pw, ph = page.get_size()
    scale = 300 / 72 # 300 DPI
    pil_image = page.render(scale=scale).to_pil()
    img_w, img_h = pil_image.size

    margin_x = 25
    margin_y = 15
    crop_l = max(0, int((min_l - margin_x) * scale))
    crop_r = min(img_w, int((max_r + margin_x) * scale))
    crop_t = max(0, int((ph - max_t - margin_y) * scale))
    crop_b = min(img_h, int((ph - min_b + margin_y) * scale))

    crop_img = pil_image.crop((crop_l, crop_t, crop_r, crop_b))
    crop_path = os.path.join(ARTIFACT_DIR, "fio_s22_amount_crop.png")
    crop_img.save(crop_path)

    print(f"Crop successfully saved to: {crop_path}")
    print(f"Crop image size: {crop_img.size} (Width x Height)")

    # Print exact characters and unicode codepoints
    raw_slice = text[idx : idx + len(target) + 20]
    print(f"\nRaw text slice: {repr(raw_slice)}")
    for i, c in enumerate(raw_slice):
        print(f"  [{i:2d}] Char: {repr(c):<6} | Unicode: U+{ord(c):04X} | Ord: {ord(c)}")

    print("=" * 100)

if __name__ == "__main__":
    main()
