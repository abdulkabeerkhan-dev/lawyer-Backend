import os
import re

file_path = "legal_ai/verification/memo_verifier.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add LABEL_DECEPTIVE_TRUNCATION and EXCEPTION_CLAUSE_TERMS
old_labels = '''LABEL_DECEPTIVE_ELLIPSIS = "DECEPTIVE ELLIPSIS — omitted material condition"
LABEL_MODEL_BANNER_DETECTED = "MODEL-INJECTED BANNER STRIPPED"

BLOCKING_CONDITION_TERMS = [
    "shall not", "unless", "except", "provided that", "subject to", "notwithstanding", "if"
]
CONDITION_TERMS = BLOCKING_CONDITION_TERMS'''

new_labels = '''LABEL_DECEPTIVE_ELLIPSIS = "DECEPTIVE ELLIPSIS — omitted material condition"
LABEL_DECEPTIVE_TRUNCATION = "DECEPTIVE TRUNCATION — omitted material exception/condition"
LABEL_MODEL_BANNER_DETECTED = "MODEL-INJECTED BANNER STRIPPED"

BLOCKING_CONDITION_TERMS = [
    "shall not", "unless", "except", "provided that", "subject to", "notwithstanding", "if"
]
EXCEPTION_CLAUSE_TERMS = [
    "unless", "provided that", "provided", "except", "save", "subject to", "notwithstanding", "but"
]
CONDITION_TERMS = BLOCKING_CONDITION_TERMS'''

assert old_labels in content.replace("\r\n", "\n"), "old_labels not found"
content = content.replace("\r\n", "\n").replace(old_labels, new_labels)

# 2. Continuous quote stream matching: add truncation check
old_stream_match = '''        for prov in self.provisions:
            if not prov["matching_stream"]:
                continue
            if q_stream in prov["matching_stream"]:
                return QuoteMatchResult(True, prov["canonical_id"], None, None)'''

new_stream_match = '''        for prov in self.provisions:
            if not prov["matching_stream"]:
                continue
            if q_stream in prov["matching_stream"]:
                # Order 1.10 - Item 7: Truncation check
                # If quote ends before sentence end and stored text continues with
                # unless / provided that / except / save / subject to / notwithstanding / but,
                # return BLOCK and show dropped text.
                norm_q = shared_normalize(raw_quote)
                p_norm = prov.get("normalized_text", "")
                idx_norm = p_norm.lower().find(norm_q.lower())
                if idx_norm != -1:
                    q_end = idx_norm + len(norm_q)
                    rest = p_norm[q_end:]
                    # Next sentence boundary (. ; : ? or newline)
                    b_match = re.search(r'[\\.\\;\\:\\?\\n]', rest)
                    clause = rest[:b_match.start()].strip() if b_match else rest.strip()
                    clause_lower = clause.lower().lstrip(" ,;:-—")
                    matched_exc = None
                    for exc in EXCEPTION_CLAUSE_TERMS:
                        if re.match(rf'\\b{re.escape(exc)}\\b', clause_lower):
                            matched_exc = exc
                            break
                    if matched_exc:
                        diff_desc = f"{LABEL_DECEPTIVE_TRUNCATION}: quote matches '{prov['canonical_id']}' but terminates before sentence end, omitting qualifying condition '{matched_exc}'. Dropped text: '{clause}'"
                        return QuoteMatchResult(False, prov["canonical_id"], diff_desc, [clause], raw_quote, [matched_exc])

                return QuoteMatchResult(True, prov["canonical_id"], None, None)'''

assert old_stream_match in content, "old_stream_match not found"
content = content.replace(old_stream_match, new_stream_match)

# 3. Disputed citation reason in verify_statutory_citation
old_disputed_cit = '''        # Disputed tier policy (Order 1.7 - Item 7)
        if tier == "disputed":
            if has_disputed:
                # Allowed with notice
                return CitationMatchResult(True, None, rec, cid)
            else:
                return CitationMatchResult(False, f"Provision '{cit_span}' is classified as disputed and cannot be cited without the required structural warning banner", rec, cid)'''

new_disputed_cit = '''        # Disputed tier policy (Order 1.7 - Item 7, Order 1.10 - Item 9)
        if tier == "disputed":
            if has_disputed:
                # Allowed with notice
                return CitationMatchResult(True, None, rec, cid)
            else:
                reason = f"{LABEL_DISPUTED_TEXT_NOTICE}: Provision '{cit_span}' is classified as disputed; human check required before reliance (missing structural warning banner)"
                return CitationMatchResult(False, reason, rec, cid)'''

assert old_disputed_cit in content, "old_disputed_cit not found"
content = content.replace(old_disputed_cit, new_disputed_cit)

# 4. In verify_memo: when is_disputed_missing_banner, use LABEL_DISPUTED_TEXT_NOTICE
old_memo_fail = '''                is_disputed_missing_banner = (rec and rec.get("tier") == "disputed" and not has_disputed)
                failures.append({
                    "rule": "(d)",
                    "category": "DISPUTED_TEXT_UNNOTICED" if is_disputed_missing_banner else "CITED_PROVISION_NOT_IN_VERIFIED_STORE",
                    "label": LABEL_DISPUTED_TEXT_MISSING_BANNER if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE,
                    "issue": f"{LABEL_DISPUTED_TEXT_MISSING_BANNER if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE}: {reason}",
                    "span": sc["span"]
                })'''

new_memo_fail = '''                is_disputed_missing_banner = (rec and rec.get("tier") == "disputed" and not has_disputed)
                if is_disputed_missing_banner:
                    disputed_notices.append({
                        "provision": cid or sc["span"],
                        "label": LABEL_DISPUTED_TEXT_NOTICE,
                        "issue": f"Provision '{cid or sc['span']}' is classified as disputed; human check required before reliance."
                    })
                failures.append({
                    "rule": "(d)",
                    "category": "DISPUTED_TEXT" if is_disputed_missing_banner else "CITED_PROVISION_NOT_IN_VERIFIED_STORE",
                    "label": LABEL_DISPUTED_TEXT_NOTICE if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE,
                    "issue": f"{LABEL_DISPUTED_TEXT_NOTICE if is_disputed_missing_banner else LABEL_CITED_PROVISION_NOT_IN_VERIFIED_STORE}: {reason}",
                    "span": sc["span"]
                })'''

assert old_memo_fail in content, "old_memo_fail not found"
content = content.replace(old_memo_fail, new_memo_fail)

with open(file_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content)

print("memo_verifier.py patched successfully")
