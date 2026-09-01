#!/usr/bin/env python3
"""
AMICUS AI — one-shot diagnostic script for the issues raised in the backend audit
(mixed embeddings, statute duplicate text, PLD count, specific "bad record" pulls,
thin/degenerate-chunk sweep).

WHY THIS EXISTS
Claude's sandboxed workspace (both the cloud container and the local device-bridge
sandbox) does not have network egress to api.pinecone.io / api.voyageai.com, so this
script could not be run from inside that session. Run it yourself wherever this repo
normally runs (your own machine, or wherever `main.py`/`ingest.py` already run), with
the same `.env` this project uses, and share the printed output back.

USAGE
    pip install pinecone voyageai python-dotenv
    python3 diagnostics.py            # runs everything
    python3 diagnostics.py --only pld_count,thin_chunks

All operations here are READ-ONLY (query/fetch/describe). Nothing is upserted,
updated, or deleted.
"""
import os
import sys
import argparse
import json
from dotenv import load_dotenv
from pinecone import Pinecone
import voyageai

# Reuse the SAME clean_court_name() that main.py now uses at query time, so this script's
# "what court does the live app actually see" checks match reality instead of trusting
# Pinecone's raw, unfixed stored metadata. Without this, a fix to clean_court_name() (like the
# AJK/Balochistan normalization fix applied 2026-08-23) is invisible to this script even though
# it's already working in the live app -- the raw "court" field in Pinecone itself is unchanged,
# only how main.py interprets it at query time changed.
from ingest import clean_court_name

load_dotenv()

PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "legal-kb-pk-local")
NAMESPACE = os.environ.get("PINECONE_NAMESPACE", "judgments")
VOYAGE_API_KEY = os.environ["VOYAGE_API_KEY"]

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)
voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)


def embed_query(text):
    res = voyage_client.embed([text], model="voyage-law-2", input_type="query")
    return res.embeddings[0]


def _meta_of(m):
    return m.get("metadata", {}) if isinstance(m, dict) else (getattr(m, "metadata", {}) or {})


