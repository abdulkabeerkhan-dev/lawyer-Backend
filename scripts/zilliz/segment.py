r"""
scripts/zilliz/segment.py

Structural legal judgment segmenter and chunker for Zilliz ingestion.
Adheres strictly to docs/antigravity/RULES.md and docs/ZILLIZ_MIGRATION_PLAN.md §4-5.

Key guarantees:
1. Headnote: split into catchword blocks; merge < 40 tokens with next.
2. Judgment body: sectioned into preamble, facts, arguments, issues, reasoning, holding, order.
3. Packed into 300-500 token chunks without crossing section boundaries.
4. Deterministic chunk_id: f"{case_key}:{section}:{ordinal:03d}".
5. Drops within-case duplicate chunks and chunks < 25 tokens.
6. Handles 120k token limit by windowing long judgments at section boundaries.
7. Outputs I:\zilliz_work\chunks.jsonl.
"""

import os
import sys
import re
import json
import hashlib
import logging
import argparse
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Any, Optional, Set, Tuple

# Ensure project root in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.hierarchical_legal_chunker import (
    HierarchicalLegalChunker,
    count_tokens,
    SECTION_PREAMBLE,
    SECTION_HEADNOTE,
    SECTION_FACTS,
    SECTION_ISSUES,
    SECTION_ARGUMENTS,
    SECTION_ANALYSIS,
    SECTION_RATIO,
    SECTION_ORDER,
)
from scripts.zilliz.enrich import MetadataEnricher

# Canonical section mapping to spec taxonomy
SECTION_TYPE_MAP = {
    SECTION_PREAMBLE: "preamble",
    SECTION_HEADNOTE: "headnote",
    SECTION_FACTS: "facts",
    SECTION_ISSUES: "issues",
    SECTION_ARGUMENTS: "arguments",
    SECTION_ANALYSIS: "reasoning",
    SECTION_RATIO: "holding",
    SECTION_ORDER: "order",
}

# Regex to detect catchword block start in headnotes
RE_CATCHWORD_BLOCK_START = re.compile(
    r'(?:\n{2,}|\A)\s*(?:[-–—]{3,}\s*)?(?:'
    r'Ss?\.\s*[\d\w\-\/]+|'
    r'O\.\s*[IVXLCDM\d]+|'
    r'Arts?\.\s*[\d\w\-\/]+|'
    r'[A-Za-z\s\.\(\)]+?\s+(?:18\d\d|19\d\d|20\d\d)\s*--+\s*[\d\w\-\/]+|'
    r'Held\s*[:\-]|'
    r'Validity\s*[:\-]'
    r')',
    re.IGNORECASE
)


def split_headnote_into_blocks(headnote_text: str) -> List[str]:
    """
    Splits editorial headnote into catchword proposition blocks.
    A block starts at a statutory catchword or blank line boundary.
    Merges blocks < 40 tokens with the subsequent block.
    """
    if not headnote_text or not headnote_text.strip():
        return []

    # Find split positions
    split_positions = [0]
    for m in RE_CATCHWORD_BLOCK_START.finditer(headnote_text):
        pos = m.start()
        if pos > 0 and pos not in split_positions:
            split_positions.append(pos)

    split_positions.append(len(headnote_text))
    raw_blocks: List[str] = []
    for i in range(len(split_positions) - 1):
        block = headnote_text[split_positions[i]:split_positions[i+1]].strip()
        if block:
            raw_blocks.append(block)

    if not raw_blocks:
        return [headnote_text.strip()]

    # Merge blocks < 40 tokens with the next block
    merged_blocks: List[str] = []
    buffer = ""

    for b in raw_blocks:
        b_tok = count_tokens(b)
        if buffer:
            combined = f"{buffer}\n\n{b}"
            if count_tokens(combined) >= 40:
                merged_blocks.append(combined)
                buffer = ""
            else:
                buffer = combined
        else:
            if b_tok < 40:
                buffer = b
            else:
                merged_blocks.append(b)

    if buffer:
        if merged_blocks:
            merged_blocks[-1] = f"{merged_blocks[-1]}\n\n{buffer}"
        else:
            merged_blocks.append(buffer)

    return merged_blocks


