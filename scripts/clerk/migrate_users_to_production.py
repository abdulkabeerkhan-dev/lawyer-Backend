r"""
scripts/clerk/migrate_users_to_production.py

Moves the users of the Clerk development instance into the production instance and re-points
their Supabase rows (queries, saved precedents, memory, ...) from the old Clerk user id to the
new one.

Input: a JSON export of the development users (id, email, names, metadata) made while the
development secret key was still configured. Passwords are not part of the Clerk Backend API,
so migrated users sign in with an email code or "Forgot password"; to keep passwords, use the
Clerk dashboard export (it includes password digests) and pass it with --dashboard-csv.

Safe to re-run: a user who already exists in production (same email) is reused, not duplicated,
and only rows still carrying the old id are updated. Dry run unless --apply is given.

Env:
  CLERK_PROD_SECRET_KEY   secret key of the production instance (sk_live_...)
  SUPABASE_ACCESS_TOKEN   Supabase Management API token
  SUPABASE_PROJECT_REF    project ref (default zrfemmnklhrzvfsqrhqs)
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

USER_TABLES = [("users", "id"), ("queries", "user_id"), ("query_jobs", "user_id"), ("saved_precedents", "user_id"),
               ("saved_searches", "user_id"), ("user_memory", "user_id"), ("activity_log", "user_id"),
               ("citation_feedback", "user_id"), ("user_case_diary", "user_id"), ("feedback", "user_id")]


def clerk(method, path, key, body=None):
    for attempt in range(4):
        req = urllib.request.Request("https://api.clerk.com/v1" + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                              "User-Agent": "section-migration/1"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            return {"_error": e.code, "_body": json.loads(e.read() or b"{}")}


def sql(query, token, ref):
    req = urllib.request.Request(f"https://api.supabase.com/v1/projects/{ref}/database/query",
                                 data=json.dumps({"query": query}).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                          "User-Agent": "section-migration/1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def load_digests(path):
    """Clerk dashboard CSV export -> {email: (digest, hasher)}."""
    out = {}
    if not path:
        return out
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            email = (row.get("primary_email_address") or row.get("email_address") or "").strip().lower()
            digest = (row.get("password_digest") or "").strip()
            hasher = (row.get("password_hasher") or "").strip()
            if email and digest and hasher:
                out[email] = (digest, hasher)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", required=True, help="JSON export of the development users")
    ap.add_argument("--dashboard-csv", help="optional Clerk dashboard export with password digests")
    ap.add_argument("--apply", action="store_true", help="create users and update Supabase (default: dry run)")
    ap.add_argument("--include-test", action="store_true", help="also move @example.com test accounts")
    args = ap.parse_args()

    key = os.environ.get("CLERK_PROD_SECRET_KEY", "")
    if args.apply and not key.startswith("sk_live_"):
        sys.exit("CLERK_PROD_SECRET_KEY must be the production secret key (sk_live_...)")
    inst = clerk("GET", "/instance", key) if key else {}
    if args.apply and inst.get("environment_type") != "production":
        sys.exit(f"The key does not belong to a production instance: {inst.get('environment_type')}")
    token = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
    ref = os.environ.get("SUPABASE_PROJECT_REF", "zrfemmnklhrzvfsqrhqs")

    users = json.load(open(args.export))
    digests = load_digests(args.dashboard_csv)
    mapping, report = {}, {"created": 0, "reused": 0, "skipped_test": 0, "failed": 0, "with_password": 0}
    for u in users:
        email = (u.get("email") or "").strip().lower()
        if not email:
            report["failed"] += 1
            continue
        if email.endswith("@example.com") and not args.include_test:
            report["skipped_test"] += 1
            continue
        if not args.apply:
            mapping[u["id"]] = "(new id)"
            continue
        found = clerk("GET", f"/users?email_address={urllib.request.quote(email)}", key)
        if isinstance(found, list) and found:
            mapping[u["id"]] = found[0]["id"]
            report["reused"] += 1
            continue
        body = {"email_address": [email], "external_id": u["id"],
                "first_name": u.get("first_name") or None, "last_name": u.get("last_name") or None,
                "public_metadata": u.get("public_metadata") or {}, "private_metadata": u.get("private_metadata") or {},
                "unsafe_metadata": u.get("unsafe_metadata") or {}, "skip_password_requirement": True}
        if email in digests:
            body["password_digest"], body["password_hasher"] = digests[email]
            body.pop("skip_password_requirement")
        res = clerk("POST", "/users", key, body)
        if res.get("id"):
            mapping[u["id"]] = res["id"]
            report["created"] += 1
            report["with_password"] += int(email in digests)
        else:
            report["failed"] += 1
            print("create failed:", email.split("@")[1], res.get("_error"),
                  [e.get("code") for e in (res.get("_body") or {}).get("errors", [])], file=sys.stderr)

    rows = {}
    if token:
        for table, col in USER_TABLES:
            ids = ",".join(lit(o) for o in mapping)
            if not ids:
                break
            r = sql(f"select count(*) n from {table} where {col} in ({ids})", token, ref)
            rows[table] = r[0]["n"] if isinstance(r, list) and r else r
            if args.apply:
                for old, new in mapping.items():
                    if new and not new.startswith("("):
                        sql(f"update {table} set {col} = {lit(new)} where {col} = {lit(old)}", token, ref)
    json.dump(mapping, open(args.export + ".id_map.json", "w"), indent=1)
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "users": report, "rows_to_repoint": rows}, indent=1))


if __name__ == "__main__":
    main()
