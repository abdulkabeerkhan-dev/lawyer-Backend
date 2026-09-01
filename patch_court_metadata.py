#!/usr/bin/env python3
"""
AMICUS AI — one-time Pinecone metadata patch: fix the "court" field in place.

WHY THIS EXISTS
main.py's clean_court_name() normalizes the "court" field at QUERY TIME only. That's
why the live app already shows correct buckets (Balochistan High Court, AJK Supreme
Court / AJK High Court split out from mainland courts, etc.) even though the raw
metadata stored in Pinecone has never actually changed. Two costs of leaving it
query-time-only:
  1. Every filtered query still has to widen the candidate pool and hard-filter in
     Python (query_top_k=60 when a court/regulator is named) instead of using a
     cheap, exact Pinecone $eq metadata filter, because the stored "court" string
     isn't guaranteed to already be the clean canonical value.
  2. Any other code path, script, or future integration that reads "court" straight
     from Pinecone (bypassing main.py's normalization) still sees the old, broken
     value.

This script rewrites "court" in place using the exact same clean_court_name() logic
ingest.py/main.py already use, so the fix becomes permanent instead of query-time-only.
It also writes the original value into a new "court_raw" field, purely so nothing is
lost if you ever want to audit or revert.

Note: this is a DIFFERENT script from the existing patch_metadata.py in this repo,
which re-derives the "year" field from source CSVs and needs those CSV files on disk.
This script does NOT need any source CSVs -- it only reads/rewrites what's already
stored in Pinecone.

SAFETY
  - Defaults to DRY RUN. Nothing is written unless you pass --apply.
  - Only ever writes the "court" + "court_raw" metadata fields via a metadata-only
    index.update() call -- vector embeddings themselves are never touched, so this
    cannot corrupt search quality or require re-ingestion/re-embedding.
  - Skips any vector whose normalized value already matches what's stored (no write,
    not counted as "changed").
  - Writes a local JSON log of every id + old_court + new_court it changed (or would
    change, in dry run) so the operation is auditable and reversible.
  - Idempotent: re-running after a successful --apply pass should report 0 changes.

USAGE
    pip install pinecone python-dotenv
    python3 patch_court_metadata.py                      # DRY RUN -- reports only, writes nothing
    python3 patch_court_metadata.py --apply               # actually writes the corrected "court" field
    python3 patch_court_metadata.py --apply --limit 500   # cap how many vectors get touched (test first)

Requires pinecone-client >= 3.0 (for index.list() namespace id iteration). If your
installed version lacks index.list(), the script tells you and exits cleanly instead
of crashing partway through a run.
"""
import os
import sys
import json
import argparse
import datetime
from dotenv import load_dotenv
from pinecone import Pinecone

from ingest import clean_court_name

load_dotenv()

PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "legal-kb-pk-local")
NAMESPACE = os.environ.get("PINECONE_NAMESPACE", "judgments")

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)

FETCH_BATCH_SIZE = 100
LOG_PATH = f"patch_court_metadata_log_{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"


def _meta_of(v):
    return v.metadata if hasattr(v, "metadata") else v.get("metadata", {})


def iter_all_ids():
    """Yield every vector id in the namespace, using index.list() pagination."""
    if not hasattr(index, "list"):
        print(
            "ERROR: this pinecone-client version has no index.list() (namespace id "
            "iteration). Upgrade with: pip install -U pinecone",
            file=sys.stderr,
        )
        sys.exit(1)
    for id_batch in index.list(namespace=NAMESPACE):
        if id_batch and isinstance(id_batch, list) and not isinstance(id_batch[0], str):
            for item in id_batch:
                yield getattr(item, "id", None) or item.get("id")
        else:
            for vid in id_batch:
                yield vid


def process_batch(ids, changed, args, counters):
    try:
        fetch_res = index.fetch(ids=ids, namespace=NAMESPACE)
        vectors = getattr(fetch_res, "vectors", None)
        if vectors is None:
            vectors = fetch_res.get("vectors", {})
    except Exception as e:
        print(f"  [ERROR] fetch failed for batch of {len(ids)}: {e}")
        counters["errors"] += len(ids)
        return

    for vid, v in vectors.items():
        meta = _meta_of(v)
        raw_court = str(meta.get("court", ""))
        normalized = clean_court_name(raw_court)

        if normalized == raw_court:
            counters["unchanged"] += 1
            continue

        changed.append({"id": vid, "old_court": raw_court, "new_court": normalized})

        if args.apply:
            try:
                index.update(
                    id=vid,
                    namespace=NAMESPACE,
                    set_metadata={"court": normalized, "court_raw": raw_court},
                )
            except Exception as e:
                print(f"  [ERROR] update failed for id={vid}: {e}")
                counters["errors"] += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                         help="Actually write changes. Without this flag, DRY RUN only.")
    parser.add_argument("--limit", type=int, default=None,
                         help="Stop after touching this many vectors (for testing on a subset first).")
    args = parser.parse_args()

    mode = "APPLY (writing changes)" if args.apply else "DRY RUN (no writes)"
    print(f"=== Pinecone court-metadata patch — {mode} ===")
    print(f"Index: {PINECONE_INDEX_NAME}  Namespace: {NAMESPACE}\n")

    changed = []
    counters = {"unchanged": 0, "errors": 0}
    processed = 0
    id_buffer = []

    for vid in iter_all_ids():
        if vid is None:
            continue
        id_buffer.append(vid)
        if len(id_buffer) < FETCH_BATCH_SIZE:
            continue

        process_batch(id_buffer, changed, args, counters)
        processed += len(id_buffer)
        id_buffer = []

        if processed % 1000 == 0:
            print(f"  ...processed {processed} vectors so far "
                  f"({len(changed)} changed, {counters['unchanged']} already correct)")

        if args.limit and processed >= args.limit:
            break

    if id_buffer and not (args.limit and processed >= args.limit):
        process_batch(id_buffer, changed, args, counters)
        processed += len(id_buffer)

    print("\n=== DONE ===")
    print(f"Processed: {processed}")
    print(f"Changed:   {len(changed)}{'' if args.apply else '  (dry run — not written)'}")
    print(f"Already correct: {counters['unchanged']}")
    print(f"Errors:    {counters['errors']}")

    if changed:
        with open(LOG_PATH, "w") as f:
            json.dump(changed, f, indent=2)
        print(f"\nFull change log written to: {LOG_PATH}")
        print("Sample of changes:")
        for row in changed[:10]:
            print(f"  id={row['id']}  {row['old_court']!r} -> {row['new_court']!r}")

    if not args.apply and changed:
        print(f"\nThis was a DRY RUN. Re-run with --apply to actually write these "
              f"{len(changed)} corrections.")


if __name__ == "__main__":
    main()
