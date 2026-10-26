import re

file_path = "legal_ai/verification/memo_verifier.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update CONDITION_TERMS
old_cond = 'CONDITION_TERMS = ["if", "unless", "provided", "except", "subject to", "not"]'
new_cond = '''BLOCKING_CONDITION_TERMS = [
    "shall not", "unless", "except", "provided that", "subject to", "notwithstanding", "if"
]
CONDITION_TERMS = BLOCKING_CONDITION_TERMS'''

assert old_cond in content, "old_cond not found"
content = content.replace(old_cond, new_cond)

# 2. Update ellipsis loop
old_loop = '''                                conds = [c for c in CONDITION_TERMS if re.search(r'\\b' + re.escape(c) + r'\\b', om_slice, re.IGNORECASE)]
                                if conds:
                                    deceptive_terms.extend(conds)
                                    rendered_parts.append(f"[... OMITTED IN QUOTE (DROPS MATERIAL CONDITION '{','.join(conds)}'): \\"{om_slice}\\" ...]")
                                else:
                                    rendered_parts.append(f"[... OMITTED IN QUOTE: \\"{om_slice}\\" ...]")'''

new_loop = '''                                conds = []
                                for term in BLOCKING_CONDITION_TERMS:
                                    pat = r'\\b' + re.escape(term).replace(r'\\ ', r'\\s+') + r'\\b'
                                    if re.search(pat, om_slice, re.IGNORECASE):
                                        conds.append(term)
                                if conds:
                                    deceptive_terms.extend(conds)
                                    rendered_parts.append(f"[... OMITTED IN QUOTE (DROPS MATERIAL CONDITION '{', '.join(conds)}'): \\"{om_slice}\\" ...]")
                                else:
                                    rendered_parts.append(f"[... OMITTED IN QUOTE (REVIEW): \\"{om_slice}\\" ...]")'''

assert old_loop in content, "old_loop not found"
content = content.replace(old_loop, new_loop)

# 3. Add attach_system_disputed_banner and verify_pleading_citations_and_quotes
functions_to_add = '''
def attach_system_disputed_banner(memo_text: str, disputed_notices: List[Dict[str, Any]]) -> str:
    """
    Attaches an authentic structural warning banner to a memorandum after verification,
    satisfying Rule (b) and Rule (d) for disputed statutory provisions.
    """
    if not disputed_notices:
        return memo_text
    prov_names = ", ".join(sorted(list({str(d.get("provision", "")) for d in disputed_notices})))
    banner_lines = [
        "> [!WARNING] DISPUTED TEXT — HUMAN CHECK REQUIRED",
        f"> The following statutory provisions cited in this memorandum are classified as disputed in official gazettes or high court rulings: {prov_names}.",
        "> Independent human verification against authenticated gazette prints is required prior to formal court reliance."
    ]
    return "\\n".join(banner_lines) + "\\n\\n" + memo_text


def verify_pleading_citations_and_quotes(pleading_text: str, is_system_rendered: bool = False) -> Dict[str, Any]:
    """
    Specialized fail-closed verifier for legal pleadings and user-supplied court submissions.
    Verifies Rule (a) (statutory quotes), Rule (c) (case authorities), and Rule (d) (statutory citations).
    Explicitly EXEMPTS Rule (e) (unsourced analysis) so that client facts and narrative pleading
    allegations are allowed without false blocks.
    """
    verifier = MemoVerifier()
    res = verifier.verify_memo(pleading_text, is_system_rendered=is_system_rendered)
    pleading_failures = [f for f in res["failures"] if f.get("rule") in ("(a)", "(b)", "(c)", "(d)")]
    passed = (len(pleading_failures) == 0)
    return {
        "passed": passed,
        "verdict": "ACCEPTED" if passed else "BLOCKED",
        "failures": pleading_failures,
        "total_failures": len(pleading_failures),
        "quotes_checked": res["quotes_checked"],
        "quotes_passed": res["quotes_passed"],
        "quotes_failed": res["quotes_failed"],
        "cases_checked": res["cases_checked"],
        "cases_passed": res["cases_passed"],
        "cases_failed": res["cases_failed"],
        "statutes_checked": res["statutes_checked"],
        "statutes_passed": res["statutes_passed"],
        "statutes_failed": res["statutes_failed"],
        "disputed_notices": res["disputed_notices"],
        "omitted_ellipses": res["omitted_ellipses"],
        "scope": "pleading_quotes_and_citations_only"
    }
'''

content += functions_to_add

with open(file_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content)

print("memo_verifier.py patched successfully")
