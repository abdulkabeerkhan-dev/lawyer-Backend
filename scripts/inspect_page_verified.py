import json
import glob
import os

print("=== INSPECTING ALL JSON FILES FOR page_verified RECORDS ===")
page_verified_records = []

for root, dirs, files in os.walk("data"):
    for file in files:
        if file.endswith(".json"):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                items = []
                if isinstance(data, list):
                    items = [(i, item) for i, item in enumerate(data) if isinstance(item, dict)]
                elif isinstance(data, dict):
                    for k in ["provisions", "sections", "records", "data"]:
                        if k in data and isinstance(data[k], list):
                            items = [(i, item) for i, item in enumerate(data[k]) if isinstance(item, dict)]
                            break
                    if not items:
                        # Maybe top-level dict is a provision or dict of provisions
                        for k, v in data.items():
                            if isinstance(v, dict):
                                items.append((k, v))

                for idx, item in items:
                    tier = item.get("tier")
                    status = item.get("status")
                    vstatus = item.get("verification_status")
                    if tier == "page_verified" or status == "page_verified" or vstatus == "page_verified":
                        page_verified_records.append({
                            "file": filepath,
                            "index": idx,
                            "canonical_id": item.get("canonical_id", item.get("citation", item.get("section", item.get("title")))),
                            "tier": tier,
                            "status": status,
                            "vstatus": vstatus,
                            "has_source_page": "source_page" in item,
                            "source_page": item.get("source_page"),
                            "has_ocr_text": "ocr_text" in item,
                            "has_page_image_hash": "page_image_hash" in item,
                            "has_text_layer": "text_layer" in item or "raw_text_layer" in item,
                            "has_similarity": "similarity" in item or "ocr_similarity" in item
                        })
            except Exception as e:
                pass

print(f"Total page_verified records found: {len(page_verified_records)}")
for rec in page_verified_records:
    print(f"- File: {rec['file']} | ID: {rec['canonical_id']} | tier: {rec['tier']} | status: {rec['status']} | page: {rec['source_page']} | ocr: {rec['has_ocr_text']} | img_hash: {rec['has_page_image_hash']} | sim: {rec['has_similarity']}")
