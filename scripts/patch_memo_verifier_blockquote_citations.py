import os

repo_dir = r"I:\c\Users\kabeer\Documents\lawyer-Backend-master\lawyer-Backend-master"
mv_path = os.path.join(repo_dir, "legal_ai", "verification", "memo_verifier.py")

with open(mv_path, "r", encoding="utf-8") as f:
    text = f.read()

target = """        # -------------------------------------------------------------
        # RULE (d): STATUTE CITATION VERIFICATION & DISPUTED POLICY
        # -------------------------------------------------------------
        stat_cits = self.extract_statutory_citations(memo_text)
        statutes_passed = 0
        statutes_failed = 0
        verified_statute_spans = set()

        for sc in stat_cits:"""

replacement = """        # -------------------------------------------------------------
        # RULE (d): STATUTE CITATION VERIFICATION & DISPUTED POLICY
        # -------------------------------------------------------------
        stat_cits = self.extract_statutory_citations(memo_text)
        statutes_passed = 0
        statutes_failed = 0
        verified_statute_spans = set()

        # Collect blockquote text spans so citations embedded inside verbatim quotes are not double-penalized under Rule (d)
        blockquote_spans = []
        for q in quotes:
            raw_q = q.get("raw", "")
            if raw_q:
                s_idx = 0
                while True:
                    found_idx = memo_text.find(raw_q, s_idx)
                    if found_idx == -1:
                        break
                    blockquote_spans.append((found_idx, found_idx + len(raw_q)))
                    s_idx = found_idx + len(raw_q)

        for sc in stat_cits:
            # Skip citations occurring inside verbatim blockquotes (governed by Rule a)
            if any(b_start <= sc["start"] and sc["end"] <= b_end for b_start, b_end in blockquote_spans):
                continue"""

if target in text:
    text = text.replace(target, replacement, 1)
    with open(mv_path, "w", encoding="utf-8") as f:
        f.write(text)
    print("SUCCESS: Patched memo_verifier.py blockquote citation exclusion")
else:
    print("WARNING: target not found")