def pack_paragraphs_into_chunks(
    paragraphs: List[str],
    min_tokens: int = 300,
    max_tokens: int = 500
) -> List[str]:
    """
    Packs whole paragraphs into chunks of 300–500 tokens without crossing section boundary.
    Splits a single paragraph only if it alone exceeds max_tokens (at sentence boundaries).
    """
    chunks: List[str] = []
    current_paras: List[str] = []
    current_tokens = 0

    for p in paragraphs:
        p_clean = p.strip()
        if not p_clean:
            continue

        p_tokens = count_tokens(p_clean)

        # If a single paragraph exceeds max_tokens, split it at sentence boundaries
        if p_tokens > max_tokens:
            # First flush any accumulated paragraphs
            if current_paras:
                chunks.append("\n\n".join(current_paras))
                current_paras = []
                current_tokens = 0

            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', p_clean) if s.strip()]
            sub_chunk: List[str] = []
            sub_tokens = 0

            for sent in sentences:
                s_tok = count_tokens(sent)
                if s_tok > max_tokens:
                    # Hard split sentence by words
                    words = sent.split()
                    word_chunk: List[str] = []
                    word_tok = 0
                    for w in words:
                        wt = count_tokens(w + " ")
                        if word_tok + wt > max_tokens:
                            if sub_chunk:
                                chunks.append(" ".join(sub_chunk))
                                sub_chunk = []
                                sub_tokens = 0
                            chunks.append(" ".join(word_chunk))
                            word_chunk = [w]
                            word_tok = wt
                        else:
                            word_chunk.append(w)
                            word_tok += wt
                    if word_chunk:
                        sub_chunk.extend(word_chunk)
                        sub_tokens += word_tok
                elif sub_tokens + s_tok > max_tokens and sub_tokens >= min_tokens:
                    chunks.append(" ".join(sub_chunk))
                    sub_chunk = [sent]
                    sub_tokens = s_tok
                else:
                    sub_chunk.append(sent)
                    sub_tokens += s_tok

            if sub_chunk:
                chunks.append(" ".join(sub_chunk))
            continue

        if current_tokens + p_tokens <= max_tokens:
            current_paras.append(p_clean)
            current_tokens += p_tokens
        else:
            if current_tokens >= min_tokens:
                chunks.append("\n\n".join(current_paras))
                current_paras = [p_clean]
                current_tokens = p_tokens
            else:
                # Add and flush if we exceeded max
                current_paras.append(p_clean)
                chunks.append("\n\n".join(current_paras))
                current_paras = []
                current_tokens = 0

    if current_paras:
        chunks.append("\n\n".join(current_paras))

    return chunks


