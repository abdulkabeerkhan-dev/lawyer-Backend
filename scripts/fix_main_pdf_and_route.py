import sys

with open('main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 1. Fix import
for idx, line in enumerate(lines[:200]):
    if 'from core.pdf_resolver import' in line and 'verify_hmac_pdf_token' not in line:
        lines[idx] = 'from core.pdf_resolver import resolve_judgment_pdf_url, fetch_storage_pdf_bytes, extract_journal_and_year, verify_hmac_pdf_token\n'
        print('Updated pdf_resolver import at line', idx+1)
        break

# 2. Restore @app.get('/api/judgments/{judgment_id:path}')
restore_endpoint = """
@app.get("/api/judgments/{judgment_id:path}")
async def get_api_judgment_endpoint(
    judgment_id: str,
    authenticated_user_id: str = Depends(verify_clerk_session)
):
    match_record = find_judgment_by_id_or_canonical(judgment_id)
    if not match_record:
        raise HTTPException(status_code=404, detail=f"Judgment '{judgment_id}' not found.")
    match_record["full_text"] = format_clean_judgment_paragraphs(match_record.get("full_text", ""))
    return match_record
"""

for idx, line in enumerate(lines):
    if '@app.get("/judgment-pdf/{case_id:path}")' in line:
        lines.insert(idx, restore_endpoint + '\n')
        print('Restored get_api_judgment_endpoint before line', idx+1)
        break

with open('main.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Done.')
