r"""
scripts/load_statutes_v3_to_zilliz.py

Creates and loads `statutes_v3` collection in Zilliz Cloud strictly adhering to Phase 1B specifications:
- Dense: voyage-4-large (1024-d, input_type="document", metric=COSINE)
- Sparse: BM25 function on text (metric=BM25)
- Scalar metadata: canonical_id, act_code, act_name, section, heading, domain, forum,
  source, tier, in_force, text_as_of, supersedes, superseded_by, former_labels, provision_type
- Willful/wilful normalized in embedded and indexed text.
- Title/section/heading included in embedded text.
- Active Pakistan Code (in_force=True) + legacy v2-only (source=statutes_v2_legacy).
- Repealed acts (in_force=False) excluded from index.
- STRICT INVARIANT: ZERO mutations to judgments_v1 or Turso.
"""

import os
import sys
import json
import time
import re
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv

ROOT_DIR = Path(r"d:\lawyer-Backend")
load_dotenv(ROOT_DIR / ".env")

import voyageai
from pymilvus import (
    MilvusClient,
    CollectionSchema,
    FieldSchema,
    DataType,
    Function,
    FunctionType,
)

COLLECTION_NAME = "statutes_v3"
V3_STAGING_DIR = ROOT_DIR / "data" / "statutes_v3_staging"
REPORTS_DIR = ROOT_DIR / "reports"

ZILLIZ_URI = os.environ.get("ZILLIZ_URI")
ZILLIZ_TOKEN = os.environ.get("ZILLIZ_TOKEN")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")

def build_statutes_v3_schema() -> CollectionSchema:
    fields = [
        FieldSchema(
            name="canonical_id",
            dtype=DataType.VARCHAR,
            max_length=128,
            is_primary=True,
            auto_id=False,
            description="Canonical provision ID e.g. FIO_2001_SEC_2_g, CONST_1973_ART_199"
        ),
        FieldSchema(
            name="act_code",
            dtype=DataType.VARCHAR,
            max_length=64,
            description="Normalized act identifier e.g. PPC_1860, FIO_2001"
        ),
        FieldSchema(
            name="act_name",
            dtype=DataType.VARCHAR,
            max_length=256,
            description="Full statute title"
        ),
        FieldSchema(
            name="section",
            dtype=DataType.VARCHAR,
            max_length=64,
            description="Section or Article label e.g. 2(g), 199, Schedule Entry 5"
        ),
        FieldSchema(
            name="heading",
            dtype=DataType.VARCHAR,
            max_length=512,
            description="Section or Article title / heading"
        ),
        FieldSchema(
            name="text",
            dtype=DataType.VARCHAR,
            max_length=65535,
            enable_analyzer=True,
            description="Clean substantive text with title/section header and normalized spelling"
        ),
        FieldSchema(
            name="dense",
            dtype=DataType.FLOAT_VECTOR,
            dim=1024,
            description="1024-d Voyage-4-Large document vector"
        ),
        FieldSchema(
            name="sparse",
            dtype=DataType.SPARSE_FLOAT_VECTOR,
            description="Milvus server-side BM25 sparse vector generated from text"
        ),
        FieldSchema(
            name="domain",
            dtype=DataType.VARCHAR,
            max_length=64,
            description="Primary legal domain e.g. banking_commercial, criminal, constitutional"
        ),
        FieldSchema(
            name="forum",
            dtype=DataType.VARCHAR,
            max_length=128,
            description="Adjudicating forum e.g. Banking Court, High Court, Magistrate"
        ),
        FieldSchema(
            name="source",
            dtype=DataType.VARCHAR,
            max_length=64,
            description="Data provenance: pakistan_code or statutes_v2_legacy"
        ),
        FieldSchema(
            name="tier",
            dtype=DataType.VARCHAR,
            max_length=64,
            description="Verification status: ingested_unreviewed"
        ),
        FieldSchema(
            name="in_force",
            dtype=DataType.BOOL,
            description="Whether the enactment is currently in force"
        ),
        FieldSchema(
            name="text_as_of",
            dtype=DataType.VARCHAR,
            max_length=128,
            description="Scrape date baseline"
        ),
        FieldSchema(
            name="supersedes",
            dtype=DataType.ARRAY,
            element_type=DataType.VARCHAR,
            max_capacity=16,
            max_length=64,
            description="Acts superseded by this enactment"
        ),
        FieldSchema(
            name="superseded_by",
            dtype=DataType.VARCHAR,
            max_length=64,
            description="Newer enactment superseding this law (if applicable)"
        ),
        FieldSchema(
            name="former_labels",
            dtype=DataType.ARRAY,
            element_type=DataType.VARCHAR,
            max_capacity=16,
            max_length=64,
            description="Historical numbering or labels (e.g. 5(r) for NAO 5(u))"
        ),
        FieldSchema(
            name="provision_type",
            dtype=DataType.VARCHAR,
            max_length=32,
            description="Provision type: section, article, clause, schedule_entry"
        )
    ]

    bm25_function = Function(
        name="statutes_text_bm25",
        function_type=FunctionType.BM25,
        input_field_names=["text"],
        output_field_names=["sparse"],
    )

    schema = CollectionSchema(
        fields=fields,
        description="Statutes V3 collection (Pakistan Code + Legacy, Voyage-4-Large 1024-d + BM25)",
        enable_dynamic_field=False,
        functions=[bm25_function],
    )
    return schema

