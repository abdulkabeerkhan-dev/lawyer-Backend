"""
scripts/patch_memo_verifier_order112.py

Updates legal_ai/verification/memo_verifier.py with:
1. Extract blockquotes with character offsets (start_char, end_char).
2. Nearest named Order resolution for bare 'Rule N'.
3. Allow citations inside verified quotes of stored provisions, labelling them
   'cross-referenced; text not loaded in store'.
"""

import os
import re

REPO_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
fpath = os.path.join(REPO_DIR, "legal_ai", "verification", "memo_verifier.py")

with open(fpath, "r", encoding="utf-8") as f:
    code = f.read()

# 1. Update extract_blockquotes
old_eb = '''    def extract_blockquotes(self, memo_text: str) -> List[Dict[str, Any]]:
        """
        Rule (b): Exempts system banners by structural marker (`> [!`).
        Extracts contiguous non-banner blockquote blocks along with their lead-in sentence.
        """
        lines = memo_text.splitlines()
        quotes = []
        current_block = []
        in_banner = False
        start_line = 0
        lead_in = ""

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(">"):
                if stripped.startswith("> [!"):
                    in_banner = True
                    continue
                if in_banner:
                    continue
                
                content = re.sub(r'^>\\s?', '', stripped)
                if not current_block:
                    start_line = idx + 1
                    # Find lead-in sentence from immediately preceding non-empty line
                    for prev_idx in range(idx - 1, -1, -1):
                        prev_line = lines[prev_idx].strip()
                        if prev_line and not prev_line.startswith("#") and not prev_line.startswith("---"):
                            lead_in = prev_line
                            break
                current_block.append(content)
            else:
                in_banner = False
                if current_block:
                    full_quote = "\\n".join(current_block).strip()
                    if full_quote:
                        quotes.append({"line": start_line, "raw": full_quote, "lead_in": lead_in})
                    current_block = []
                    lead_in = ""

        if current_block and not in_banner:
            full_quote = "\\n".join(current_block).strip()
            if full_quote:
                quotes.append({"line": start_line, "raw": full_quote, "lead_in": lead_in})

        return quotes'''

new_eb = '''    def extract_blockquotes(self, memo_text: str) -> List[Dict[str, Any]]:
        """
        Rule (b): Exempts system banners by structural marker (`> [!`).
        Extracts contiguous non-banner blockquote blocks along with their lead-in sentence and character offsets.
        """
        lines_with_ends = memo_text.splitlines(keepends=True)
        quotes = []
        current_block = []
        in_banner = False
        start_line = 0
        lead_in = ""
        offset = 0
        block_start = 0
        block_end = 0

        for idx, line in enumerate(lines_with_ends):
            line_len = len(line)
            line_start = offset
            line_end = offset + line_len
            offset = line_end

            stripped = line.strip()
            if stripped.startswith(">"):
                if stripped.startswith("> [!"):
                    in_banner = True
                    continue
                if in_banner:
                    continue
                
                content = re.sub(r'^>\\s?', '', stripped)
                if not current_block:
                    start_line = idx + 1
                    block_start = line_start
                    # Find lead-in sentence from immediately preceding non-empty line
                    for prev_idx in range(idx - 1, -1, -1):
                        prev_line = lines_with_ends[prev_idx].strip()
                        if prev_line and not prev_line.startswith("#") and not prev_line.startswith("---"):
                            lead_in = prev_line
                            break
                current_block.append(content)
                block_end = line_end
            else:
                in_banner = False
                if current_block:
                    full_quote = "\\n".join(current_block).strip()
                    if full_quote:
                        quotes.append({
                            "line": start_line,
                            "raw": full_quote,
                            "lead_in": lead_in,
                            "start_char": block_start,
                            "end_char": block_end
                        })
                    current_block = []
                    lead_in = ""

        if current_block and not in_banner:
            full_quote = "\\n".join(current_block).strip()
            if full_quote:
                quotes.append({
                    "line": start_line,
                    "raw": full_quote,
                    "lead_in": lead_in,
                    "start_char": block_start,
                    "end_char": block_end
                })

        return quotes'''

assert old_eb in code, "old_eb not found in code!"
code = code.replace(old_eb, new_eb)

