# Prompt for Antigravity: Section security & privacy audit

Copy everything below the line into Antigravity.

---

You're auditing and hardening **Section**, a private, invitation-only legal research app for
Pakistani advocates. It's live at https://sectionai.net. Real lawyers use it with client matters,
so treat every query, saved case and note as confidential.

## The stack (read the code, don't assume)
- **Frontend** `abdulkabeerkhan-dev/section-frontend` (branch from `main`): TanStack Start + React +
  Vite, deployed on Railway. It began as a Lovable export, so expect leftover generated files.
- **Backend** `abdulkabeerkhan-dev/lawyer-Backend` (branch from `master`): FastAPI, a single large
  `main.py`, deployed on Railway, Python 3.11.
- **Auth:** Clerk production instance on `clerk.sectionai.net`. A custom sign-in form is in
  `src/routes/auth.tsx` (password, email code, forgot password). New users arrive only via Clerk
  invitations sent automatically by `POST /request-access`.
- **Data:** Supabase Postgres (RLS is ON for every table with **zero policies**, so only the
  service-role key on the server can read or write), Zilliz vectors, Cloudflare R2 judgment texts,
  Anthropic for answers.

## Ground rules (break one and the work gets thrown away)
1. **Work on a branch and open a PR. Never push to `main` or `master`.** One PR per repo, small
   commits, one concern per commit.
2. **Never delete data, users, tables, buckets or Clerk settings.** Never run destructive SQL.
   Never change RLS to *allow* anything.
3. **Never print, log or commit a secret.** Don't copy values from `.env` or Railway into code, tests,
   docs or commit messages.
4. **Prove every finding before you fix it.** For each one, show the file and line, explain how
   someone would actually exploit it, and give its severity (critical / high / medium / low). If
   you can't show a real path to harm, list it under "Not an issue" and don't change code for it.
5. **No AI slop.** That means:
   - No new dependencies unless a finding needs one, and pin the exact version.
   - No rewrites, no "refactor for clarity", no renaming, no reformatting files you didn't need to touch.
   - No new abstractions, wrappers, "utils" files or config frameworks for a one-line fix.
   - No comments that narrate the change ("// Added security check"). A comment only where the *why* isn't obvious.
   - No placeholder, TODO, mock or fake code. No `any`. No disabled lint rules. No skipped tests.
   - Don't touch the UI design, copy, legal text or statute/judgment data.
   - Don't "fix" things that aren't broken.
6. **Keep it green.** Before and after, run:
   - Frontend: `npx eslint .`, `npx tsc --noEmit`, `npm run build`.
   - Backend: `python -m pytest -q tests/test_audit_fixes_nov25.py tests/test_golden_repaired_statutes.py tests/test_named_provision_anchoring.py`.

   Your change may not add a new failure. Add a test for each backend fix.
7. **If a fix needs a dashboard or Railway change** (Clerk, Supabase, Railway, Cloudflare), don't
   fake it in code. Write it in the report as an owner action, with exact click-by-click steps.

## Already done. Verify it, don't redo it.
- **Security headers** in `src/server.ts` (HSTS, X-Frame-Options DENY, Referrer-Policy,
  Permissions-Policy, a CSP with frame-ancestors only), and generic error pages in production.
- **Clerk token checks:** the issuer allowlist is pinned (`src/integrations/clerk/verify.server.ts`).
  The backend rejects unsigned tokens in production (`verify_clerk_session`).
- **Request scoping:** server functions take `userId` from the verified token (`requireClerkAuth`),
  never from the request body.
- **Backend controls:** CORS limited to `ALLOWED_ORIGINS` in production. Search endpoints require
  sign-in. The admin role needs status `admin_approved` AND an email in `ADMIN_EMAILS`.
- **Rate limits:** `/request-access` is rate limited and validates email. Burst limits apply to
  query, PDF, pleading and export endpoints.

## What to audit, in this order
1. **Authentication and sessions**
   - Can any backend or server-function route be reached without a valid Clerk token? List every
     route with its auth dependency.
   - Is the token's `azp` (authorized party) checked? `CLERK_AUTHORIZED_PARTY` is unset today
     because the backend accepts only one value and the site serves both `sectionai.net` and
     `www.sectionai.net`. Propose the smallest fix: accept a comma-separated list, or redirect www
     to the apex domain.
   - Check `check_burst_rate_limit` and every other place that exempts
     `mock_clerk_user_id_dev_run` or any other dev/test bypass. Prove none of them is reachable when
     the environment is production.
   - Sign-in form (`src/routes/auth.tsx`): check for user enumeration, a missing lockout or delay,
     and that error messages don't leak internal details.
