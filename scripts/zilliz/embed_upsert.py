r"""
scripts/zilliz/embed_upsert.py

Idempotent, resumable embedding and upsert pipeline for Pakistani case law into Zilliz Cloud.
Adheres strictly to docs/antigravity/RULES.md (Rules 7, 9, 10, 11, 16, 17, 19, 22)
and docs/ZILLIZ_MIGRATION_PLAN.md §8.

Guarantees:
1. Batched by whole cases (never split a case across batches).
2. Primary key chunk_id = f"{case_key}:{section}:{ordinal:03d}".
3. Writes via upsert; re-running produces zero duplicates.
4. Manifest-driven: SQLite table `vector_ingest_manifest`. Skips chunks already done with identical chunk_hash + embed_model.
5. Stale chunk deletion: deletes lingering chunks when a case is re-segmented.
6. Spending cap enforcement: <= $5 (pilot) or <= $60 (full run).
"""

import os
import sys
import time
import json
import sqlite3
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional, Set, Tuple
from collections import OrderedDict
import numpy as np

# Ensure project root in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
from pymilvus import MilvusClient

LOG_DIR = r"I:\zilliz_work\logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, "embed_upsert.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("embed_upsert")

PRICE_PER_MILLION_TOKENS = 0.12


class IngestManifest:
    """SQLite-backed run manifest for idempotency and resume tracking."""

    def __init__(self, db_path: str = r"I:\zilliz_work\manifest.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS vector_ingest_manifest (
                    chunk_id TEXT PRIMARY KEY,
                    case_key TEXT NOT NULL,
                    chunk_hash TEXT NOT NULL,
                    embed_model TEXT NOT NULL,
                    collection TEXT NOT NULL,
                    status TEXT NOT NULL,
                    batch_id TEXT,
                    upserted_at TEXT,
                    source_file_sha256 TEXT
                );
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_manifest_case ON vector_ingest_manifest(case_key);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_manifest_status ON vector_ingest_manifest(status);")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS run_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)

    def get_metadata(self, key: str, default: Optional[str] = None) -> Optional[str]:
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM run_metadata WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

    def set_metadata(self, key: str, value: str):
        with self.conn:
            self.conn.execute(
                "INSERT INTO run_metadata (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def is_chunk_done(self, chunk_id: str, chunk_hash: str, embed_model: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT 1 FROM vector_ingest_manifest WHERE chunk_id = ? AND chunk_hash = ? AND embed_model = ? AND status = 'done'",
            (chunk_id, chunk_hash, embed_model),
        )
        return cursor.fetchone() is not None

    def mark_chunks_done(self, rows: List[Tuple[str, str, str, str, str, str, str]]):
        """Batch record completed chunks: (chunk_id, case_key, chunk_hash, embed_model, collection, status, batch_id, upserted_at)."""
        now = datetime.utcnow().isoformat()
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO vector_ingest_manifest 
                    (chunk_id, case_key, chunk_hash, embed_model, collection, status, batch_id, upserted_at)
                VALUES (?, ?, ?, ?, ?, 'done', ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    case_key=excluded.case_key,
                    chunk_hash=excluded.chunk_hash,
                    embed_model=excluded.embed_model,
                    collection=excluded.collection,
                    status='done',
                    batch_id=excluded.batch_id,
                    upserted_at=excluded.upserted_at;
                """,
                [(r[0], r[1], r[2], r[3], r[4], r[5], now) for r in rows],
            )

    def get_completed_count(self, collection: str, embed_model: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT count(*) FROM vector_ingest_manifest WHERE collection = ? AND embed_model = ? AND status = 'done'",
            (collection, embed_model),
        )
        return cursor.fetchone()[0]


class EmbedUpsertPipeline:
    def __init__(
        self,
        collection_name: str = "judgments_v1",
        embed_model: str = "voyage-law-2",
        spend_cap: float = 60.0,
        manifest_db: str = r"I:\zilliz_work\manifest.db",
        dry_run: bool = False,
    ):
        self.collection_name = collection_name
        self.embed_model = embed_model
        self.spend_cap = spend_cap
        self.dry_run = dry_run
        self.manifest = IngestManifest(db_path=manifest_db)

        self.total_tokens_used = int(self.manifest.get_metadata("total_tokens_used", "0"))
        self.total_spend_usd = self.total_tokens_used * PRICE_PER_MILLION_TOKENS / 1_000_000

        # Optional pre-computed embedding cache (e.g. from bakeoff)
        model_slug = embed_model.replace("-", "_")
        bakeoff_cache_dir = os.path.join(r"I:\zilliz_work\bakeoff", model_slug)
        self.embedding_cache: Dict[str, List[float]] = {}
        npy_path = os.path.join(bakeoff_cache_dir, "embeddings.npy")
        manifest_path = os.path.join(bakeoff_cache_dir, "manifest.json")
        if os.path.exists(npy_path) and os.path.exists(manifest_path):
            logger.info(f"Loading pre-computed embeddings cache from {bakeoff_cache_dir}...")
            with open(manifest_path, "r", encoding="utf-8") as f:
                c_man = json.load(f)
            cached_embs = np.load(npy_path)
            for cid, emb in zip(c_man.get("chunk_ids", []), cached_embs):
                self.embedding_cache[cid] = emb.tolist()
            logger.info(f"Loaded {len(self.embedding_cache)} embeddings into memory cache.")

        load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
        api_key = os.environ.get("VOYAGE_API_KEY")
        if not api_key:
            raise ValueError("VOYAGE_API_KEY missing from .env")

        import voyageai
        self.voyage_client = voyageai.Client(api_key=api_key)

        uri = os.environ.get("ZILLIZ_URI")
        token = os.environ.get("ZILLIZ_TOKEN")
        if not uri or not token:
            raise ValueError("ZILLIZ_URI or ZILLIZ_TOKEN missing from .env")

        if not dry_run:
            logger.info("Connecting to Zilliz Cloud...")
            self.milvus_client = MilvusClient(uri=uri, token=token)
            if not self.milvus_client.has_collection(collection_name):
                raise RuntimeError(
                    f"Collection '{collection_name}' does not exist! Run create_collection.py first."
                )
        else:
            self.milvus_client = None

    def check_and_record_spend(self, tokens: int):
        est_cost = (self.total_tokens_used + tokens) * PRICE_PER_MILLION_TOKENS / 1_000_000
        if est_cost > self.spend_cap:
            raise RuntimeError(
                f"Spending cap exceeded! Total spend would reach ${est_cost:.4f} > ${self.spend_cap:.2f}"
            )
        self.total_tokens_used += tokens
        self.total_spend_usd = self.total_tokens_used * PRICE_PER_MILLION_TOKENS / 1_000_000
        self.manifest.set_metadata("total_tokens_used", str(self.total_tokens_used))

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts with Voyage model and exponential backoff retry."""
        if self.dry_run:
            return [[0.0] * 1024 for _ in texts]

        max_retries = 5
        for attempt in range(max_retries):
            try:
                res = self.voyage_client.embed(
                    texts=texts,
                    model=self.embed_model,
                    input_type="document",
                )
                self.check_and_record_spend(res.total_tokens)
                return res.embeddings
            except Exception as e:
                logger.warning(f"Embedding attempt {attempt+1} failed: {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
        return []

    def embed_cases_contextual(self, cases_chunks: List[List[Dict[str, Any]]]) -> List[List[float]]:
        """Embed a list of cases (each case = list of chunk dicts) using voyage-context-4 with 25k windowing."""
        if self.dry_run:
            total_chunks = sum(len(c) for c in cases_chunks)
            return [[0.0] * 1024 for _ in range(total_chunks)]

        # Window cases exceeding 25k tokens into sub-documents
        MAX_CASE_DOC_TOKENS = 25000
        sub_docs: List[List[str]] = []
        for case in cases_chunks:
            curr_texts: List[str] = []
            curr_toks = 0
            for c in case:
                t = c["text"]
                tok = c.get("token_count", len(t.split()))
                if curr_toks + tok > MAX_CASE_DOC_TOKENS and curr_texts:
                    sub_docs.append(curr_texts)
                    curr_texts = [t]
                    curr_toks = tok
                else:
                    curr_texts.append(t)
                    curr_toks += tok
            if curr_texts:
                sub_docs.append(curr_texts)

        max_retries = 5
        for attempt in range(max_retries):
            try:
                res = self.voyage_client.contextualized_embed(
                    inputs=sub_docs,
                    model=self.embed_model,
                    input_type="document",
                )
                self.check_and_record_spend(res.total_tokens)
                flat_embeddings = []
                for doc_res in res.results:
                    flat_embeddings.extend(doc_res.embeddings)
                return flat_embeddings
            except Exception as e:
                logger.warning(f"Contextual embedding attempt {attempt+1} failed: {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
        return []

    def clean_stale_chunks(self, case_keys_to_chunks: Dict[str, List[Dict[str, Any]]]):
        """Delete lingering chunks from previously segmented versions of these cases."""
        if self.dry_run or not self.milvus_client or not case_keys_to_chunks:
            return

        active_ids = {c["chunk_id"] for chunks in case_keys_to_chunks.values() for c in chunks}
        case_keys_list = list(case_keys_to_chunks.keys())

        try:
            # Batch query existing chunks for all cases in this batch
            expr = f"case_key in {json.dumps(case_keys_list)}"
            existing = self.milvus_client.query(
                collection_name=self.collection_name,
                filter=expr,
                output_fields=["chunk_id"],
                limit=16384,
            )
            stale_ids = [row["chunk_id"] for row in existing if row["chunk_id"] not in active_ids]
            if stale_ids:
                logger.info(f"Removing {len(stale_ids)} stale chunks across batch")
                self.milvus_client.delete(
                    collection_name=self.collection_name,
                    pks=stale_ids,
                )
        except Exception as e:
            logger.warning(f"Stale chunk check failed: {e}")

    def upsert_case_batch(
        self,
        batch_cases: List[Tuple[str, List[Dict[str, Any]]]],
        batch_id: str,
    ):
        """Process and upsert a batch of whole cases."""
        # Check which chunks need embedding
        chunks_to_embed: List[Dict[str, Any]] = []
        cases_for_contextual: List[List[Dict[str, Any]]] = []

        all_batch_chunks: List[Dict[str, Any]] = []
        for ck, case_chunks in batch_cases:
            all_batch_chunks.extend(case_chunks)
            case_needs_embed = False
            for c in case_chunks:
                if not self.manifest.is_chunk_done(c["chunk_id"], c["chunk_hash"], self.embed_model):
                    chunks_to_embed.append(c)
                    case_needs_embed = True
            if case_needs_embed:
                cases_for_contextual.append(case_chunks)

        if not chunks_to_embed:
            # All chunks in this batch are already done!
            return

        # Check cache first for chunks needing embedding
        chunks_still_needing_api: List[Dict[str, Any]] = []
        for c in chunks_to_embed:
            cid = c["chunk_id"]
            if cid in self.embedding_cache:
                c["dense"] = self.embedding_cache[cid]
            else:
                chunks_still_needing_api.append(c)

        if chunks_still_needing_api:
            # Perform embeddings via Voyage API
            if self.embed_model == "voyage-context-4":
                # Group still needing API by case
                cases_for_api: List[List[Dict[str, Any]]] = []
                case_groups = OrderedDict()
                for c in chunks_still_needing_api:
                    ck = c["case_key"]
                    if ck not in case_groups:
                        case_groups[ck] = []
                    case_groups[ck].append(c)
                cases_for_api = list(case_groups.values())
                embeddings = self.embed_cases_contextual(cases_for_api)
                emb_idx = 0
                for case_chunks in cases_for_api:
                    for c in case_chunks:
                        c["dense"] = embeddings[emb_idx]
                        self.embedding_cache[c["chunk_id"]] = c["dense"]
                        emb_idx += 1
            else:
                texts = [c["text"] for c in chunks_still_needing_api]
                embeddings = []
                for i in range(0, len(texts), 100):
                    sub_texts = texts[i : i + 100]
                    embeddings.extend(self.embed_texts(sub_texts))
                for c, emb in zip(chunks_still_needing_api, embeddings):
                    c["dense"] = emb
                    self.embedding_cache[c["chunk_id"]] = emb

        # Clean stale chunks for cases being written
        case_map = {ck: chunks for ck, chunks in batch_cases}
        self.clean_stale_chunks(case_map)

        # Build payload for Zilliz upsert
        records_to_upsert = []
        now_iso = datetime.utcnow().isoformat()
        manifest_rows = []

        for c in chunks_to_embed:
            # Enforce max 64 items and max 64 chars per statute string as required by Zilliz schema
            safe_statutes = [
                str(s)[:64] for s in c.get("statutes", [])[:64]
                if s and isinstance(s, str)
            ]
            rec = {
                "chunk_id": str(c["chunk_id"])[:128],
                "case_key": str(c["case_key"])[:64],
                "text": str(c["text"])[:65535],
                "dense": c["dense"],
                "citation": str(c.get("citation", ""))[:128],
                "journal": str(c.get("journal", ""))[:32],
                "court_code": str(c.get("court_code", ""))[:32],
                "year": int(c.get("year", 0)),
                "court_level": int(c.get("court_level", 3)),
                "cited_by_count": int(c.get("cited_by_count", 0)),
                "section": str(c.get("section", "headnote"))[:32],
                "content_level": str(c.get("content_level", "full_judgment"))[:32],
                "domain": str(c.get("domain", "civil"))[:32],
                "statutes": safe_statutes,
                "chunk_hash": str(c.get("chunk_hash", ""))[:64],
                "embed_model": str(self.embed_model)[:64],
                "schema_version": "v1",
                "ingested_at": now_iso[:32],
            }
            records_to_upsert.append(rec)
            manifest_rows.append((
                c["chunk_id"],
                c["case_key"],
                c["chunk_hash"],
                self.embed_model,
                self.collection_name,
                batch_id,
            ))

        if not self.dry_run and self.milvus_client:
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    self.milvus_client.upsert(
                        collection_name=self.collection_name,
                        data=records_to_upsert,
                    )
                    break
                except Exception as e:
                    logger.warning(f"Zilliz upsert attempt {attempt+1} failed: {e}")
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(2 ** attempt)

        # Update manifest
        self.manifest.mark_chunks_done(manifest_rows)

    def run(
        self,
        chunks_file: str = r"I:\zilliz_work\chunks.jsonl",
        case_keys_file: Optional[str] = None,
        limit_cases: Optional[int] = None,
        case_keys_filter: Optional[Set[str]] = None,
        batch_size_cases: int = 50,
    ):
        """Run the ingestion pipeline over chunks file grouped by whole cases."""
        logger.info(f"Starting ingestion pipeline for collection '{self.collection_name}' with model '{self.embed_model}'")
        logger.info(f"Spending cap: ${self.spend_cap:.2f} | Dry run: {self.dry_run}")

        target_keys = None
        if case_keys_file and os.path.exists(case_keys_file):
            with open(case_keys_file, "r", encoding="utf-8") as f:
                target_keys = set(json.load(f))
            logger.info(f"Loaded {len(target_keys)} target case keys from {case_keys_file}")

        if case_keys_filter:
            target_keys = target_keys.intersection(case_keys_filter) if target_keys else case_keys_filter

        logger.info(f"Reading chunks from {chunks_file}...")
        # Stream chunks by whole case
        current_case_key = None
        current_case_chunks: List[Dict[str, Any]] = []
        cases_batch: List[Tuple[str, List[Dict[str, Any]]]] = []

        total_cases_processed = 0
        total_chunks_processed = 0
        batch_idx = 0
        start_time = time.time()

        with open(chunks_file, "r", encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                ck = c["case_key"]

                if target_keys and ck not in target_keys:
                    continue

                if ck != current_case_key:
                    if current_case_chunks:
                        cases_batch.append((current_case_key, current_case_chunks))
                        total_cases_processed += 1
                        total_chunks_processed += len(current_case_chunks)

                        if limit_cases and total_cases_processed >= limit_cases:
                            break

                        if len(cases_batch) >= batch_size_cases:
                            batch_idx += 1
                            batch_id = f"batch_{batch_idx:06d}"
                            self.upsert_case_batch(cases_batch, batch_id=batch_id)
                            elapsed = time.time() - start_time
                            logger.info(
                                f"Batch {batch_idx}: Processed {total_cases_processed} cases, "
                                f"{total_chunks_processed} chunks | Tokens: {self.total_tokens_used:,} | Spend: ${self.total_spend_usd:.4f} | Elapsed: {elapsed:.1f}s"
                            )
                            cases_batch = []

                    current_case_key = ck
                    current_case_chunks = [c]
                else:
                    current_case_chunks.append(c)

            # Flush final case and batch
            if current_case_chunks and (not limit_cases or total_cases_processed < limit_cases):
                cases_batch.append((current_case_key, current_case_chunks))
                total_cases_processed += 1
                total_chunks_processed += len(current_case_chunks)

            if cases_batch:
                batch_idx += 1
                batch_id = f"batch_{batch_idx:06d}"
                self.upsert_case_batch(cases_batch, batch_id=batch_id)
                elapsed = time.time() - start_time
                logger.info(
                    f"Final Batch {batch_idx}: Processed {total_cases_processed} cases, "
                    f"{total_chunks_processed} chunks | Tokens: {self.total_tokens_used:,} | Spend: ${self.total_spend_usd:.4f} | Elapsed: {elapsed:.1f}s"
                )

        if not self.dry_run and self.milvus_client:
            logger.info("Flushing collection to ensure persistent indexing...")
            self.milvus_client.flush(self.collection_name)

        logger.info(f"\nPipeline run completed!")
        logger.info(f"Total cases: {total_cases_processed} | Total chunks: {total_chunks_processed}")
        logger.info(f"Total tokens used: {self.total_tokens_used:,} | Total spend: ${self.total_spend_usd:.4f}")
        logger.info(f"Manifest 'done' count: {self.manifest.get_completed_count(self.collection_name, self.embed_model)}")


def main():
    parser = argparse.ArgumentParser(description="Embed and upsert Pakistani case law into Zilliz")
    parser.add_argument("--chunks", default=r"I:\zilliz_work\chunks.jsonl", help="Path to chunks.jsonl")
    parser.add_argument("--case-keys-file", default=None, help="JSON file containing list of case_keys")
    parser.add_argument("--collection", default="judgments_v1", help="Target collection name")
    parser.add_argument("--model", default="voyage-4-large", help="Embedding model name")
    parser.add_argument("--spend-cap", type=float, default=60.0, help="Spending cap in USD")
    parser.add_argument("--limit-cases", type=int, default=None, help="Limit number of cases")
    parser.add_argument("--case-keys", type=str, default=None, help="Comma-separated case keys")
    parser.add_argument("--batch-size", type=int, default=50, help="Cases per batch")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without API calls")

    args = parser.parse_args()

    filter_keys = set(args.case_keys.split(",")) if args.case_keys else None

    pipeline = EmbedUpsertPipeline(
        collection_name=args.collection,
        embed_model=args.model,
        spend_cap=args.spend_cap,
        dry_run=args.dry_run,
    )
    pipeline.run(
        chunks_file=args.chunks,
        case_keys_file=args.case_keys_file,
        limit_cases=args.limit_cases,
        case_keys_filter=filter_keys,
        batch_size_cases=args.batch_size,
    )


if __name__ == "__main__":
    main()
