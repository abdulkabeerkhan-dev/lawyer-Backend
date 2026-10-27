"""
scripts/patch_unified_store_reviewed.py
"""

import os
import re

store_path = "core/unified_statute_store.py"
with open(store_path, "r", encoding="utf-8") as f:
    code = f.read()

target1 = 'VERSIONS_DIR = os.path.join(REPO_DIR, "data", "statute_versions")'
replacement1 = '''VERSIONS_DIR = os.path.join(REPO_DIR, "data", "statute_versions")
REVIEWS_DIR = os.path.join(REPO_DIR, "data", "reviews")

def verify_reviewed_tier(canonical_id: str, content_hash: str) -> bool:
    """
    Validates whether a provision has been legitimately promoted to 'reviewed' tier.
    A provision can ONLY be 'reviewed' if a signed review file exists in data/reviews/
    named <canonical_id>.review.json with matching record_content_hash, reviewer_name,
    and cryptographic_signature. Agents/models cannot set this tier.
    """
    review_file = os.path.join(REVIEWS_DIR, f"{canonical_id}.review.json")
    if not os.path.exists(review_file):
        return False
    try:
        import json
        with open(review_file, "r", encoding="utf-8") as rf:
            data = json.load(rf)
        return (
            str(data.get("canonical_id")).upper() == str(canonical_id).upper() and
            bool(data.get("reviewer_name")) and
            bool(data.get("review_date")) and
            str(data.get("record_content_hash")) == str(content_hash) and
            data.get("status") == "approved" and
            bool(data.get("cryptographic_signature"))
        )
    except Exception:
        return False'''

target2 = '''                        if cid:
                            self._by_cid[cid.upper()] = r'''

replacement2 = '''                        if cid:
                            if r.get("tier") == "reviewed":
                                if not verify_reviewed_tier(cid.upper(), r.get("content_hash", "")):
                                    r["tier"] = "disputed" if r.get("is_disputed") else "ingested_unreviewed"
                                    r["quoting_allowed"] = False
                            self._by_cid[cid.upper()] = r'''

if target1 in code:
    code = code.replace(target1, replacement1)
else:
    print("Warning: target1 not found")

norm_t2 = re.sub(r'\r\n', '\n', target2)
norm_code = re.sub(r'\r\n', '\n', code)
if norm_t2 in norm_code:
    norm_code = norm_code.replace(norm_t2, re.sub(r'\r\n', '\n', replacement2))
    with open(store_path, "w", encoding="utf-8") as f:
        f.write(norm_code)
    print("Successfully patched core/unified_statute_store.py with reviewed tier gating!")
else:
    print("Warning: target2 not found in code")