# 2. Update extract_context_order and extract_statutory_citations
old_eco = '''    def extract_context_order(self, text: str) -> Optional[str]:
        """Detects active CPC Order context from headings (e.g. 'Order XXXIX')."""
        m = re.search(r'\\bOrder\\s+([IVXLCDM\\d]+)\\b', text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        return None

    def extract_statutory_citations(self, text: str) -> List[Dict[str, Any]]:
        """Extracts candidate statutory citations according to Order 1.7 - Item 5."""
        active_order = self.extract_context_order(text)
        found = []

        statute_patterns = [
            # 1. Order X Rule Y(z) of CPC / Code of Civil Procedure or standalone
            r'\\b(?:Order|Ord\\.?|o\\.)\\s*([IVXLCDM\\d]+)\\s*(?:Rule|r\\.)\\s*(\\d+[A-Za-z]?)(?:\\s*\\(\\s*(\\d+)\\s*\\))?(?:\\s*(?:of\\s+(?:the\\s+)?(?:CPC|Code of Civil Procedure|Code|1908)))?\\b',
            # 2. Rule Y(z) standalone in Order context
            r'(?<![A-Za-z0-9])(?:Rule|r\\.)\\s*(\\d+[A-Za-z]?)(?:\\s*\\(\\s*(\\d+)\\s*\\))?\\b',
            # 3. Section N(x)(y) of Act / s. N
            r'\\b(?:Section|Sec\\.?|s\\.)\\s*(\\d+[A-Za-z]?(?:\\(\\d+\\))*(?:\\([a-z]\\))*)\\s*(?:,\\s*|\\s+of\\s+(?:the\\s+)?)?([A-Za-z0-9\\s,\\(\\)]+?(?:Act|Ordinance|Code|Order|Rules|CPC|PPC|CrPC|FIO|FIFO|TPA|BCO))\\b',
            # 4. Section multiple: ss. 10 and 22
            r'\\b(?:ss\\.|sections)\\s*(\\d+[A-Za-z]?)\\s+and\\s+(\d+[A-Za-z]?)(?:\\s*(?:of\\s+(?:the\\s+)?)?([A-Za-z0-9\\s,\\(\\)]+?(?:Act|Ordinance|Code|Order|Rules|CPC|PPC|CrPC|FIO|FIFO|TPA|BCO)))?\\b',
            # 5. Article N of Act / Constitution / QSO
            r'\\b(?:Article|Art\\.)\\s*(\\d+[A-Za-z]?)\\s*(?:,\\s*|\\s+of\\s+(?:the\\s+)?)?([A-Za-z0-9\\s,\\(\\)]+?(?:Constitution|QSO|Qanun-e-Shahadat))\\b',
            # 6. Standalone: Section 489-F PPC, Section 22 FIO, Section 10 FIO, Section 61 FIO
            r'\\b(?:Section|Sec\\.?|s\\.)\\s*(\\d+[A-Za-z]?(?:-[A-Za-z]+)?)\\s+(PPC|CPC|CrPC|FIO|FIFO|TPA|BCO)\\b'
        ]

        for pat in statute_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                span = m.group(0).strip()
                found.append({
                    "span": span,
                    "active_order": active_order,
                    "start": m.start(),
                    "end": m.end()
                })

        return found'''

