r"""
scripts/zilliz/bakeoff.py

Phase 3: Embedding bake-off for Pakistani case law retrieval.
Evaluates voyage-law-2, voyage-4-large, and voyage-context-4.
Adheres strictly to docs/antigravity/RULES.md (Rules 11, 16, 17, 19, 22)
and docs/ZILLIZ_MIGRATION_PLAN.md §6.

Model specs & pricing (from docs.voyageai.com & docs/voyage_pricing_20261003.html):
- voyage-law-2: 1024-d, 16k context, max 128 items / 120k tokens per req, $0.12/M tokens
- voyage-4-large: 1024-d, 32k context, max 128 items / 120k tokens per req, $0.12/M tokens
- voyage-context-4: 1024-d, 120k context, max 120k tokens per req, $0.12/M tokens

Spending cap: <= $5.00 total for the bake-off.
"""

import os
import sys
import time
import json
import logging
import argparse
from typing import Dict, List, Any, Optional, Tuple, Set
import numpy as np

# Ensure project root in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv

# Set up logging to console and file
LOG_DIR = r"I:\zilliz_work\logs"
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, f"bakeoff_{int(time.time())}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger("bakeoff")

SPEND_CAP_USD = 5.00
PRICE_PER_MILLION_TOKENS = 0.12

EVAL_QUERIES = [
    {
        "id": "golden_q1",
        "query": "Can a wife claim dissolution of marriage on the ground of Khula without consent of her husband?",
        "expected_citations": ["2006 YLR 96"],
        "expected_case_keys": ["2006_YLR_LHC_96"],
        "is_canary": False,
    },
    {
        "id": "golden_q2",
        "query": "Can a Family Court grant khula without the husband's consent, and what evidentiary standard applies?",
        "expected_citations": ["2006 YLR 2204"],
        "expected_case_keys": ["2006_YLR_LHC_2204"],
        "is_canary": False,
    },
    {
        "id": "golden_q3_canary",
        "query": "Can a landlord claim eviction of a commercial shop under Section 9 CPC in Lahore for non-payment of rent?",
        "expected_citations": [],
        "expected_case_keys": [],
        "is_canary": True,
        "notes": "Canary query: Section 9 CPC does not govern PRPA commercial tenancy. Should have low confidence / no false match.",
    },
    {
        "id": "golden_q4",
        "query": "Can an accused charged under Section 302 PPC be granted bail on the plea of self defence or private defence?",
        "expected_citations": ["2008 YLR 1137"],
        "expected_case_keys": ["2008_YLR_LHC_1137"],
        "is_canary": False,
    },
    {
        "id": "benchmark_302_bail",
        "query": "My client was arrested under Section 302 PPC for murder. What are the grounds for post-arrest bail and the procedure?",
        "expected_citations": ["2024 SCMR 14", "2025 SCMR 129", "2010 SCMR 806"],
        "expected_case_keys": ["2024_SCMR_SC_14", "2025_SCMR_SC_129", "2010_SCMR_SC_806"],
        "is_canary": False,
    },
    {
        "id": "benchmark_489f_cheque",
        "query": "A cheque was dishonoured for insufficient funds. Is Section 489-F PPC attracted, what is the procedure, and what are the ingredients of the offence?",
        "expected_citations": ["2023 SCMR 2122", "2023 SCMR 1948"],
        "expected_case_keys": ["2023_SCMR_SC_2122", "2023_SCMR_SC_1948"],
        "is_canary": False,
    },
]