def section_header(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


# ---------------------------------------------------------------------------
def check_index_overview():
    section_header("0. INDEX OVERVIEW")
    desc = pc.describe_index(PINECONE_INDEX_NAME)
    print(desc)
    stats = index.describe_index_stats()
    print("\nStats:")
    print(stats)
    embed_config = getattr(desc, "embed", None)
    if embed_config:
        print("\nThis index has Pinecone-integrated embedding configured:")
        print(embed_config)
    else:
        print("\nNo integrated-embedding config — embeddings are generated client-side "
              "(Voyage AI in ingest.py). This means Pinecone itself has NO record of which "
              "model produced any given vector; that has to be tracked in metadata or inferred.")


# ---------------------------------------------------------------------------
def check_statute_duplicate():
    section_header("1a. STATUTE CONTENT MISMATCH: PECA 2016 vs Banks (Nationalization) Amendment Act 2016")
    targets = [
        "Prevention of Electronic Crimes Act 2016",
        "Banks (Nationalization) (Amendment) Act 2016",
    ]
    seen_texts = {}
    for t in targets:
        vec = embed_query(t)
        res = index.query(vector=vec, top_k=5, namespace=NAMESPACE, include_metadata=True,
                           filter={"title": {"$eq": t}})
        matches = res.get("matches", []) if isinstance(res, dict) else getattr(res, "matches", [])
        if not matches:
            # fall back to semantic search without exact title filter
            res = index.query(vector=vec, top_k=5, namespace=NAMESPACE, include_metadata=True)
            matches = res.get("matches", []) if isinstance(res, dict) else getattr(res, "matches", [])
        print(f"\n--- '{t}' — top {len(matches)} matches ---")
        for m in matches[:3]:
            meta = _meta_of(m)
            mid = m.get("id") if isinstance(m, dict) else getattr(m, "id", None)
            text = str(meta.get("text", meta.get("text_preview", "")))
            print(f"  id={mid}  title={meta.get('title')!r}  dataset_category={meta.get('dataset_category')!r}")
            print(f"  text[:300]={text[:300]!r}")
            seen_texts.setdefault(t, []).append((mid, text))

    a_texts = {t for _, t in seen_texts.get(targets[0], [])}
    b_texts = {t for _, t in seen_texts.get(targets[1], [])}
    overlap = a_texts & b_texts
    if overlap:
        print(f"\n[CONFIRMED] {len(overlap)} identical text block(s) shared between the two statutes' "
              f"top matches — this is the copy/indexing bug described.")
    else:
        print("\n[NOT REPRODUCED in this sample] — try increasing top_k or checking exact IDs "
              "if you still see this in the product.")


# ---------------------------------------------------------------------------
def check_pld_count():
    section_header("2. PLD-REPORTED JUDGMENT COUNT")
    # Pinecone metadata filters don't support substring/regex match, only $eq/$in/etc, so we
    # can't do "citation LIKE '%PLD%'" server-side. Also: asking for top_k=10000 WITH metadata
    # in one call exceeds Pinecone's response-size limit (this is what errored last run). Fix:
    # get the exact chunk count per court with a metadata-FREE query (cheap, allowed at high
    # top_k), then sample a smaller metadata-included batch to estimate what fraction carries a
    # PLD citation, and extrapolate. This is still an estimate, not an exact count — flagged
    # clearly below — but it no longer crashes and it's a much better estimate than a raw
    # top_k=10000 sample would have been anyway (that undercounts on large courts).
    courts = [
        "Supreme Court of Pakistan", "Lahore High Court", "Sindh High Court",
        "Peshawar High Court", "Islamabad High Court", "Balochistan High Court",
        "Federal Shariat Court",
    ]
    SAMPLE_SIZE = 300
    generic_vector = embed_query("Pakistan law supreme court cases")
    total_pld_estimate = 0
    for court in courts:
        # Exact chunk count for this court (no metadata payload, so top_k=10000 is fine).
        count_res = index.query(vector=generic_vector, filter={"court": {"$eq": court}}, top_k=10000,
                                 namespace=NAMESPACE, include_metadata=False)
        count_matches = count_res.get("matches", []) if isinstance(count_res, dict) else getattr(count_res, "matches", [])
        exact_chunk_count = len(count_matches)

        # Smaller metadata-included sample to estimate the PLD ratio.
        sample_res = index.query(vector=generic_vector, filter={"court": {"$eq": court}}, top_k=SAMPLE_SIZE,
                                  namespace=NAMESPACE, include_metadata=True)
        sample_matches = sample_res.get("matches", []) if isinstance(sample_res, dict) else getattr(sample_res, "matches", [])
        pld_in_sample = sum(1 for m in sample_matches if "pld" in str(_meta_of(m).get("citation", "")).lower())
        sample_n = len(sample_matches)
        ratio = (pld_in_sample / sample_n) if sample_n else 0.0
        estimated_pld_chunks = round(ratio * exact_chunk_count)
        total_pld_estimate += estimated_pld_chunks

        print(f"  {court}: {exact_chunk_count} total chunks (exact) | "
              f"{pld_in_sample}/{sample_n} sampled chunks carry a PLD citation ({ratio:.1%}) | "
              f"~{estimated_pld_chunks} estimated PLD chunks")

    print(f"\nTOTAL estimated chunks with a PLD citation across these 7 courts: ~{total_pld_estimate}")
    print("NOTE: this is CHUNK-level, not case-level (one judgment = several chunks), and the "
          "per-court figure is an extrapolation from a 300-chunk sample, not an exact scan of "
          "every vector. Treat it as a directional estimate for gap-scanning, not an audited count.")


# ---------------------------------------------------------------------------
def check_normalized_court_distribution():
    section_header("2c. NORMALIZED COURT DISTRIBUTION (post-fix view, what main.py now actually sees)")
    # Broad, filter-free sample across a spread of court-flavored probes, then bucket by
    # clean_court_name(raw_value) instead of trusting the raw stored string or a server-side
    # $eq filter. This is what actually validates whether the clean_court_name() fix works --
    # the earlier pld_count/citation_format checks query Pinecone's raw metadata directly and
    # can never see this improvement, since the raw "court" field on disk hasn't changed.
    probes = [
        "High Court judgment Pakistan", "Balochistan Quetta court ruling", "AJK Kashmir court case",
        "Sindh Karachi court judgment", "Lahore court judgment", "Supreme Court Pakistan ruling",
    ]
    seen_ids = set()
    normalized_counts = {}
    raw_examples = {}
    for probe in probes:
        vec = embed_query(probe)
        res = index.query(vector=vec, top_k=200, namespace=NAMESPACE, include_metadata=True)
        matches = res.get("matches", []) if isinstance(res, dict) else getattr(res, "matches", [])
        for m in matches:
            mid = m.get("id") if isinstance(m, dict) else getattr(m, "id", None)
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            meta = _meta_of(m)
            raw_court = str(meta.get("court", ""))
            normalized = clean_court_name(raw_court)
            normalized_counts[normalized] = normalized_counts.get(normalized, 0) + 1
            raw_examples.setdefault(normalized, set()).add(raw_court)

    print(f"Deduped sample size: {len(seen_ids)} chunks across {len(probes)} probes.\n")
    for normalized, count in sorted(normalized_counts.items(), key=lambda x: -x[1]):
        examples = list(raw_examples[normalized])[:3]
        print(f"  {normalized}: {count} chunks  <- raw values seen: {examples}")
    print("\nIf 'Balochistan High Court' now appears here with a non-zero count (pulling in raw "
          "values like 'High Court Of Balochistan'), the normalization fix is working — the live "
          "app will now correctly bucket those records, even though the raw Pinecone metadata is "
          "untouched. Same check applies to 'AJK Supreme Court' / 'AJK High Court' no longer "
          "hiding inside 'Supreme Court of Pakistan' or a province High Court bucket.")


# ---------------------------------------------------------------------------
def check_citation_format_and_balochistan():
    section_header("2b. CITATION FORMAT SAMPLE + BALOCHISTAN HC GAP CHECK")

    # Broad sample of judgment citations across courts, no court filter, to see what the
    # citation field actually looks like in practice (PLD/PLJ-style vs docket numbers vs
    # "No Citation").
    generic_vector = embed_query("Pakistan court judgment ruling")
    res = index.query(vector=generic_vector, top_k=50, namespace=NAMESPACE, include_metadata=True)
    matches = res.get("matches", []) if isinstance(res, dict) else getattr(res, "matches", [])
    print(f"Sampled {len(matches)} broad judgment-like matches. Citation field values seen:")
    reporter_style = 0
    for m in matches[:30]:
        meta = _meta_of(m)
        cit = str(meta.get("citation", ""))
        court = str(meta.get("court", ""))
        print(f"  court={court!r} citation={cit!r}")
        if any(tag in cit.upper() for tag in ("PLD", "SCMR", "MLD", "YLR", "PCRLJ", "CLC")):
            reporter_style += 1
    print(f"\n{reporter_style}/{min(30, len(matches))} sampled citations look like a real reporter "
          f"citation (PLD/SCMR/MLD/YLR/PCRLJ/CLC). The rest are docket numbers, 'No Citation', or blank.")

    # Balochistan gap check: search with NO court filter for Balochistan-flavored judgment
    # queries and report whatever court label the top matches actually carry.
    print("\n--- Balochistan HC gap check (no court filter) ---")
    probes = ["Balochistan High Court judgment", "Quetta High Court ruling", "contempt of court Balochistan"]
    for probe in probes:
        vec = embed_query(probe)
        res = index.query(vector=vec, top_k=10, namespace=NAMESPACE, include_metadata=True)
        matches = res.get("matches", []) if isinstance(res, dict) else getattr(res, "matches", [])
        print(f"\nProbe: {probe!r}")
        for m in matches[:5]:
            meta = _meta_of(m)
            print(f"  court={meta.get('court')!r} dataset_category={meta.get('dataset_category')!r} "
                  f"title={meta.get('title')!r} score={m.get('score') if isinstance(m, dict) else getattr(m, 'score', None)}")
    print("\nIf none of the above ever say court='Balochistan High Court' (or anything Balochistan-shaped), "
          "that's a genuine 'we never scraped/ingested this court' gap, not a naming mismatch.")


# ---------------------------------------------------------------------------
KNOWN_BAD_RECORDS = [
    ("Khadim Hussain v. The State (Crl. P. No. 974/2025)", "Khadim Hussain"),
    ("sbp-ROW-37", None),
    ("Mst. Zubaida Bibi vs. The State & Others (21-O54-L/23)", "Zubaida Bibi"),
    ("ccp-ROW-4", None),
    ("ccp_vector-ROW-4", None),
]


def check_bad_records():
    section_header("3. SPECIFIC 'BAD RECORD' PULLS (near-empty / polluting chunks)")
    for label, search_text in KNOWN_BAD_RECORDS:
        print(f"\n--- {label} ---")
        # 1) Try direct fetch by likely ID prefix (vector IDs are f"{case_id}_chunk_{n}")
        possible_ids = [f"{label}_chunk_0", f"{label}_chunk_1"]
        try:
            fetch_res = index.fetch(ids=possible_ids, namespace=NAMESPACE)
            found = getattr(fetch_res, "vectors", {}) or (fetch_res.get("vectors", {}) if isinstance(fetch_res, dict) else {})
            if found:
                for vid, v in found.items():
                    meta = v.metadata if hasattr(v, "metadata") else v.get("metadata", {})
                    print(f"  [direct fetch] id={vid}")
                    print(f"    text={str(meta.get('text', meta.get('text_preview','')))!r}")
                    continue
        except Exception as e:
            print(f"  direct fetch failed (expected if ID guess is wrong): {e}")

        # 2) Fall back to semantic search for the case name/id string, then report full text length
        if search_text:
            vec = embed_query(search_text)
            res = index.query(vector=vec, top_k=5, namespace=NAMESPACE, include_metadata=True)
            matches = res.get("matches", []) if isinstance(res, dict) else getattr(res, "matches", [])
            for m in matches:
                meta = _meta_of(m)
                title = str(meta.get("title", meta.get("case_title", "")))
                if search_text.lower().split()[0] in title.lower() or search_text.lower().split()[0] in str(meta.get("case_id","")).lower():
                    mid = m.get("id") if isinstance(m, dict) else getattr(m, "id", None)
                    text = str(meta.get("text", meta.get("text_preview", "")))
                    print(f"  [semantic match] id={mid} title={title!r}")
                    print(f"    text length={len(text)} chars, text={text[:400]!r}")


# ---------------------------------------------------------------------------
def check_stub_dataset_quality():
    section_header("2d. TITLE-ONLY STUB CHECK: na_acts / sbp / ccp / pakistan_code / punjab_code / punjab_laws / senate_acts")
    # These dataset_category values were flagged as suspected "title-only stub" records
    # (e.g. sbp-ROW-37, ccp-ROW-4 in the bad-records sweep) -- chunks that carry a case/document
    # title but little or no real body text. This check tells you WHETHER that's true and HOW
    # BADLY, without needing the source CSVs yet: if avg/median text length here is tiny and a
    # large fraction of chunks are near-empty, that's strong evidence of either (a) a genuine gap
    # in the source data for these categories, or (b) an ingest.py content-column-selection bug
    # (e.g. picking up a short "title"/"subject" column as the main text instead of the actual
    # full-text column). It can't fully distinguish (a) from (b) without the source CSVs -- that
    # still needs them -- but a near-100%-stub result across ALL of these categories, especially
    # if it lines up with a specific column name pattern, points strongly at (b).
    categories = ["na_acts", "sbp", "ccp", "pakistan_code", "punjab_code", "punjab_laws", "senate_acts"]
    generic_vector = embed_query("Pakistan law statute regulation act")
    STUB_THRESHOLD = 200  # chars; below this, treat as a likely title-only stub

    for cat in categories:
        res = index.query(vector=generic_vector, filter={"dataset_category": {"$eq": cat}}, top_k=100,
                           namespace=NAMESPACE, include_metadata=True)
        matches = res.get("matches", []) if isinstance(res, dict) else getattr(res, "matches", [])
        if not matches:
            print(f"\n  {cat}: 0 chunks found with this exact dataset_category filter "
                  f"(either mis-named category or genuinely not ingested).")
            continue

        lengths = []
        stub_count = 0
        samples = []
        for m in matches:
            meta = _meta_of(m)
            text = str(meta.get("text", meta.get("text_preview", "")))
            lengths.append(len(text))
            if len(text) < STUB_THRESHOLD:
                stub_count += 1
            if len(samples) < 2:
                samples.append((meta.get("title", meta.get("case_title", "")), text[:200]))

        n = len(lengths)
        avg_len = sum(lengths) / n if n else 0
        median_len = sorted(lengths)[n // 2] if n else 0
        stub_pct = stub_count / n if n else 0
        print(f"\n  {cat}: {n} chunks sampled | avg text length={avg_len:.0f} chars | "
              f"median={median_len} chars | {stub_count}/{n} ({stub_pct:.0%}) under {STUB_THRESHOLD} chars")
        for title, snippet in samples:
            print(f"    example: title={title!r} text={snippet!r}")

    print("\nInterpretation guide:")
    print("  - If a category shows ~0% stubs with normal-length text: not a stub problem, ignore.")
    print("  - If a category shows a HIGH stub % here: either the source CSV for that category")
    print("    genuinely only has short entries (a real data gap -- needs the source CSVs to")
    print("    confirm and can only be fixed by re-scraping/sourcing fuller text), OR ingest.py")
    print("    picked the wrong column as the main text for that file (a code bug -- check")
    print("    CONTENT_COLUMN / COLUMN_ALIASES in ingest.py against that CSV's actual headers).")
    print("    Share this output plus that CSV's column headers and this can be narrowed down")
    print("    without needing the full file.")


# ---------------------------------------------------------------------------
def check_thin_chunks():
    section_header("4. THIN / DEGENERATE CHUNK SWEEP")
    # Sample across a spread of generic legal queries and flag anything whose indexed text
    # is suspiciously short (a likely cause of "generic embedding matches everything").
    probes = [
        "constitutional writ jurisdiction", "criminal bail application", "family law maintenance",
        "banking regulation", "tax appeal", "contract dispute", "service tribunal appeal",
        "narcotics possession case", "land revenue mutation", "electricity consumer complaint",
    ]
    THRESHOLD = 120  # chars; a real judgment chunk should be well above this
    thin_hits = {}
    for probe in probes:
        vec = embed_query(probe)
        res = index.query(vector=vec, top_k=20, namespace=NAMESPACE, include_metadata=True)
        matches = res.get("matches", []) if isinstance(res, dict) else getattr(res, "matches", [])
        for m in matches:
            meta = _meta_of(m)
            text = str(meta.get("text", meta.get("text_preview", "")))
            if len(text) < THRESHOLD:
                mid = m.get("id") if isinstance(m, dict) else getattr(m, "id", None)
                thin_hits[mid] = {"len": len(text), "text": text, "title": meta.get("title"),
                                   "court": meta.get("court"), "seen_in_probes": thin_hits.get(mid, {}).get("seen_in_probes", 0) + 1}
    print(f"Found {len(thin_hits)} distinct chunk(s) under {THRESHOLD} chars across {len(probes)} unrelated probe queries:")
    for mid, info in sorted(thin_hits.items(), key=lambda x: -x[1]["seen_in_probes"]):
        print(f"  id={mid} len={info['len']} title={info['title']!r} court={info['court']!r} text={info['text']!r}")
    print("\nA chunk under ~120 chars that keeps surfacing across unrelated probes is exactly the "
          "'generic/degenerate embedding' pattern described in the bug report — its embedding "
          "carries almost no real signal, so it scores as a weak-but-present match on nearly "
          "everything. These are strong candidates to purge and re-ingest from source.")


# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated subset: overview,statute_dup,pld_count,bad_records,thin_chunks")
    args = parser.parse_args()

    all_checks = {
        "overview": check_index_overview,
        "statute_dup": check_statute_duplicate,
        "pld_count": check_pld_count,
        "normalized_courts": check_normalized_court_distribution,
        "citation_format": check_citation_format_and_balochistan,
        "bad_records": check_bad_records,
        "stub_datasets": check_stub_dataset_quality,
        "thin_chunks": check_thin_chunks,
    }
    to_run = args.only.split(",") if args.only else list(all_checks.keys())
    for name in to_run:
        name = name.strip()
        if name not in all_checks:
            print(f"Unknown check '{name}', skipping. Valid: {list(all_checks.keys())}")
            continue
        try:
            all_checks[name]()
        except Exception as e:
            print(f"\n[ERROR running {name}]: {e}")


if __name__ == "__main__":
    main()