new_eco = '''    def extract_context_order(self, text: str, pos: Optional[int] = None) -> Optional[str]:
        """Detects nearest active CPC Order context from text or nearest preceding a given character position."""
        matches = list(re.finditer(r'\\b(?:Order|Ord\\.?|o\\.)\\s*([IVXLCDM\\d]+)\\b', text, re.IGNORECASE))
        if not matches:
            return None
        if pos is None:
            return matches[0].group(1).upper()
        preceding = [m for m in matches if m.end() <= pos]
        if preceding:
            return preceding[-1].group(1).upper()
        return matches[0].group(1).upper()

    def extract_statutory_citations(self, text: str) -> List[Dict[str, Any]]:
        """Extracts candidate statutory citations according to Order 1.7 - Item 5 and Order 1.12 - Item 2."""
        found = []

        statute_patterns = [
            # 1. Order X Rule Y(z) of CPC / Code of Civil Procedure or standalone
            r'\\b(?:Order|Ord\\.?|o\\.)\\s*([IVXLCDM\\d]+)\\s*(?:Rule|r\\.)\\s*(\\d+[A-Za-z]?)(?:\\s*\\(\\s*(\\d+)\\s*\\))?(?:\\s*(?:of\\s+(?:the\\s+)?(?:CPC|Code of Civil Procedure|Code|1908)))?\\b',
            # 2. Rule Y(z) standalone in Order context
            r'(?<![A-Za-z0-9])(?:Rule|r\\.)\\s*(\\d+[A-Za-z]?)(?:\\s*\\(\\s*(\\d+)\\s*\\))?\\b',
            # 3. Section N(x)(y) of Act / s. N
            r'\\b(?:Section|Sec\\.?|s\\.)\\s*(\\d+[A-Za-z]?(?:\\(\\d+\\))*(?:\\([a-z]\\))*)\\s*(?:,\\s*|\\s+of\\s+(?:the\\s+)?)?([A-Za-z0-9\\s,\\(\\)]+?(?:Act|Ordinance|Code|Order|Rules|CPC|PPC|CrPC|FIO|FIFO|TPA|BCO))\\b',
            # 4. Section multiple: ss. 10 and 22
            r'\\b(?:ss\\.|sections)\\s*(\\d+[A-Za-z]?)\\s+and\\s+(\d+[A-Za-z]?)(?:\\s*(?:of\\s+(?:the\\s+)?)?([A-Za-z0-9\\s,\\(\\)]+?(?:Act|Ordinance|Code|Order|Rules|CPC|PPC|CrPC|FIO|FIFO|TPA|BCO)))?\\b',
            # 5. Article N of Act / Constitution / QSO
            r'\\b(?:Article|Art\\.)\\s*(\\d+[A-Za-z]?)\\s*(?:,\\s*|\\s+of\\s+(?:the\\s+)?)?([A-Za-z0-9\\s,\\(\\)]+?(?:Constitution|QSO|Qanun-e-Shahadat))\\b',
            # 6. Standalone: Section 489-F PPC, Section 22 FIO, Section 10 FIO, Section 61 FIO
            r'\\b(?:Section|Sec\\.?|s\\.)\\s*(\\d+[A-Za-z]?(?:-[A-Za-z]+)?)\\s+(PPC|CPC|CrPC|FIO|FIFO|TPA|BCO)\\b'
        ]

        for pat in statute_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                span = m.group(0).strip()
                active_order = self.extract_context_order(text, m.start())
                found.append({
                    "span": span,
                    "active_order": active_order,
                    "start": m.start(),
                    "end": m.end()
                })

        return found'''

assert old_eco in code, "old_eco not found in code!"
code = code.replace(old_eco, new_eco)

# 3. Update Rule (a) quote match tracking
old_qp = '''                            continue

                quotes_passed += 1
            else:'''

new_qp = '''                            continue

                quotes_passed += 1
                q["matched"] = True
                q["match_cid"] = match_cid
            else:'''

assert old_qp in code, "old_qp not found in code!"
code = code.replace(old_qp, new_qp)

# 4. Update Rule (d) citation verification
old_rule_d = '''        # Collect blockquote text spans so citations embedded inside verbatim quotes are not double-penalized under Rule (d)
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
                continue
            cit_res = self.verify_statutory_citation(sc["span"], sc["active_order"], has_disputed)
            is_valid, reason, rec = cit_res
            cid = cit_res.cid
            tier_val = rec.get("tier", "unknown") if rec else "not_found"
            txt_val = (rec.get("text") or rec.get("statutory_text") or "").strip() if rec else ""
            has_op = bool(rec.get("has_operative_text", True) and tier_val != "title_only" and len(txt_val) > 0 and txt_val != (rec.get("title") or "").strip() and "[heading only]" not in txt_val.lower() and rec.get("verification_status") != "stub") if rec else False
            cited_provisions_meta.append({
                "span": sc["span"],
                "canonical_id": cid,
                "tier": tier_val,
                "has_operative_text": has_op,
                "is_valid": is_valid,
                "reason": reason
            })
            if is_valid:
                statutes_passed += 1
                verified_statute_spans.add(sc["span"])
                if rec and rec.get("tier") == "disputed":
                    disputed_notices.append({
                        "provision": cid or sc["span"],
                        "label": LABEL_DISPUTED_TEXT_NOTICE,
                        "issue": f"Provision '{cid or sc['span']}' is classified as disputed; human check required before reliance."
                    })
            else:
                statutes_failed += 1
                is_disputed_missing_banner = (rec and rec.get("tier") == "disputed" and not has_disputed)
                if is_disputed_missing_banner:
                    disputed_notices.append({
                        "provision": cid or sc["span"],
                        "label": LABEL_DISPUTED_TEXT_NOTICE,
                        "issue": f"Provision '{cid or sc['span']}' is classified as disputed; human check required before reliance."
                    })
                failures.append({
                    "rule": "(d)",
                    "category": "DISPUTED_TEXT_UNNOTICED" if is_disputed_missing_banner else "CITED_PROVISION_NOT_IN_VERIFIED_STORE",
                    "label": LABEL_DISPUTED_TEXT_NOTICE if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE,
                    "issue": f"{LABEL_DISPUTED_TEXT_NOTICE if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE}: {reason}",
                    "span": sc["span"]
                })'''

