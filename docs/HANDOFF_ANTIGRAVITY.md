# Handoff: remaining work for Antigravity

Repo: `abdulkabeerkhan-dev/lawyer-Backend`, work branch `claude/lawyers-app-relevancy-xgbjb0`
(pull it first). Production deploys from `master` on Railway; merge to master only after the
checks in each task pass.

## Ground rules (do not skip)
1. Never delete data. Mark records instead (`in_force=false`, `status="omitted"`,
   `retrieval_status='quarantined'`) and keep the old text in `text_previous`.
2. Never print or commit secrets. Keys live in `.env` (local) and Railway variables.
3. Official text only. Statute text must come from the official PDFs
   (Pakistan Code / Punjab Code), never from memory or a model.
4. Run the tests before and after; a change may not add new failures:
   `python -m pytest -q tests/test_audit_fixes_nov25.py tests/test_golden_repaired_statutes.py tests/test_named_provision_anchoring.py`
   (Python 3.11, same as production).
5. After changing any statute record, re-embed that record in Zilliz `statutes_v3`
   (model `voyage-4-large`, input_type `document`, text = `"{act_name}\nSection {section}: {heading}\n\n{text}"`).
   Long provisions (over 1,500 characters) also live in `statutes_v3_chunks`: after editing them run
   `python scripts/zilliz/build_statute_chunks.py --ids changed_ids.json` so no stale piece remains.

## Task 1 — Punjab statutes (highest value)
Source: `D:\punjab_code_pdfs\`. Biggest gaps today:
- Punjab Pre-emption Act 1991 (`PREEMPTION_1991`): 36 of 37 sections have no text.
- Punjab Rented Premises Act 2009 (`PRPA_2009`): 21 of 35 sections empty.
- Punjab Tenancy Act 1887, Punjab Partition of Immovable Property Act 2012, Punjab Protection of
  Women against Violence Act 2016, Punjab Loans Limitation Act 1904 (we hold 0-7 provisions each).

Steps:
1. Parse each PDF with `scripts/statutes/parse_pakistan_code_pdf.py`
   (`parse_with_toc(pdf_path)` returns `[{number, heading, text, omitted}]`). Punjab Code PDFs may
   use a different contents layout: check the first 30 parsed provisions by eye; if numbers or
   headings are wrong, adjust the parser for that layout rather than accepting bad text.
2. Compare with `data/statutes_v3_staging/*.json` (records whose `act_code` is the act, ids like
   `PRPA_2009_SEC_15`). Fill empty provisions; replace text only when the number matches AND the
   contents-page heading appears in the first 300 chars of the PDF text; add missing sections;
   mark omitted ones. Keep `text_previous`, set `text_source="punjabcode_pdf_<date>"`.
3. Mirror the same ids into `data/statute_tables/` (field `text`) and `in_force` into
   `data/statute_versions/`.
4. Re-embed changed ids in Zilliz (rule 5), run tests (rule 4), commit, PR to master.

## Task 2 — CrPC (Code of Criminal Procedure 1898)
The official PDF in `D:\pakistan_code_pdfs\` is 15 MB. Same procedure as Task 1 with
`act_code=CRPC_1898`, unit `SEC`. Watch for omitted sections and amended bail provisions
(ss.496-498).

## Task 3 — Acts whose PDFs did not parse
Income Tax Ordinance 2001, Sales Tax Act 1990, Family Courts Act 1964, Dissolution of Muslim
Marriages Act 1939, Registration Act 1908. Their contents pages use another layout; extend the
parser for them, verify by eye, then apply as in Task 1. Do not apply a parse you have not checked.

## Task 4 — Owner actions (need the account owner, not code)
- Rotate the Clerk secret keys and the R2 access keys that were pasted in chat.
- Clerk production instance needs a custom domain; until then the app runs on the dev instance.
- Optional: delete the old Supabase project "Legal-KB-Backend" and the 10,674 fragment rows
  (`full_judgments` where the citation is unparseable; they are already blocked from search and
  backed up in R2 `audit/full_judgments_fragment_rows_2026-11-25.json.gz`).

## Task 5 — After Anthropic credit is added
1. Choose the answer model (`CLAUDE_MODEL` on Railway; currently claude-haiku-4-5).
2. Rerun the 100-question evaluation (baseline: 57% correct, 83% useful) and compare.
3. Then set Railway `CLERK_AUTHORIZED_PARTY=https://section-frontend-production-f959.up.railway.app`
   and delete the two eval users (`section-eval-1@example.com`, `section-eval-2@example.com`) in Clerk.

## Quick sanity check after any deploy
- `GET https://lawyer-backend-production-5c6d.up.railway.app/health` -> `"healthy": true`
- `GET /api/statutes/CONST_1973_ART_184` -> `in_force: false`; `/api/statutes/CONST_1973_ART_175E` -> in force
- Sign in on the frontend and save a precedent (confirms the Clerk issuer pin).

## What was already done (do not redo)
Audit PRs #9-#14 (backend) and #2-#3 (frontend): trust gates, statute placeholders and corrupted
texts, 19 acts re-synced to the official Pakistan Code (27th Amendment: Art. 184 omitted,
Art. 175E), Limitation Art. 182 omitted, PECA/PRPA/CrPC template fixes, CORS, search sign-in,
security headers, Clerk issuer pin, dependency pins.