def compute_cosine_similarity(query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between 1D query vector and 2D doc vectors."""
    q_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    doc_norms = np.linalg.norm(doc_vecs, axis=1, keepdims=True) + 1e-10
    normalized_docs = doc_vecs / doc_norms
    return np.dot(normalized_docs, q_norm)


def aggregate_chunk_scores_to_cases(
    chunk_ids: List[str], case_keys: List[str], scores: np.ndarray
) -> List[Tuple[str, float, str]]:
    """
    Aggregate chunk level similarity scores to case level.
    Returns list of (case_key, max_score, top_chunk_id) sorted descending by max_score.
    """
    case_scores: Dict[str, Tuple[float, str]] = {}
    for cid, ckey, score in zip(chunk_ids, case_keys, scores):
        s = float(score)
        if ckey not in case_scores or s > case_scores[ckey][0]:
            case_scores[ckey] = (s, cid)

    sorted_cases = sorted(
        [(ck, val[0], val[1]) for ck, val in case_scores.items()],
        key=lambda x: x[1],
        reverse=True,
    )
    return sorted_cases


def calculate_retrieval_metrics(
    ranked_cases: List[Tuple[str, float, str]], expected_keys: List[str]
) -> Dict[str, Any]:
    """Calculate Recall@10, Recall@50, and MRR for a list of target case keys."""
    if not expected_keys:
        return {
            "recall@10": None,
            "recall@50": None,
            "mrr": None,
            "first_rank": None,
            "ranks": {},
        }

    ranks: Dict[str, int] = {}
    ranked_keys = [c[0] for c in ranked_cases]

    for target in expected_keys:
        try:
            rank = ranked_keys.index(target) + 1
            ranks[target] = rank
        except ValueError:
            ranks[target] = 999999

    min_rank = min(ranks.values()) if ranks else 999999
    first_rank = min_rank if min_rank <= len(ranked_cases) else None

    # Recall: proportion of expected targets found
    hits_10 = sum(1 for r in ranks.values() if r <= 10)
    hits_50 = sum(1 for r in ranks.values() if r <= 50)

    recall_10 = hits_10 / len(expected_keys)
    recall_50 = hits_50 / len(expected_keys)
    mrr = (1.0 / first_rank) if first_rank is not None else 0.0

    return {
        "recall@10": recall_10,
        "recall@50": recall_50,
        "mrr": mrr,
        "first_rank": first_rank,
        "ranks": ranks,
    }


class BakeoffRunner:
    def __init__(self, output_dir: str = r"I:\zilliz_work\bakeoff"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.total_tokens_used = 0
        self.total_spend_usd = 0.0

        load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
        api_key = os.environ.get("VOYAGE_API_KEY")
        if not api_key:
            raise ValueError("VOYAGE_API_KEY not found in .env")

        import voyageai
        self.client = voyageai.Client(api_key=api_key)

    def check_spend(self, additional_tokens: int):
        est_cost = (self.total_tokens_used + additional_tokens) * PRICE_PER_MILLION_TOKENS / 1_000_000
        if est_cost > SPEND_CAP_USD:
            raise RuntimeError(
                f"Spending cap exceeded! Total spend would reach ${est_cost:.4f} > ${SPEND_CAP_USD:.2f}"
            )

    def record_usage(self, tokens: int):
        self.total_tokens_used += tokens
        self.total_spend_usd = self.total_tokens_used * PRICE_PER_MILLION_TOKENS / 1_000_000
        logger.info(
            f"Tokens used: {tokens:,} | Cumulative: {self.total_tokens_used:,} tokens | Spend: ${self.total_spend_usd:.4f}"
        )

    def embed_chunks_standard(
        self, chunks: List[Dict[str, Any]], model: str, dry_run: bool = False
    ) -> Tuple[np.ndarray, List[str], List[str]]:
        """Embed chunks using voyage-law-2 or voyage-4-large with caching."""
        model_slug = model.replace("-", "_")
        cache_dir = os.path.join(self.output_dir, model_slug)
        os.makedirs(cache_dir, exist_ok=True)
        npy_path = os.path.join(cache_dir, "embeddings.npy")
        manifest_path = os.path.join(cache_dir, "manifest.json")

        chunk_ids = [c["chunk_id"] for c in chunks]
        case_keys = [c["case_key"] for c in chunks]

        if os.path.exists(npy_path) and os.path.exists(manifest_path):
            logger.info(f"Loading cached embeddings for {model} from {cache_dir}")
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            cached_ids = manifest.get("chunk_ids", [])
            if cached_ids == chunk_ids:
                embeddings = np.load(npy_path)
                logger.info(f"Successfully loaded {len(embeddings)} embeddings from cache.")
                return embeddings, chunk_ids, case_keys

        if dry_run:
            logger.info(f"[DRY-RUN] Would embed {len(chunks)} chunks with {model}")
            return np.zeros((len(chunks), 1024), dtype=np.float32), chunk_ids, case_keys

        embeddings_list: List[List[float]] = []
        batch_size = 100
        total_chunks = len(chunks)

        logger.info(f"Embedding {total_chunks} chunks with {model}...")

        for i in range(0, total_chunks, batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c["text"] for c in batch]

            # Retry with exponential backoff on transient errors
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    res = self.client.embed(texts=texts, model=model, input_type="document")
                    embeddings_list.extend(res.embeddings)
                    self.record_usage(res.total_tokens)
                    break
                except Exception as e:
                    logger.warning(f"Batch {i//batch_size} attempt {attempt+1} failed: {e}")
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(2 ** attempt)

            if (i // batch_size) % 10 == 0 or i + batch_size >= total_chunks:
                logger.info(f"Progress: {len(embeddings_list)}/{total_chunks} chunks embedded ({model})")

        embeddings = np.array(embeddings_list, dtype=np.float32)
        np.save(npy_path, embeddings)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump({
                "model": model,
                "chunk_ids": chunk_ids,
                "case_keys": case_keys,
                "created_at": time.time(),
            }, f, indent=2)

        return embeddings, chunk_ids, case_keys

    def embed_chunks_contextual(
        self, chunks: List[Dict[str, Any]], model: str = "voyage-context-4", dry_run: bool = False
    ) -> Tuple[np.ndarray, List[str], List[str]]:
        """Embed chunks using voyage-context-4 (grouped by case) with caching."""
        model_slug = model.replace("-", "_")
        cache_dir = os.path.join(self.output_dir, model_slug)
        os.makedirs(cache_dir, exist_ok=True)
        npy_path = os.path.join(cache_dir, "embeddings.npy")
        manifest_path = os.path.join(cache_dir, "manifest.json")

        chunk_ids = [c["chunk_id"] for c in chunks]
        case_keys = [c["case_key"] for c in chunks]

        if os.path.exists(npy_path) and os.path.exists(manifest_path):
            logger.info(f"Loading cached embeddings for {model} from {cache_dir}")
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            cached_ids = manifest.get("chunk_ids", [])
            if cached_ids == chunk_ids:
                embeddings = np.load(npy_path)
                logger.info(f"Successfully loaded {len(embeddings)} embeddings from cache.")
                return embeddings, chunk_ids, case_keys

        if dry_run:
            logger.info(f"[DRY-RUN] Would embed {len(chunks)} chunks with {model}")
            return np.zeros((len(chunks), 1024), dtype=np.float32), chunk_ids, case_keys

        # Group chunks by case_key and window at <= 25k tokens to respect Voyage 32k context limit
        from collections import OrderedDict
        case_to_chunks = OrderedDict()
        for c in chunks:
            ck = c["case_key"]
            if ck not in case_to_chunks:
                case_to_chunks[ck] = []
            case_to_chunks[ck].append(c)

        logger.info(f"Embedding {len(chunks)} chunks across {len(case_to_chunks)} cases with {model}...")

        chunk_id_to_emb: Dict[str, List[float]] = {}
        cases_list = list(case_to_chunks.items())
        total_cases = len(cases_list)

        # Window cases exceeding 25,000 tokens into sub-documents
        MAX_CASE_DOC_TOKENS = 25000
        case_docs: List[Tuple[List[str], List[str]]] = []

        for ck, case_chunks in cases_list:
            curr_texts: List[str] = []
            curr_cids: List[str] = []
            curr_toks = 0

            for c in case_chunks:
                t = c["text"]
                tok = c.get("token_count", len(t.split()))
                if curr_toks + tok > MAX_CASE_DOC_TOKENS and curr_texts:
                    case_docs.append((curr_texts, curr_cids))
                    curr_texts = [t]
                    curr_cids = [c["chunk_id"]]
                    curr_toks = tok
                else:
                    curr_texts.append(t)
                    curr_cids.append(c["chunk_id"])
                    curr_toks += tok

            if curr_texts:
                case_docs.append((curr_texts, curr_cids))

        logger.info(f"Prepared {len(case_docs)} contextual sub-documents across {total_cases} cases.")

        batch_docs: List[List[str]] = []
        batch_case_chunk_ids: List[List[str]] = []
        curr_batch_tokens = 0
        MAX_BATCH_TOKENS = 28000
        total_sub_docs = len(case_docs)

        for i, (doc_texts, doc_chunk_ids) in enumerate(case_docs):
            doc_tokens = sum(len(t.split()) for t in doc_texts)

            batch_docs.append(doc_texts)
            batch_case_chunk_ids.append(doc_chunk_ids)
            curr_batch_tokens += doc_tokens

            # Send batch if reaching token limit or at the end
            if curr_batch_tokens >= MAX_BATCH_TOKENS or i == total_sub_docs - 1 or len(batch_docs) >= 30:
                max_retries = 5
                for attempt in range(max_retries):
                    try:
                        res = self.client.contextualized_embed(
                            inputs=batch_docs, model=model, input_type="document"
                        )
                        for doc_idx, doc_res in enumerate(res.results):
                            doc_cids = batch_case_chunk_ids[doc_idx]
                            for cid, emb in zip(doc_cids, doc_res.embeddings):
                                chunk_id_to_emb[cid] = emb

                        self.record_usage(res.total_tokens)
                        break
                    except Exception as e:
                        logger.warning(f"Contextual batch at doc {i} attempt {attempt+1} failed: {e}")
                        if attempt == max_retries - 1:
                            raise
                        time.sleep(2 ** attempt)

                batch_docs = []
                batch_case_chunk_ids = []
                curr_batch_tokens = 0

                if (i + 1) % 100 == 0 or i == total_sub_docs - 1:
                    logger.info(f"Progress: {i+1}/{total_sub_docs} sub-docs ({len(chunk_id_to_emb)}/{len(chunks)} chunks) embedded ({model})")

        # Assemble embeddings in original chunk order
        embeddings_list = [chunk_id_to_emb[cid] for cid in chunk_ids]
        embeddings = np.array(embeddings_list, dtype=np.float32)

        np.save(npy_path, embeddings)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump({
                "model": model,
                "chunk_ids": chunk_ids,
                "case_keys": case_keys,
                "created_at": time.time(),
            }, f, indent=2)

        return embeddings, chunk_ids, case_keys

    def embed_query(self, query: str, model: str) -> np.ndarray:
        """Embed a single query with input_type='query'."""
        if model == "voyage-context-4":
            res = self.client.contextualized_embed(inputs=[query], model=model, input_type="query")
            emb = res.results[0].embeddings[0]
            self.record_usage(res.total_tokens)
        else:
            res = self.client.embed(texts=[query], model=model, input_type="query")
            emb = res.embeddings[0]
            self.record_usage(res.total_tokens)
        return np.array(emb, dtype=np.float32)

    def evaluate_model(
        self,
        model: str,
        chunks: List[Dict[str, Any]],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Run embedding and evaluation for a single model."""
        start_tokens = self.total_tokens_used

        if model == "voyage-context-4":
            embeddings, chunk_ids, case_keys = self.embed_chunks_contextual(chunks, model=model, dry_run=dry_run)
        else:
            embeddings, chunk_ids, case_keys = self.embed_chunks_standard(chunks, model=model, dry_run=dry_run)

        # Mapping for display lookup
        case_meta = {}
        for c in chunks:
            ck = c["case_key"]
            if ck not in case_meta:
                case_meta[ck] = {
                    "citation": c.get("citation", ""),
                    "court_code": c.get("court_code", ""),
                    "year": c.get("year", ""),
                    "parties": c.get("parties", ""),
                }

        model_results = []
        top_cases_benchmark = {}

        for q in EVAL_QUERIES:
            qid = q["id"]
            query_text = q["query"]
            expected_keys = q["expected_case_keys"]

            if dry_run:
                q_vec = np.zeros(1024, dtype=np.float32)
            else:
                q_vec = self.embed_query(query_text, model=model)

            scores = compute_cosine_similarity(q_vec, embeddings)
            ranked_cases = aggregate_chunk_scores_to_cases(chunk_ids, case_keys, scores)

            metrics = calculate_retrieval_metrics(ranked_cases, expected_keys)

            # Store top 10 cases for reporting
            top_10 = []
            for rank, (ck, score, cid) in enumerate(ranked_cases[:10], start=1):
                meta = case_meta.get(ck, {})
                top_10.append({
                    "rank": rank,
                    "case_key": ck,
                    "citation": meta.get("citation", ""),
                    "score": round(score, 4),
                    "top_chunk_id": cid,
                })

            if qid in ["benchmark_302_bail", "benchmark_489f_cheque"]:
                top_cases_benchmark[qid] = top_10

            model_results.append({
                "id": qid,
                "query": query_text,
                "expected_citations": q["expected_citations"],
                "expected_case_keys": expected_keys,
                "is_canary": q["is_canary"],
                "metrics": metrics,
                "top_10": top_10,
            })

        # Calculate macro averages across non-canary queries
        eval_queries_res = [r for r in model_results if not r["is_canary"]]
        avg_recall_10 = np.mean([r["metrics"]["recall@10"] for r in eval_queries_res])
        avg_recall_50 = np.mean([r["metrics"]["recall@50"] for r in eval_queries_res])
        avg_mrr = np.mean([r["metrics"]["mrr"] for r in eval_queries_res])

        tokens_spent_for_model = self.total_tokens_used - start_tokens
        cost_spent_for_model = tokens_spent_for_model * PRICE_PER_MILLION_TOKENS / 1_000_000

        return {
            "model": model,
            "tokens_spent": tokens_spent_for_model,
            "cost_spent_usd": round(cost_spent_for_model, 4),
            "macro_avg": {
                "recall@10": round(float(avg_recall_10), 4),
                "recall@50": round(float(avg_recall_50), 4),
                "mrr": round(float(avg_mrr), 4),
            },
            "query_results": model_results,
            "top_cases_benchmark": top_cases_benchmark,
        }


def main():
    parser = argparse.ArgumentParser(description="Run embedding bake-off (Phase 3)")
    parser.add_argument("--sample-chunks", default=r"I:\zilliz_work\sample_2000_chunks.jsonl", help="Sample chunks file")
    parser.add_argument("--models", default="voyage-law-2,voyage-4-large,voyage-context-4", help="Comma-separated models")
    parser.add_argument("--output-dir", default=r"I:\zilliz_work\bakeoff", help="Bakeoff output dir")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without calling Voyage API")
    parser.add_argument("--limit-cases", type=int, default=None, help="Limit number of cases")
    parser.add_argument("--case-keys", type=str, default=None, help="Filter to specific case keys")

    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    logger.info(f"Starting Phase 3 Bake-off for models: {models}")
    logger.info(f"Loading sample chunks from {args.sample_chunks}...")

    chunks = []
    case_key_filter = set(args.case_keys.split(",")) if args.case_keys else None

    with open(args.sample_chunks, "r", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            if case_key_filter and c["case_key"] not in case_key_filter:
                continue
            chunks.append(c)

    if args.limit_cases:
        unique_keys = []
        filtered_chunks = []
        for c in chunks:
            ck = c["case_key"]
            if ck not in unique_keys:
                if len(unique_keys) >= args.limit_cases:
                    continue
                unique_keys.append(ck)
            filtered_chunks.append(c)
        chunks = filtered_chunks

    logger.info(f"Total chunks loaded for bake-off: {len(chunks)}")

    runner = BakeoffRunner(output_dir=args.output_dir)

    all_model_reports = []
    for model in models:
        logger.info(f"\n{'='*50}\nEVALUATING MODEL: {model}\n{'='*50}")
        rep = runner.evaluate_model(model, chunks, dry_run=args.dry_run)
        all_model_reports.append(rep)

    # Save comprehensive report
    report_path = os.path.join(args.output_dir, "bakeoff_report.json")
    summary = {
        "timestamp": time.time(),
        "chunks_evaluated": len(chunks),
        "total_tokens_used": runner.total_tokens_used,
        "total_spend_usd": round(runner.total_spend_usd, 4),
        "models": all_model_reports,
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"\nBake-off complete! Report saved to {report_path}")
    logger.info(f"Total tokens: {runner.total_tokens_used:,} | Total spend: ${runner.total_spend_usd:.4f}")


if __name__ == "__main__":
    main()
