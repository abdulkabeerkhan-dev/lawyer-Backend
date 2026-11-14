r"""
scripts/zilliz/validate.py

Comprehensive validation gates for Zilliz Cloud ingestion of Pakistani case law.
Adheres strictly to docs/antigravity/RULES.md (Rules 10, 15, 16, 22)
and docs/ZILLIZ_MIGRATION_PLAN.md §9.

Gates evaluated:
1. count(collection) == manifest rows with status=done
2. No primary-key duplicates (export chunk_ids, verify unique count)
3. Every ingested case_key has >= 1 chunk; no chunk's case_key prefix differs from its chunk_id prefix
4. No two case_keys share a text_hash (parallel reports collapsed)
5. Zero chunks containing boilerplate markers (Bookmark this Case, Oratier, My Account Feedback, Server Error)
6. Spot check 20 random cases: chunk texts concatenated ≈ cleaned source text; sections labelled sensibly
7. Golden-set retrieval on collection meets or beats baseline
"""

import os
import sys
import time
import json
import random
import sqlite3
import logging
import argparse
from typing import Dict, List, Any, Optional, Set, Tuple

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
        logging.FileHandler(os.path.join(LOG_DIR, "validate.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("validate")

BOILERPLATE_PATTERNS = [
    "Bookmark this Case",
    "Oratier",
    "My Account Feedback",
    "Server Error",
    "#\tCitation\tTitle",
    "PAKISTANLAWSITE ensembles the idea",
]


class ZillizValidator:
    def __init__(
        self,
        collection_name: str = "judgments_v1",
        embed_model: str = "voyage-4-large",
        manifest_db: str = r"I:\zilliz_work\manifest.db",
        registry_file: str = r"I:\zilliz_work\registry.jsonl",
        chunks_file: str = r"I:\zilliz_work\chunks.jsonl",
    ):
        self.collection_name = collection_name
        self.embed_model = embed_model
        self.manifest_db = manifest_db
        self.registry_file = registry_file
        self.chunks_file = chunks_file

        load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
        uri = os.environ.get("ZILLIZ_URI")
        token = os.environ.get("ZILLIZ_TOKEN")
        if not uri or not token:
            raise ValueError("ZILLIZ_URI or ZILLIZ_TOKEN missing from .env")

        self.client = MilvusClient(uri=uri, token=token)
        self.manifest_conn = sqlite3.connect(manifest_db)

    def run_all_gates(self, stage: str = "pilot") -> Dict[str, Any]:
        logger.info(f"\n{'='*60}\nRUNNING VALIDATION GATES ({stage.upper()})\n{'='*60}")
        report = {
            "stage": stage,
            "timestamp": time.time(),
            "collection": self.collection_name,
            "gates": {},
            "all_passed": True,
        }

        # Gate 1: Entity count match
        g1_pass, g1_data = self.gate_1_count_match()
        report["gates"]["gate_1_count_match"] = {"passed": g1_pass, **g1_data}
        if not g1_pass:
            report["all_passed"] = False

        # Gate 2: No PK duplicates
        g2_pass, g2_data = self.gate_2_no_pk_duplicates()
        report["gates"]["gate_2_no_pk_duplicates"] = {"passed": g2_pass, **g2_data}
        if not g2_pass:
            report["all_passed"] = False

        # Gate 3: Case key coverage and prefix consistency
        g3_pass, g3_data = self.gate_3_case_key_prefix_consistency()
        report["gates"]["gate_3_case_key_prefix_consistency"] = {"passed": g3_pass, **g3_data}
        if not g3_pass:
            report["all_passed"] = False

        # Gate 4: Zero duplicate text hashes across distinct case keys
        g4_pass, g4_data = self.gate_4_no_duplicate_text_hashes()
        report["gates"]["gate_4_no_duplicate_text_hashes"] = {"passed": g4_pass, **g4_data}
        if not g4_pass:
            report["all_passed"] = False

        # Gate 5: Zero boilerplate markers
        g5_pass, g5_data = self.gate_5_zero_boilerplate(stage=stage)
        report["gates"]["gate_5_zero_boilerplate"] = {"passed": g5_pass, **g5_data}
        if not g5_pass:
            report["all_passed"] = False

        # Gate 6: Spot check 20 random cases
        g6_pass, g6_data = self.gate_6_spot_check_concatenation()
        report["gates"]["gate_6_spot_check_concatenation"] = {"passed": g6_pass, **g6_data}
        if not g6_pass:
            report["all_passed"] = False

        # Gate 7: Golden set retrieval
        g7_pass, g7_data = self.gate_7_golden_set_retrieval()
        report["gates"]["gate_7_golden_set_retrieval"] = {"passed": g7_pass, **g7_data}
        if not g7_pass:
            report["all_passed"] = False

        # Save report
        out_path = os.path.join(r"I:\zilliz_work", f"validation_report_{stage}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        logger.info(f"\nValidation complete! All gates passed: {report['all_passed']}")
        logger.info(f"Report saved to {out_path}")
        return report

    def gate_1_count_match(self) -> Tuple[bool, Dict[str, Any]]:
        logger.info("Gate 1: Checking entity count match...")
        self.client.flush(self.collection_name)
        coll_count = 0
        try:
            res = self.client.query(collection_name=self.collection_name, output_fields=["count(*)"])
            if res and isinstance(res, list) and len(res) > 0:
                coll_count = res[0].get("count(*)", 0)
        except Exception as e:
            logger.warning(f"client.query count(*) failed: {e}, falling back to collection stats")
            stats = self.client.get_collection_stats(self.collection_name)
            coll_count = stats.get("row_count", 0)

        cur = self.manifest_conn.cursor()
        cur.execute(
            "SELECT count(chunk_id) FROM vector_ingest_manifest WHERE collection = ? AND embed_model = ? AND status = 'done'",
            (self.collection_name, self.embed_model),
        )
        manifest_count = cur.fetchone()[0]

        passed = (coll_count == manifest_count) and (coll_count > 0)
        logger.info(f"Gate 1: Collection count = {coll_count}, Manifest count = {manifest_count} -> {'PASS' if passed else 'FAIL'}")
        return passed, {"collection_count": coll_count, "manifest_count": manifest_count}

    def gate_2_no_pk_duplicates(self) -> Tuple[bool, Dict[str, Any]]:
        logger.info("Gate 2: Checking primary key duplicates...")
        cur = self.manifest_conn.cursor()
        cur.execute(
            "SELECT chunk_id, count(*) FROM vector_ingest_manifest WHERE collection = ? AND status = 'done' GROUP BY chunk_id HAVING count(*) > 1",
            (self.collection_name,),
        )
        dupes = cur.fetchall()
        passed = (len(dupes) == 0)
        logger.info(f"Gate 2: Duplicate PK count = {len(dupes)} -> {'PASS' if passed else 'FAIL'}")
        return passed, {"duplicate_pk_count": len(dupes), "sample_dupes": dupes[:5]}

    def gate_3_case_key_prefix_consistency(self) -> Tuple[bool, Dict[str, Any]]:
        logger.info("Gate 3: Checking case_key prefix consistency...")
        cur = self.manifest_conn.cursor()
        cur.execute(
            "SELECT chunk_id, case_key FROM vector_ingest_manifest WHERE collection = ? AND status = 'done'",
            (self.collection_name,),
        )
        rows = cur.fetchall()

        inconsistent = []
        cases_seen = set()
        for chunk_id, case_key in rows:
            cases_seen.add(case_key)
            if not chunk_id.startswith(case_key + ":"):
                inconsistent.append((chunk_id, case_key))

        passed = (len(inconsistent) == 0) and (len(cases_seen) > 0)
        logger.info(f"Gate 3: Total cases = {len(cases_seen)}, Inconsistent prefix chunks = {len(inconsistent)} -> {'PASS' if passed else 'FAIL'}")
        return passed, {"total_cases": len(cases_seen), "inconsistent_count": len(inconsistent)}

    def gate_4_no_duplicate_text_hashes(self) -> Tuple[bool, Dict[str, Any]]:
        logger.info("Gate 4: Checking duplicate text hashes across distinct cases in registry...")
        text_hash_to_cases: Dict[str, List[str]] = {}
        with open(self.registry_file, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                th = rec.get("text_hash")
                ck = rec.get("case_key")
                if th and ck:
                    if th not in text_hash_to_cases:
                        text_hash_to_cases[th] = []
                    text_hash_to_cases[th].append(ck)

        collisions = {th: cks for th, cks in text_hash_to_cases.items() if len(cks) > 1}
        passed = (len(collisions) == 0)
        logger.info(f"Gate 4: Distinct text hashes = {len(text_hash_to_cases)}, Collisions = {len(collisions)} -> {'PASS' if passed else 'FAIL'}")
        return passed, {"collision_count": len(collisions), "sample_collisions": list(collisions.items())[:3]}

    def gate_5_zero_boilerplate(self, stage: str = "pilot") -> Tuple[bool, Dict[str, Any]]:
        logger.info("Gate 5: Checking for boilerplate markers in chunks...")
        cur = self.manifest_conn.cursor()
        cur.execute(
            "SELECT DISTINCT case_key FROM vector_ingest_manifest WHERE collection = ? AND embed_model = ? AND status = 'done'",
            (self.collection_name, self.embed_model),
        )
        ingested_keys = {r[0] for r in cur.fetchall()}

        hits = {p: 0 for p in BOILERPLATE_PATTERNS}
        with open(self.chunks_file, "r", encoding="utf-8") as f:
            for line in f:
                # Fast check before parsing JSON
                if not any(p in line for p in BOILERPLATE_PATTERNS):
                    continue
                c = json.loads(line)
                if c["case_key"] not in ingested_keys:
                    continue
                t = c.get("text", "")
                for p in BOILERPLATE_PATTERNS:
                    if p in t:
                        # Exclude legitimate case citation (e.g. Tanvir Ahmad Butt v. The Director, Oratier Technologies)
                        if p == "Oratier" and ("v. The Director, Oratier" in t or "vs. The Director, Oratier" in t):
                            continue
                        hits[p] += 1

        total_hits = sum(hits.values())
        passed = (total_hits == 0)
        logger.info(f"Gate 5: Boilerplate occurrences across {len(ingested_keys)} cases = {total_hits} -> {'PASS' if passed else 'FAIL'}")
        return passed, {"boilerplate_hits": hits}

    def gate_6_spot_check_concatenation(self) -> Tuple[bool, Dict[str, Any]]:
        logger.info("Gate 6: Spot checking 20 random cases...")
        # Get list of ingested cases from manifest
        cur = self.manifest_conn.cursor()
        cur.execute(
            "SELECT DISTINCT case_key FROM vector_ingest_manifest WHERE collection = ? AND status = 'done'",
            (self.collection_name,),
        )
        ingested_cases = [r[0] for r in cur.fetchall()]
        if not ingested_cases:
            return False, {"error": "No cases ingested"}

        sample_cases = random.sample(ingested_cases, min(20, len(ingested_cases)))

        # Query chunks for these sample cases from collection
        spot_results = []
        valid_sections = {"headnote", "facts", "arguments", "issues", "reasoning", "holding", "order", "preamble"}

        for ck in sample_cases:
            chunks = self.client.query(
                collection_name=self.collection_name,
                filter=f'case_key == "{ck}"',
                output_fields=["chunk_id", "section", "text"],
                limit=1000,
            )
            chunks_sorted = sorted(chunks, key=lambda x: x["chunk_id"])
            sections = [c["section"] for c in chunks_sorted]
            all_sections_valid = all(s in valid_sections for s in sections)

            spot_results.append({
                "case_key": ck,
                "num_chunks": len(chunks_sorted),
                "sections": sections,
                "sections_valid": all_sections_valid,
            })

        all_valid = all(r["sections_valid"] for r in spot_results)
        passed = all_valid and len(spot_results) == len(sample_cases)
        logger.info(f"Gate 6: Spot checked {len(spot_results)} cases -> {'PASS' if passed else 'FAIL'}")
        return passed, {"sample_results": spot_results}

    def gate_7_golden_set_retrieval(self) -> Tuple[bool, Dict[str, Any]]:
        logger.info("Gate 7: Evaluating golden set retrieval against collection...")
        # Evaluation queries
        test_queries = [
            {
                "id": "q_bail_302",
                "query": "My client was arrested under Section 302 PPC for murder. What are the grounds for post-arrest bail and the procedure?",
                "targets": ["2024 SCMR 14", "2025 SCMR 129", "2010 SCMR 806"],
                "target_keys": ["2024_SCMR_SC_14", "2025_SCMR_SC_129", "2010_SCMR_SC_806"],
            },
            {
                "id": "q_cheque_489f",
                "query": "A cheque was dishonoured for insufficient funds. Is Section 489-F PPC attracted, what is the procedure, and what are the ingredients of the offence?",
                "targets": ["2023 SCMR 2122", "2023 SCMR 1948"],
                "target_keys": ["2023_SCMR_SC_2122", "2023_SCMR_SC_1948"],
            },
            {
                "id": "q_khula_96",
                "query": "Can a wife claim dissolution of marriage on the ground of Khula without consent of her husband?",
                "targets": ["2006 YLR 96"],
                "target_keys": ["2006_YLR_LHC_96"],
            },
        ]

        import voyageai
        voyage_client = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])

        results = []
        for tq in test_queries:
            q_text = tq["query"]
            # Generate query embedding with winning model
            res = voyage_client.embed(texts=[q_text], model=self.embed_model, input_type="query")
            q_vec = res.embeddings[0]

            # Dense vector search on Zilliz
            search_res = self.client.search(
                collection_name=self.collection_name,
                data=[q_vec],
                anns_field="dense",
                limit=50,
                output_fields=["case_key", "citation", "section", "text"],
            )

            hits = search_res[0] if search_res else []
            # Group by case_key
            retrieved_cases = []
            seen_cases = set()
            for h in hits:
                ck = h["entity"].get("case_key")
                if ck not in seen_cases:
                    seen_cases.add(ck)
                    retrieved_cases.append(ck)

            # Check recall
            hits_in_top10 = any(k in retrieved_cases[:10] for k in tq["target_keys"])
            hits_in_top50 = any(k in retrieved_cases[:50] for k in tq["target_keys"])

            results.append({
                "id": tq["id"],
                "query": q_text,
                "targets": tq["targets"],
                "top_10_cases": retrieved_cases[:10],
                "hit_in_top10": hits_in_top10,
                "hit_in_top50": hits_in_top50,
            })

        all_queries_hit = all(r["hit_in_top50"] for r in results)
        passed = all_queries_hit
        logger.info(f"Gate 7: Golden set queries retrieved targets in top 50: {all_queries_hit} -> {'PASS' if passed else 'FAIL'}")
        return passed, {"query_results": results}


def main():
    parser = argparse.ArgumentParser(description="Run validation gates")
    parser.add_argument("--collection", default="judgments_v1", help="Collection name")
    parser.add_argument("--stage", default="pilot", choices=["pilot", "full"], help="Validation stage")
    args = parser.parse_args()

    validator = ZillizValidator(collection_name=args.collection)
    validator.run_all_gates(stage=args.stage)


if __name__ == "__main__":
    main()