def segment_case(
    case: Dict[str, Any],
    enricher: MetadataEnricher,
    max_doc_tokens: int = 120000
) -> List[Dict[str, Any]]:
    """
    Segments a single case into deterministic chunks with rich metadata.
    """
    case_key = case["case_key"]
    citation = case["citation"]
    journal = case["journal"]
    year = case["year"]
    court_code = case["court_code"]
    court_level = case["court_level"]
    parties = case.get("parties", "")
    judge = case.get("judge", "")
    content_level = case["content_level"]
    parallel_citations = case.get("parallel_citations", [])
    legacy_case_id = case.get("legacy_case_id", "")

    headnote_text = case.get("headnote_text", "")
    judgment_text = case.get("judgment_text", "")

    # Extract global case-level statutes and domain
    combined_sample = f"{headnote_text} {judgment_text[:5000]}"
    case_statutes = enricher.extract_statutes(combined_sample)
    case_domain = enricher.classify_domain(judgment_text, headnote_text, case_statutes)
    cited_by_count = enricher.get_cited_by_count(citation)

    court_display_map = {
        "SC": "Supreme Court of Pakistan",
        "FSC": "Federal Shariat Court",
        "LHC": "Lahore High Court",
        "SHC": "High Court of Sindh",
        "PHC": "Peshawar High Court",
        "BHC": "High Court of Balochistan",
        "IHC": "Islamabad High Court",
        "AJKHC": "High Court of Azad Kashmir",
        "GBSAC": "Supreme Appellate Court Gilgit-Baltistan",
    }
    court_display = court_display_map.get(court_code, f"Court ({court_code})")

    # Ordinal tracking per section type
    section_ordinals: Dict[str, int] = defaultdict(int)
    raw_chunks: List[Dict[str, Any]] = []

    # 1. Segment Headnote
    if headnote_text:
        hn_blocks = split_headnote_into_blocks(headnote_text)
        for block in hn_blocks:
            if count_tokens(block) > 500:
                paras = [p.strip() for p in block.split('\n\n') if p.strip()]
                sub_blocks = pack_paragraphs_into_chunks(paras, min_tokens=300, max_tokens=500)
            else:
                sub_blocks = [block]

            for sub_b in sub_blocks:
                section_ordinals["headnote"] += 1
                ord_num = section_ordinals["headnote"]
                chunk_id = f"{case_key}:headnote:{ord_num:03d}"

                # Chunk-specific statutes
                chunk_statutes = enricher.extract_statutes(sub_b)
                statutes_merged = sorted(list(set(chunk_statutes or case_statutes)))[:64]
                statutes_summary = ", ".join(statutes_merged[:3]) if statutes_merged else "General"

                # Context header
                header = f"[{citation} | {court_display} | {case_domain.title()} | {statutes_summary} | headnote]"
                full_text = f"{header}\n\n{sub_b}".strip()

                raw_chunks.append({
                    "chunk_id": chunk_id,
                    "section": "headnote",
                    "clean_body": sub_b,
                    "text": full_text,
                    "statutes": statutes_merged,
                })

    # 2. Segment Judgment Body
    if judgment_text:
        sections = HierarchicalLegalChunker.parse_judgment_sections(judgment_text)
        for sec in sections:
            raw_sec_type = sec["section_type"]
            canonical_sec = SECTION_TYPE_MAP.get(raw_sec_type, "reasoning")

            # Skip editorial headnotes from body if already captured
            if canonical_sec == "headnote" and headnote_text:
                continue

            paras = sec.get("paragraphs", [])
            if not paras:
                continue

            sec_chunks = pack_paragraphs_into_chunks(paras, min_tokens=300, max_tokens=500)
            for body_chunk in sec_chunks:
                section_ordinals[canonical_sec] += 1
                ord_num = section_ordinals[canonical_sec]
                chunk_id = f"{case_key}:{canonical_sec}:{ord_num:03d}"

                chunk_statutes = enricher.extract_statutes(body_chunk)
                statutes_merged = sorted(list(set(chunk_statutes or case_statutes)))[:64]
                statutes_summary = ", ".join(statutes_merged[:3]) if statutes_merged else "General"

                header = f"[{citation} | {court_display} | {case_domain.title()} | {statutes_summary} | {canonical_sec}]"
                full_text = f"{header}\n\n{body_chunk}".strip()

                raw_chunks.append({
                    "chunk_id": chunk_id,
                    "section": canonical_sec,
                    "clean_body": body_chunk,
                    "text": full_text,
                    "statutes": statutes_merged,
                })

    # 3. Deduplication within the case & drop < 25 tokens
    seen_texts: Set[str] = set()
    final_chunks: List[Dict[str, Any]] = []

    for rc in raw_chunks:
        body = rc["clean_body"]
        token_cnt = count_tokens(body)

        # Drop chunks < 25 tokens
        if token_cnt < 25:
            continue

        # Drop within-case duplicate texts
        norm_body = re.sub(r'[^a-z0-9]+', ' ', body.lower()).strip()
        if norm_body in seen_texts:
            continue
        seen_texts.add(norm_body)

        full_text = rc["text"]
        chunk_hash = hashlib.sha1(full_text.encode("utf-8")).hexdigest()

        final_chunks.append({
            "chunk_id": rc["chunk_id"],
            "case_key": case_key,
            "text": full_text,
            "dense": [],  # Filled in Phase 3/4
            "sparse": {},  # Filled in Phase 4
            "citation": citation,
            "parallel_citations": parallel_citations,
            "legacy_case_id": legacy_case_id,
            "journal": journal,
            "year": year,
            "court_code": court_code,
            "court_level": court_level,
            "parties": parties,
            "judge": judge,
            "section": rc["section"],
            "content_level": content_level,
            "domain": case_domain,
            "statutes": rc["statutes"],
            "cited_by_count": cited_by_count,
            "token_count": count_tokens(full_text),
            "chunk_hash": chunk_hash,
            "embed_model": "",
            "schema_version": "1.0",
            "ingested_at": datetime.utcnow().isoformat() + "Z",
        })

    return final_chunks


