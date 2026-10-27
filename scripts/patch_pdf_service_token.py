"""
scripts/patch_pdf_service_token.py
Ensures resolve_judgment_pdf_url and main.py attach ?token={hmac_token} to all judgment-pdf URLs
"""

# 1. Patch legal_ai/documents/pdf_service.py
with open("legal_ai/documents/pdf_service.py", "r", encoding="utf-8") as f:
    text = f.read()

old_code = """    target_id = case_id or citation or "judgment"
    clean_base = backend_base_url.rstrip("/")
    return f"{clean_base}/judgment-pdf/{urllib.parse.quote(str(target_id))}"""

new_code = """    target_id = case_id or citation or "judgment"
    clean_base = backend_base_url.rstrip("/")
    try:
        from core.pdf_resolver import create_hmac_pdf_token
        token = create_hmac_pdf_token(str(target_id))
        return f"{clean_base}/judgment-pdf/{urllib.parse.quote(str(target_id))}?token={token}"
    except Exception:
        return f"{clean_base}/judgment-pdf/{urllib.parse.quote(str(target_id))}"""

text_norm = text.replace("\r\n", "\n")
old_code_norm = old_code.replace("\r\n", "\n")
new_code_norm = new_code.replace("\r\n", "\n")

if old_code_norm in text_norm:
    text_norm = text_norm.replace(old_code_norm, new_code_norm, 1)
    with open("legal_ai/documents/pdf_service.py", "w", encoding="utf-8") as f:
        f.write(text_norm)
    print("SUCCESS: Patched legal_ai/documents/pdf_service.py")
else:
    print("WARNING: Old code not found in legal_ai/documents/pdf_service.py")


# 2. Patch main.py for lines 11196, 12044, 15621
with open("main.py", "r", encoding="utf-8") as f:
    main_text = f.read()

main_norm = main_text.replace("\r\n", "\n")

# Patch 11196
target_1 = """                    target_cid = meta.get("supabase_id") or meta.get("id") or case_id or neutral_cit or title

                    pdf_url_val = f"{get_backend_base_url()}/judgment-pdf/{urllib.parse.quote(str(target_cid))}"""

replace_1 = """                    target_cid = meta.get("supabase_id") or meta.get("id") or case_id or neutral_cit or title
                    pdf_tok = create_hmac_pdf_token(str(target_cid))
                    pdf_url_val = f"{get_backend_base_url()}/judgment-pdf/{urllib.parse.quote(str(target_cid))}?token={pdf_tok}"""

# Patch 12044
target_2 = """            target_pdf_id = c_supabase_id or c_id

            c_date = extract_year_from_citation_or_date(intercepted_card.get("decision_date") or intercepted_card.get("year"), c_cit, c_id)

            pdf_url = f"{get_backend_base_url()}/judgment-pdf/{urllib.parse.quote(str(target_pdf_id))}"""

replace_2 = """            target_pdf_id = c_supabase_id or c_id

            c_date = extract_year_from_citation_or_date(intercepted_card.get("decision_date") or intercepted_card.get("year"), c_cit, c_id)
            pdf_tok = create_hmac_pdf_token(str(target_pdf_id))
            pdf_url = f"{get_backend_base_url()}/judgment-pdf/{urllib.parse.quote(str(target_pdf_id))}?token={pdf_tok}"""

# Patch 15621
target_3 = """                        cid = c.get("case_id") or c.get("citation") or "precedent"

                        p_url = c.get("pdf_url") or f"{get_backend_base_url()}/judgment-pdf/{urllib.parse.quote(str(cid))}"""

replace_3 = """                        cid = c.get("case_id") or c.get("citation") or "precedent"
                        p_tok = create_hmac_pdf_token(str(cid))
                        p_url = c.get("pdf_url") or f"{get_backend_base_url()}/judgment-pdf/{urllib.parse.quote(str(cid))}?token={p_tok}"""

changed = False
if target_1 in main_norm:
    main_norm = main_norm.replace(target_1, replace_1, 1)
    changed = True
    print("SUCCESS: Patched target_1 in main.py")
else:
    print("WARNING: target_1 not found in main.py")

if target_2 in main_norm:
    main_norm = main_norm.replace(target_2, replace_2, 1)
    changed = True
    print("SUCCESS: Patched target_2 in main.py")
else:
    print("WARNING: target_2 not found in main.py")

if target_3 in main_norm:
    main_norm = main_norm.replace(target_3, replace_3, 1)
    changed = True
    print("SUCCESS: Patched target_3 in main.py")
else:
    print("WARNING: target_3 not found in main.py")

if changed:
    with open("main.py", "w", encoding="utf-8") as f:
        f.write(main_norm)
    print("SUCCESS: Saved main.py")