def create_collection_if_needed(client: MilvusClient):
    if client.has_collection(COLLECTION_NAME):
        print(f"Collection '{COLLECTION_NAME}' already exists.")
        return

    print(f"Creating collection '{COLLECTION_NAME}'...")
    schema = build_statutes_v3_schema()

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="dense",
        index_type="AUTOINDEX",
        metric_type="COSINE"
    )
    index_params.add_index(
        field_name="sparse",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="BM25"
    )

    client.create_collection(
        collection_name=COLLECTION_NAME,
        schema=schema,
        index_params=index_params
    )
    print(f"Collection '{COLLECTION_NAME}' created successfully.")

def run_loader(batch_size: int = 128, max_records: int = None):
    print("=" * 70)
    print(f"LOADING STATUTES V3 TO ZILLIZ ({COLLECTION_NAME})")
    print("=" * 70)

    if not ZILLIZ_URI or not ZILLIZ_TOKEN:
        raise ValueError("Missing ZILLIZ_URI or ZILLIZ_TOKEN in environment.")
    if not VOYAGE_API_KEY:
        raise ValueError("Missing VOYAGE_API_KEY in environment.")

    zclient = MilvusClient(uri=ZILLIZ_URI, token=ZILLIZ_TOKEN)
    vclient = voyageai.Client(api_key=VOYAGE_API_KEY)

    # 1. Create collection if not exists
    create_collection_if_needed(zclient)

    # 2. Gather all active records from staging
    print("Gathering active records from staging...")
    active_records = []
    for fpath in sorted(list(V3_STAGING_DIR.glob("*.json"))):
        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                if not isinstance(data, list):
                    continue
                for r in data:
                    if not r.get("in_force", True) or r.get("provision_type") == "repeal_notice":
                        continue

                    # Text formatting
                    act_name = r.get("act_name", "")
                    sec = r.get("section", "")
                    hdg = r.get("heading", "")
                    txt = r.get("text", "")

                    formatted_text = f"{act_name}\nSection {sec}: {hdg}\n\n{txt}".strip()
                    formatted_text = re.sub(r'\bwilful\b', 'willful', formatted_text, flags=re.I)

                    # Ensure fields conform to schema
                    row = {
                        "canonical_id": r["canonical_id"],
                        "act_code": r.get("act_code", "")[:64],
                        "act_name": act_name[:255],
                        "section": str(sec)[:63],
                        "heading": str(hdg)[:511],
                        "text": formatted_text[:65530],
                        "domain": r.get("domain", "other")[:63],
                        "forum": r.get("forum", "Court")[:127],
                        "source": r.get("source", "pakistan_code")[:63],
                        "tier": r.get("tier", "ingested_unreviewed")[:63],
                        "in_force": bool(r.get("in_force", True)),
                        "text_as_of": r.get("text_as_of", "")[:127],
                        "supersedes": [str(x)[:63] for x in r.get("supersedes", [])][:16],
                        "superseded_by": str(r.get("superseded_by") or "")[:63],
                        "former_labels": [str(x)[:63] for x in r.get("former_labels", [])][:16],
                        "provision_type": r.get("provision_type", "section")[:31],
                    }
                    active_records.append(row)
        except Exception as e:
            print(f"Error reading {fpath.name}: {e}")

    print(f"Total active records prepared: {len(active_records):,}")
    if max_records:
        active_records = active_records[:max_records]
        print(f"Restricted to first {max_records} records.")

    # 2.5 Check already ingested records in statutes_v3
    print(f"Checking already ingested records in '{COLLECTION_NAME}'...")
    iterator = zclient.query_iterator(collection_name=COLLECTION_NAME, output_fields=["canonical_id"], batch_size=4000)
    existing_ids = set()
    while True:
        res = iterator.next()
        if not res:
            iterator.close()
            break
        for item in res:
            existing_ids.add(item["canonical_id"])

    print(f"Already ingested in '{COLLECTION_NAME}': {len(existing_ids):,} provisions.")
    to_ingest = [r for r in active_records if r["canonical_id"] not in existing_ids]
    print(f"Remaining provisions to embed and ingest: {len(to_ingest):,}")

    if not to_ingest:
        print(f"All active provisions are already ingested into '{COLLECTION_NAME}'!")
        return

    active_records = to_ingest

    # 3. Concurrent Batch Embed & Upsert
    total_upserted = 0
    t0 = time.time()
    total_batches = (len(active_records) + batch_size - 1) // batch_size
    batches = [active_records[i:i+batch_size] for i in range(0, len(active_records), batch_size)]

    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    lock = threading.Lock()
    completed_batches = 0

    def process_batch(batch, b_idx):
        texts = [r["text"] for r in batch]

        # Call Voyage API with exponential backoff
        embeddings = None
        for attempt in range(5):
            try:
                res = vclient.embed(texts, model="voyage-4-large", input_type="document")
                embeddings = res.embeddings
                break
            except Exception as e:
                if attempt == 4:
                    raise
                time.sleep((attempt + 1) * 3)

        for r, emb in zip(batch, embeddings):
            r["dense"] = emb

        # Upsert to Milvus with retry
        for attempt in range(5):
            try:
                zclient.upsert(collection_name=COLLECTION_NAME, data=batch)
                break
            except Exception as e:
                if attempt == 4:
                    raise
                time.sleep((attempt + 1) * 2)

        nonlocal total_upserted, completed_batches
        with lock:
            total_upserted += len(batch)
            completed_batches += 1
            if completed_batches % 10 == 0 or completed_batches == total_batches:
                elapsed = time.time() - t0
                rate = total_upserted / elapsed if elapsed > 0 else 0
                print(f"Progress: Batch {completed_batches}/{total_batches} ({total_upserted:,}/{len(active_records):,} rows) [{rate:.1f} rows/s, elapsed {elapsed:.0f}s]")

    print(f"Starting ingestion with 4 concurrent workers across {total_batches} batches...")
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(process_batch, b, i) for i, b in enumerate(batches)]
        for f in as_completed(futures):
            f.result() # raise if exception occurred

    # Save final ingestion report
    final_report = {
        "collection_name": COLLECTION_NAME,
        "total_active_provisions": len(active_records),
        "total_upserted": total_upserted,
        "elapsed_seconds": round(time.time() - t0, 1),
        "status": "completed"
    }
    with open(REPORTS_DIR / "statutes_v3_ingestion_report.json", "w", encoding="utf-8") as fp:
        json.dump(final_report, fp, indent=2)

    print("\n" + "=" * 70)
    print(f"INGESTION COMPLETE: {total_upserted:,} rows into '{COLLECTION_NAME}'")
    print(f"Total time: {time.time()-t0:.1f}s")
    print("=" * 70)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print("Dry run requested. Checking schema and records without upserting...")
        schema = build_statutes_v3_schema()
        print("Schema built successfully:", schema)
    else:
        run_loader(batch_size=args.batch_size, max_records=args.max_records)