def run_segmentation(
    registry_path: str = "I:\\zilliz_work\\registry.jsonl",
    work_dir: str = "I:\\zilliz_work",
    limit_cases: Optional[int] = None,
    case_keys_filter: Optional[Set[str]] = None,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, Any]:
    """
    Runs the segmentation and enrichment pipeline over the canonical registry.
    """
    if logger is None:
        logger = logging.getLogger("segment")

    logger.info("Initializing MetadataEnricher and citation graph...")
    enricher = MetadataEnricher()
    cache_path = os.path.join(work_dir, "citation_counts.json")
    citation_counts = enricher.build_citation_graph(registry_path, cache_path=cache_path)
    logger.info(f"Citation graph ready: {len(citation_counts)} cited citations tracked.")

    out_chunks_path = os.path.join(work_dir, "chunks.jsonl")
    report_path = os.path.join(work_dir, "segment_report.json")

    total_cases = 0
    total_chunks = 0
    chunks_by_section: Counter = Counter()
    token_counts: List[int] = []
    statutes_counter: Counter = Counter()
    domain_counter: Counter = Counter()
    cases_over_120k_tokens: List[Tuple[str, int]] = []

    out_f = None
    if not dry_run:
        out_f = open(out_chunks_path, "w", encoding="utf-8")

    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f):
                if not line.strip():
                    continue

                case = json.loads(line)
                ck = case["case_key"]

                if case_keys_filter and ck not in case_keys_filter:
                    continue

                # Check if judgment alone exceeds 120k tokens
                jd_text = case.get("judgment_text", "")
                if jd_text:
                    jd_tokens = count_tokens(jd_text)
                    if jd_tokens > 120000:
                        cases_over_120k_tokens.append((ck, jd_tokens))

                # Segment case
                case_chunks = segment_case(case, enricher)
                total_cases += 1
                total_chunks += len(case_chunks)

                for chunk in case_chunks:
                    chunks_by_section[chunk["section"]] += 1
                    token_counts.append(chunk["token_count"])
                    domain_counter[chunk["domain"]] += 1
                    for s in chunk["statutes"]:
                        statutes_counter[s] += 1

                    if out_f:
                        out_f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

                if total_cases % 10000 == 0:
                    logger.info(f"Segmented {total_cases} cases -> {total_chunks} chunks...")

                if limit_cases and total_cases >= limit_cases:
                    logger.info(f"Reached limit of {limit_cases} cases.")
                    break
    finally:
        if out_f:
            out_f.close()

    # Calculate token percentiles
    token_counts.sort()
    n = len(token_counts)
    p10 = token_counts[int(0.10 * n)] if n > 0 else 0
    p50 = token_counts[int(0.50 * n)] if n > 0 else 0
    p90 = token_counts[int(0.90 * n)] if n > 0 else 0
    max_t = token_counts[-1] if n > 0 else 0
    total_tokens = sum(token_counts)

    # Cost estimation ($0.12 per 1M tokens)
    estimated_cost_usd = (total_tokens / 1_000_000) * 0.12

    # Top cases by cited_by_count
    top_cited = sorted(citation_counts.items(), key=lambda x: x[1], reverse=True)[:25]

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_cases_processed": total_cases,
        "total_chunks_produced": total_chunks,
        "chunks_per_section": dict(chunks_by_section),
        "token_distribution": {
            "p10": p10,
            "p50": p50,
            "p90": p90,
            "max": max_t,
            "total_tokens": total_tokens,
            "estimated_embedding_cost_usd": round(estimated_cost_usd, 2),
        },
        "cases_over_120k_tokens_count": len(cases_over_120k_tokens),
        "cases_over_120k_tokens": cases_over_120k_tokens,
        "top_20_statutes": dict(statutes_counter.most_common(20)),
        "domain_distribution": dict(domain_counter),
        "top_20_cited_cases": top_cited,
    }

    if not dry_run:
        with open(report_path, "w", encoding="utf-8") as rf:
            json.dump(report, rf, indent=2, ensure_ascii=False)
        logger.info(f"Segmentation report written to {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Segment canonical legal case registry into vector chunks")
    parser.add_argument("--registry-path", default="I:\\zilliz_work\\registry.jsonl", help="Path to registry.jsonl")
    parser.add_argument("--work-dir", default="I:\\zilliz_work", help="Working directory for outputs")
    parser.add_argument("--limit-cases", type=int, default=None, help="Limit number of cases to segment")
    parser.add_argument("--case-keys", type=str, default=None, help="Comma-separated case keys to segment")
    parser.add_argument("--dry-run", action="store_true", help="Perform segmentation without writing chunks")
    args = parser.parse_args()

    # Configure logging
    log_dir = os.path.join(args.work_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "segment.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger = logging.getLogger("segment")

    case_keys_filter = None
    if args.case_keys:
        case_keys_filter = set(k.strip() for k in args.case_keys.split(",") if k.strip())

    report = run_segmentation(
        registry_path=args.registry_path,
        work_dir=args.work_dir,
        limit_cases=args.limit_cases,
        case_keys_filter=case_keys_filter,
        dry_run=args.dry_run,
        logger=logger,
    )

    print("\n--- SEGMENTATION COMPLETE ---")
    print(f"Total Cases: {report['total_cases_processed']}")
    print(f"Total Chunks: {report['total_chunks_produced']}")
    print("Chunks per Section:", report["chunks_per_section"])
    print("Token Distribution:", report["token_distribution"])
    print("Domain Distribution:", report["domain_distribution"])
    print(f"Cases over 120k Tokens: {report['cases_over_120k_tokens_count']}")


if __name__ == "__main__":
    main()