2. **Authorization (IDOR)**
   - For every read, update or delete on `saved_precedents`, `saved_searches`, `user_memory`,
     `user_case_diary`, `queries`, `query_jobs`, `activity_log`, `feedback` and
     `citation_feedback`: is it filtered by the token's user ID? Show a test where user A tries
     user B's id.
   - Admin endpoints and `src/routes/_authenticated/admin.tsx`: is the check done on the server,
     not just by hiding the page?
3. **Invitation abuse**
   - `/request-access` auto-invites everyone. Check the rate limit per IP AND per email, input
     lengths, and header injection in name or firm fields.
   - Recommend (don't build without asking) bot protection such as Cloudflare Turnstile, because
     every request sends a real email.
4. **Cookies and browser storage**
   - List every cookie the site sets (Clerk's `__session`, `__client_uat` and similar, plus the
     sidebar cookie in `src/components/ui/sidebar.tsx`). Report their `Secure`, `SameSite` and
     `HttpOnly` flags and lifetimes. Add `SameSite=Lax; Secure` to the sidebar cookie.
   - `localStorage` key `section_local_activity` (`QueryWorkspace.tsx`) stores recent legal queries
     in the browser. That's client-confidential data on possibly shared office computers. Propose
     clearing it on sign-out, or drop it if the server already keeps history.
   - Same check for `sessionStorage` `section_counsel_handoff`.
5. **Leftover Lovable code**
   - `src/integrations/supabase/previewAuthStorage.ts` uses `postMessage` for an editor preview,
     and `src/integrations/supabase/auth-middleware.ts` is unused Supabase-auth middleware.
   - Prove whether each is imported anywhere in production code. If it's dead, remove it. If
     `postMessage` is live, check that it validates `event.origin`.
   - Also check `src/integrations/supabase/client.ts`: does the browser hold any Supabase key, and
     is it only the publishable one?
6. **Content Security Policy**
   - Extend the CSP to a real policy: `default-src 'self'`, plus exactly the hosts the app loads:
     `clerk.sectionai.net`, `*.clerk.accounts.dev` only if still used, the backend API host,
     Google Fonts if used, and Sentry if used.
   - The inline theme script in `src/routes/__root.tsx` needs a hash or nonce, not
     `'unsafe-inline'`.
   - Test the policy in a real browser: sign in, run a query, open a PDF. Report every CSP
     violation before you call it done.
7. **Backend input handling**
   - Look for SQL or PostgREST filter injection where user text goes into
     `.ilike(...)`/`.or_(...)` (e.g. party-name search around `main.py` ~4446). Check prompt
     injection that could make the model reveal system prompts or other users' data. Check path
     traversal in PDF or file endpoints. Check SSRF in any URL fetch.
   - Check request body size limits, and that `/docs` and `/openapi.json` are off in production.
8. **Secrets and dependencies**
   - `git log -p` scan both repos for committed keys (Clerk `sk_`, R2, Supabase service role,
     Anthropic, Voyage, Zilliz). List the commit and the key *type*, never the value.
   - Run `npm audit --omit=dev` and `pip-audit`. Fix only high or critical issues with a real path.
9. **Privacy and legal pages** (Pakistan: PECA 2016; the Personal Data Protection Bill is pending)
   - The site has no Privacy Policy or Terms page. Draft both as plain, specific pages
     (`/privacy`, `/terms`). They must state:
     - what's collected (email, name, firm, queries, saved items);
     - where it's processed (Clerk, Supabase, Railway, Cloudflare R2, Zilliz, Anthropic, Voyage, Sentry);
     - retention, and how to request deletion.
   - Link them from the sign-in page footer. Mark the drafts "for the owner's lawyer to review".
     Don't invent company names, addresses or registration numbers: leave clearly marked blanks.
   - **Cookie banner:** only add one if the audit finds non-essential cookies (analytics or
     marketing). Auth cookies alone don't need a consent banner, so don't add one just to have one.

## What to hand back
One report (`docs/SECURITY_AUDIT_<date>.md` in the backend repo) with:
1. **Findings table:** id, severity, file:line, exploit in one sentence, status
   (fixed in PR / owner action / not an issue).
2. **Owner actions:** exact dashboard steps for Clerk, Railway, Supabase and Cloudflare.
3. **Not an issue:** what you checked and why it's fine, so nobody re-checks it.
4. **PR links and test output** (before and after).

Stop and ask before anything that changes how users sign in, deletes code paths users rely on, or
touches production data.