new_rule_d = '''        # Track verified blockquote spans (Order 1.12 - Item 2)
        verified_quote_spans = []
        for q in quotes:
            if q.get("matched") and "start_char" in q and "end_char" in q:
                verified_quote_spans.append((q["start_char"], q["end_char"]))

        for sc in stat_cits:
            is_inside_verified_quote = any(v_start <= sc["start"] and sc["end"] <= v_end for v_start, v_end in verified_quote_spans)
            cit_res = self.verify_statutory_citation(sc["span"], sc["active_order"], has_disputed)
            is_valid, reason, rec = cit_res
            cid = cit_res.cid
            tier_val = rec.get("tier", "unknown") if rec else "not_found"
            txt_val = (rec.get("text") or rec.get("statutory_text") or "").strip() if rec else ""
            has_op = bool(rec.get("has_operative_text", True) and tier_val != "title_only" and len(txt_val) > 0 and txt_val != (rec.get("title") or "").strip() and "[heading only]" not in txt_val.lower() and rec.get("verification_status") != "stub") if rec else False

            if is_inside_verified_quote:
                # Order 1.12 - Item 2: Citations occurring inside verified quotes of stored provisions
                # are allowed, labelled "cross-referenced; text not loaded in store" if not loaded in store.
                if is_valid:
                    cited_provisions_meta.append({
                        "span": sc["span"],
                        "canonical_id": cid,
                        "tier": tier_val,
                        "has_operative_text": has_op,
                        "is_valid": True,
                        "reason": reason
                    })
                    statutes_passed += 1
                    verified_statute_spans.add(sc["span"])
                else:
                    cited_provisions_meta.append({
                        "span": sc["span"],
                        "canonical_id": cid,
                        "tier": "cross_referenced",
                        "has_operative_text": False,
                        "is_valid": True,
                        "cross_referenced": True,
                        "label": "cross-referenced; text not loaded in store",
                        "reason": "cross-referenced; text not loaded in store"
                    })
                    statutes_passed += 1
                    verified_statute_spans.add(sc["span"])
                continue

            # Outside verified quotes: standard verification
            cited_provisions_meta.append({
                "span": sc["span"],
                "canonical_id": cid,
                "tier": tier_val,
                "has_operative_text": has_op,
                "is_valid": is_valid,
                "reason": reason
            })
            if is_valid:
                statutes_passed += 1
                verified_statute_spans.add(sc["span"])
                if rec and rec.get("tier") == "disputed":
                    disputed_notices.append({
                        "provision": cid or sc["span"],
                        "label": LABEL_DISPUTED_TEXT_NOTICE,
                        "issue": f"Provision '{cid or sc['span']}' is classified as disputed; human check required before reliance."
                    })
            else:
                statutes_failed += 1
                is_disputed_missing_banner = (rec and rec.get("tier") == "disputed" and not has_disputed)
                if is_disputed_missing_banner:
                    disputed_notices.append({
                        "provision": cid or sc["span"],
                        "label": LABEL_DISPUTED_TEXT_NOTICE,
                        "issue": f"Provision '{cid or sc['span']}' is classified as disputed; human check required before reliance."
                    })
                failures.append({
                    "rule": "(d)",
                    "category": "DISPUTED_TEXT_UNNOTICED" if is_disputed_missing_banner else "CITED_PROVISION_NOT_IN_VERIFIED_STORE",
                    "label": LABEL_DISPUTED_TEXT_NOTICE if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE,
                    "issue": f"{LABEL_DISPUTED_TEXT_NOTICE if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE}: {reason}",
                    "span": sc["span"]
                })'''

assert old_rule_d in code, "old_rule_d not found in code!"
code = code.replace(old_rule_d, new_rule_d)

with open(fpath, "w", encoding="utf-8") as f:
    f.write(code)

print("Successfully patched legal_ai/verification/memo_verifier.py for Order 1.12 - Item 2!")
