"""
core/hierarchical_legal_chunker.py

Structure-Aware Hierarchical Legal Judgment Chunker for Pakistani Jurisprudence.
Parses superior court judgments into canonical structural sections:
- Preamble & Coram (bench, parties, counsel appearances)
- Editorial Headnote / Digest (reporter catchwords, statutory anchors, held summaries)
- Procedural Facts & Factual Genesis (background, FIR, trial history)
- Framed Issues & Questions of Law (points for determination)
- Counsel Submissions & Arguments (petitioner & respondent contentions)
- Judicial Analysis & Precedent Discussion (court's legal evaluation)
- Ratio Decidendi & Judicial Holding (binding legal rule, test, or principle)
- Operative Order & Disposition (final relief, decree, dismissal, or bail order)

Enforces:
1. Section frontier containment (zero overlap bleed between argument and holding).
2. Paragraph-boundary indivisibility (preserves atomic legal paragraphs).
3. Rich hierarchical metadata tagging for Pinecone dense indexing & cross-encoder reranking.
"""

import re
import math
import hashlib
from typing import Dict, List, Any, Optional, Set, Tuple


# =====================================================================
# Canonical Section Taxonomy
# =====================================================================

SECTION_PREAMBLE = "preamble"
SECTION_HEADNOTE = "headnote"
SECTION_FACTS = "facts_and_procedural_history"
SECTION_ISSUES = "issues_framed"
SECTION_ARGUMENTS = "counsel_arguments"
SECTION_ANALYSIS = "judicial_analysis"
SECTION_RATIO = "ratio_decidendi"
SECTION_ORDER = "operative_order"

ALL_SECTIONS = [
    SECTION_PREAMBLE,
    SECTION_HEADNOTE,
    SECTION_FACTS,
    SECTION_ISSUES,
    SECTION_ARGUMENTS,
    SECTION_ANALYSIS,
    SECTION_RATIO,
    SECTION_ORDER,
]

HOLDING_SECTIONS = {SECTION_RATIO, SECTION_HEADNOTE}
ARGUMENT_SECTIONS = {SECTION_ARGUMENTS}


# =====================================================================
# Pakistani Heading & Structural Regex Registry
# =====================================================================

# Explicit Heading Line Matchers
RE_EXPLICIT_HEADINGS = [
    (SECTION_ORDER, re.compile(
        r'^(?:OPERATIVE\s+(?:PART|ORDER)|FINAL\s+ORDER|DISPOSITION|RELIEF|CONCLUSION|ORDER\s+ACCORDINGLY)\s*[:\-]?\s*$',
        re.IGNORECASE
    )),
    (SECTION_RATIO, re.compile(
        r'^(?:RATIO\s+DECIDENDI|LEGAL\s+(?:PRINCIPLE|HOLDING)|FINDING\s+ON\s+ISSUE|DECISION\s+ON\s+POINT|HELD)\s*[:\-]?\s*$',
        re.IGNORECASE
    )),
    (SECTION_ISSUES, re.compile(
        r'^(?:ISSUES\s+FRAMED|POINTS?\s+FOR\s+DETERMINATION|QUESTIONS?\s+(?:OF\s+LAW|FOR\s+CONSIDERATION)|ISSUES?)\s*[:\-]?\s*$',
        re.IGNORECASE
    )),
    (SECTION_ARGUMENTS, re.compile(
        r'^(?:CONTENTIONS?\s+OF\s+COUNSEL|SUBMISSIONS?\s+OF\s+COUNSEL|ARGUMENTS?|RIVAL\s+CONTENTIONS?|ARGUMENTS?\s+ON\s+BEHALF\s+OF\s+[^\n]+)\s*[:\-]?\s*$',
        re.IGNORECASE
    )),
    (SECTION_FACTS, re.compile(
        r'^(?:FACTS|FACTUAL\s+BACKGROUND|BRIEF\s+FACTS|BACKGROUND|PROSECUTION\s+CASE|PROSECUTION\s+STORY|CASE\s+OF\s+THE\s+PARTIES)\s*[:\-]?\s*$',
        re.IGNORECASE
    )),
    (SECTION_ANALYSIS, re.compile(
        r'^(?:JUDICIAL\s+ANALYSIS|ANALYSIS|DISCUSSION|CONSIDERATION|FINDINGS?|EVALUATION\s+OF\s+EVIDENCE|REASONS?)\s*[:\-]?\s*$',
        re.IGNORECASE
    )),
    (SECTION_ORDER, re.compile(
        r'^(?:SHORT\s+ORDER|ORDER|JUDGMENT)\s*$',
        re.IGNORECASE
    )),
]

# Paragraph-Level Structural Semantic Signals
RE_SIGNAL_ORDER = re.compile(
    r'\b(?:for\s+the\s+reasons\s+(?:recorded|stated)\s+(?:above|hereinabove)|'
    r'in\s+(?:the\s+)?foregoing\s+circumstances|'
    r'consequently,?\s+this\s+(?:appeal|petition|revision)|'
    r'resultantly,?\s+this\s+(?:appeal|petition|revision)|'
    r'the\s+up-shot\s+of\s+the\s+above\s+discussion|'
    r'accordingly,?\s+this\s+(?:appeal|petition|revision)|'
    r'in\s+view\s+of\s+the\s+above,?\s+this\s+(?:appeal|petition|revision)|'
    r'petition\s+is\s+converted\s+into\s+(?:an\s+)?appeal\s+and\s+allowed|'
    r'ad-interim\s+pre-arrest\s+bail\s+is\s+confirmed|'
    r'ad-interim\s+bail\s+is\s+confirmed|'
    r'revision\s+(?:is\s+)?accepted|'
    r'appeal\s+(?:is\s+)?allowed|'
    r'appeal\s+(?:is\s+)?dismissed|'
    r'petition\s+(?:is\s+)?dismissed|'
    r'order\s+accordingly|no\s+order\s+as\s+to\s+costs)',
    re.IGNORECASE
)

RE_SIGNAL_RATIO = re.compile(
    r'\b(?:(?:we|i)\s+hold\s+that|'
    r'settled\s+(?:proposition|principle|law)\s+(?:that|of)|'
    r'in\s+(?:our|my)\s+considered\s+view|'
    r'the\s+principle\s+that\s+emerges\s+from|'
    r'we\s+are\s+of\s+the\s+(?:unhesitating\s+)?view\s+that|'
    r'the\s+inescapable\s+conclusion\s+is\s+that|'
    r'held\s*[:\-]|'
    r'is\s+not\s+legally\s+sustainable|'
    r'was\s+not\s+legally\s+sustainable|'
    r'entitled\s+to\s+confine|'
    r'non-performance\s+of\s+contractual\s+promise\s+does\s+not\s+per\s+se\s+constitute|'
    r'criminal\s+machinery\s+cannot\s+be\s+activated\s+as\s+a\s+recovery\s+forum|'
    r'under\s+section\s+\d+.*the\s+court\s+is\s+under\s+mandatory\s+statutory\s+duty|'
    r'consent\s+of\s+husband\s+is\s+not\s+a\s+prerequisite|'
    r'each\s+co-owner\s+possesses\s+ownership\s+rights|'
    r'the\s+question\s+is\s+answered\s+in\s+the\s+(?:affirmative|negative))',
    re.IGNORECASE
)

RE_SIGNAL_ARGUMENTS = re.compile(
    r'\b(?:learned\s+counsel\s+for\s+the\s+(?:petitioner|appellant|respondent|plaintiff|defendant|applicant|State)|'
    r'the\s+learned\s+(?:counsel|advocate|Additional\s+Attorney\s+General|Prosecutor\s+General|AAG|DAG|ASC|AOR)|'
    r'learned\s+Attorney\s+General\s+argued|'
    r'learned\s+State\s+counsel\s+contended|'
    r'Mr\.\s+[A-Za-z\s\.]+,?\s+(?:learned\s+counsel|ASC|advocate)|'
    r'conversely,?\s+(?:the\s+)?learned\s+counsel|'
    r'on\s+the\s+other\s+hand,?\s+(?:the\s+)?learned|'
    r'contended\s+that|submits\s+that|vehemently\s+(?:argued|contended|submitted)|'
    r'took\s+up\s+the\s+plea\s+that|'
    r'contended\s+that\s+the\s+(?:suit|petition|appeal)\s+was\s+not\s+maintainable)\b',
    re.IGNORECASE
)

RE_SIGNAL_ISSUES = re.compile(
    r'\b(?:the\s+following\s+questions?\s+(?:arise|arises|for\s+determination)|'
    r'the\s+points?\s+for\s+(?:our\s+)?consideration|'
    r'the\s+pivotal\s+(?:question|issue|point)\s+requiring\s+determination|'
    r'issue\s+no\.?\s*\d+\s*[:\-]|'
    r'whether\s+(?:or\s+not\s+)?[a-z\s]+(?:\?|:))\b',
    re.IGNORECASE
)

RE_SIGNAL_ANALYSIS = re.compile(
    r'\b(?:we\s+have\s+heard\s+the\s+learned\s+counsel|'
    r'having\s+heard\s+the\s+(?:rival\s+)?contentions|'
    r'we\s+have\s+perused\s+the\s+record|'
    r'perusal\s+of\s+the\s+record\s+reveals|'
    r'in\s+order\s+to\s+appreciate\s+the\s+controversy|'
    r'a\s+bare\s+reading\s+of\s+section|'
    r'it\s+is\s+profitable\s+to\s+refer\s+to|'
    r'adverting\s+to\s+the\s+(?:merits|contentions)|'
    r'examination\s+of\s+the\s+impugned\s+judgment)\b',
    re.IGNORECASE
)

RE_SIGNAL_FACTS = re.compile(
    r'\b(?:briefly\s+stated,?\s+(?:the\s+)?facts|'
    r'the\s+facts\s+relevant\s+for\s+(?:the\s+)?disposal|'
    r'the\s+factual\s+matrix\s+of\s+the\s+case|'
    r'this\s+(?:civil\s+revision|appeal|petition|constitutional\s+petition)\s+arises\s+out\s+of|'
    r'the\s+prosecution\s+(?:case|story)\s+as\s+(?:unfolded|narrated|alleged)|'
    r'through\s+this\s+(?:petition|appeal|revision),?\s+the\s+petitioner|'
    r'the\s+petitioner\s+filed\s+a\s+suit\s+for|'
    r'the\s+learned\s+trial\s+court\s+decreed|'
    r'dispute\s+between\s+the\s+parties\s+pertains\s+to|'
    r'fir\s+no\.?\s*\d+\s+was\s+registered)\b',
    re.IGNORECASE
)

RE_PREAMBLE_SIGNATURES = re.compile(
    r'(?:Before\s+[A-Za-z\s\.]+,?\s*(?:J|CJ|JJ)|'
    r'Present:\s+[A-Za-z\s\.,]+|'
    r'---Petitioner|---Respondent|'
    r'\bVersus\b|'
    r'Civil\s+Revision\s+No\.|Criminal\s+Appeal\s+No\.|Constitutional\s+Petition\s+No\.|Civil\s+Appeal\s+No\.|'
    r'for\s+Petitioner|for\s+Respondent|for\s+Appellant)',
    re.IGNORECASE
)

RE_REPORTER_CATCHWORDS = re.compile(
    r'(?:-{3,}Ss?\.\s*\d+|-{3,}O\.\s*[IVXLCDM\d]+|-{3,}Arts?\.\s*\d+|-{3,}(?:Held|Validity|Scope|Applicability)\b|^-{4,}|'
    r'\bO\.\s*[IVXLCDM\d]+[,\s]+R\.\s*\d+|\bSs?\.\s*\d+[,\s]+(?:of\s+)?(?:Partition|CPC|Cr\.?P\.?C|PPC)\b|\bHeld\s*[:\-])',
    re.MULTILINE | re.IGNORECASE
)


# =====================================================================
# Tokenizer Estimator
# =====================================================================

try:
    import tiktoken
    _CL100K_ENC = tiktoken.get_encoding("cl100k_base")
except Exception:
    _CL100K_ENC = None


def count_tokens(text: str) -> int:
    """Exact tiktoken count if installed; calibrated 2.4 chars/token fallback."""
    if not text:
        return 0
    if _CL100K_ENC is not None:
        try:
            return len(_CL100K_ENC.encode(text))
        except Exception:
            pass
    # Calibrated fallback for legal English/Pakistani mixed text
    return max(1, math.ceil(len(text) / 2.4))


# =====================================================================
# Core Hierarchical Legal Judgment Chunker
# =====================================================================

class HierarchicalLegalChunker:
    """
    Transforms unstructured Pakistani court judgments into structured,
    hierarchically sectioned and tagged chunks.
    """

    @classmethod
    def clean_portal_debris(cls, text: str) -> str:
        """Strips HTML tags, portal navigation, and scraping headers."""
        if not text:
            return ""
        t = re.sub(r'<[^>]+>', ' ', text)
        t = re.sub(r'(?i)(?:Citation Name:\s*[^\n]+|Bookmark this Case|Copyrights?\s*©?[^\n]+|Help\s+FAQ\'?s\s+Sitemap|This site is developed\s*&?\s*maintained[^\n]*)', '', t)
        t = re.sub(r'(?i)(?:page \d+ of \d+|all rights reserved)', '', t)
        t = t.replace('\xa0', ' ')
        t = re.sub(r'[\r\t]+', ' ', t)
        t = re.sub(r'\n{3,}', '\n\n', t)
        return t.strip()

    @classmethod
    def parse_judgment_sections(cls, text: str) -> List[Dict[str, Any]]:
        """
        Parses judgment text into discrete structural sections:
        - Editorial Headnote
        - Preamble & Coram
        - Facts & History
        - Framed Issues
        - Counsel Arguments
        - Judicial Analysis
        - Ratio Decidendi
        - Operative Order
        """
        cleaned = cls.clean_portal_debris(text)
        if not cleaned:
            return []

        # Step 1: Detect and isolate editorial headnote vs body
        headnote_text, body_text = cls._extract_headnote_and_body(cleaned)

        sections: List[Dict[str, Any]] = []

        if headnote_text:
            sections.append({
                "section_type": SECTION_HEADNOTE,
                "heading": "HEADNOTE",
                "raw_text": headnote_text,
                "paragraphs": [p.strip() for p in re.split(r'\n{2,}', headnote_text) if p.strip()],
                "is_holding": True,
                "is_argument": False
            })

        if not body_text:
            return sections

        # Step 2: Split body into atomic paragraphs
        raw_paras = [p.strip() for p in re.split(r'\n{2,}|\n(?=\d+\.\s+|\([a-z\d]+\)\s+)', body_text) if p.strip()]

        if not raw_paras:
            return sections

        # Step 3: Classify each paragraph into its structural section
        current_section_type = SECTION_PREAMBLE
        current_heading = "PREAMBLE"
        current_paras: List[str] = []

        for p in raw_paras:
            detected_sec, explicit_head, p_content = cls._detect_paragraph_section(p, current_section_type)

            # Skip empty or trivial isolated transitions like bare "JUDGMENT\n"
            if not p_content and explicit_head in ("JUDGMENT", "ORDER", "SHORT ORDER"):
                current_section_type = SECTION_FACTS
                current_heading = explicit_head
                continue

            if detected_sec != current_section_type:
                if current_paras:
                    # Flush previous section
                    combined_p_text = "\n\n".join(current_paras)
                    sections.append({
                        "section_type": current_section_type,
                        "heading": current_heading,
                        "raw_text": combined_p_text,
                        "paragraphs": current_paras,
                        "is_holding": current_section_type in HOLDING_SECTIONS,
                        "is_argument": current_section_type in ARGUMENT_SECTIONS
                    })
                current_section_type = detected_sec
                current_heading = explicit_head or detected_sec.upper()
                current_paras = [p_content] if p_content else []
            else:
                if explicit_head:
                    current_heading = explicit_head
                if p_content:
                    current_paras.append(p_content)

        if current_paras:
            combined_p_text = "\n\n".join(current_paras)
            sections.append({
                "section_type": current_section_type,
                "heading": current_heading,
                "raw_text": combined_p_text,
                "paragraphs": current_paras,
                "is_holding": current_section_type in HOLDING_SECTIONS,
                "is_argument": current_section_type in ARGUMENT_SECTIONS
            })

        # Step 4: Drop empty or non-substantive preamble artifacts (< 10 words)
        cleaned_sections = []
        for s in sections:
            words = len(s["raw_text"].split())
            if s["section_type"] == SECTION_PREAMBLE and words < 10:
                continue
            cleaned_sections.append(s)

        return cleaned_sections

    @classmethod
    def chunk_judgment(
        cls,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        target_tokens: int = 512,
        overlap_tokens: int = 64
    ) -> List[Dict[str, Any]]:
        """
        Hierarchically chunks judgment into discrete vector payloads.
        Guarantees:
        1. Never blends content across distinct structural sections into the same chunk.
        2. Preserves atomic legal paragraphs.
        3. Enforces token bounds (target_tokens) with paragraph-aware splitting.
        4. Injects rich hierarchical context header to each chunk.
        """
        meta = metadata or {}
        sections = cls.parse_judgment_sections(text)
        if not sections:
            return []

        cid = str(meta.get("case_id") or "CASE_UNKNOWN")
        cit = meta.get("neutral_citation") or meta.get("citation") or cid
        title = meta.get("case_title") or meta.get("title") or "Precedent"
        court = meta.get("court_name") or meta.get("court") or "Superior Court of Pakistan"
        year = meta.get("decision_date", "")[:4] if meta.get("decision_date") else str(meta.get("year", 2024))
        domain = meta.get("domain") or meta.get("legal_domain") or "civil"
        subdomain = meta.get("subdomain") or "general"

        all_chunks: List[Dict[str, Any]] = []

        for sec_idx, sec in enumerate(sections):
            sec_type = sec["section_type"]
            sec_heading = sec["heading"]
            paras = sec["paragraphs"]
            is_holding = sec["is_holding"]
            is_argument = sec["is_argument"]

            sec_label = sec_type.replace("_", " ").upper()
            header = f"[{cit} | {court} | {year} | Section: {sec_label}]"
            header_tokens = count_tokens(header + "\n\n")
            max_body_tokens = max(100, target_tokens - header_tokens)

            # Micro-chunking paragraphs within this section
            sec_chunks = cls._chunk_section_paragraphs(paras, max_body_tokens, overlap_tokens)

            for chk_in_sec, chunk_body in enumerate(sec_chunks):
                if not chunk_body.strip():
                    continue
                full_chunk_text = f"{header}\n\n{chunk_body}".strip()
                t_count = count_tokens(full_chunk_text)

                safe_cid = cid if len(cid) <= 100 else f"{cid[:80]}_{hashlib.md5(cid.encode('utf-8')).hexdigest()[:10]}"
                chunk_id = f"{safe_cid}_s{sec_idx}_c{chk_in_sec}"

                chunk_payload = {
                    "chunk_id": chunk_id,
                    "text": full_chunk_text,
                    "clean_body": chunk_body,
                    "token_count": t_count,
                    "section_type": sec_type,
                    "section_heading": sec_heading,
                    "section_index": sec_idx,
                    "chunk_index": len(all_chunks),
                    "is_holding": is_holding,
                    "is_argument": is_argument,
                    "metadata": {
                        "case_id": cid[:256],
                        "citation": cit[:256],
                        "case_title": title[:256],
                        "court": court[:128],
                        "year": int(year) if str(year).isdigit() else 2024,
                        "domain": domain,
                        "legal_domain": domain,
                        "subdomain": subdomain,
                        "section_type": sec_type,
                        "section_heading": sec_heading,
                        "section_index": sec_idx,
                        "is_holding": is_holding,
                        "is_argument": is_argument,
                        "token_count": t_count,
                        "chunk_id": chunk_id
                    }
                }
                all_chunks.append(chunk_payload)

        # Update total_chunks in each chunk payload
        total_count = len(all_chunks)
        for c in all_chunks:
            c["total_chunks"] = total_count
            c["metadata"]["total_chunks"] = total_count

        return all_chunks

    # -----------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------

    @classmethod
    def _extract_headnote_and_body(cls, text: str) -> Tuple[str, str]:
        """Separates law report editorial headnote from judicial order/judgment."""
        t = text.strip()

        # Check for genuine statutory catchwords
        has_catchwords = bool(RE_REPORTER_CATCHWORDS.search(t[:2500]))
        if not has_catchwords:
            return "", t

        # Split markers separating headnote from judicial body
        order_match = re.search(r'\n{2,}\s*(?:JUDGMENT|ORDER|SHORT ORDER)\s*\n+', t, re.IGNORECASE)
        byline_match = re.search(r'\n{2,}\s*(?:[A-Z\s\.]+(?:,?\s*J\.|,?\s*CJ\.|,?\s*JJ\.)---|Before\s+[A-Za-z\s\.]+,?\s*(?:J|CJ|JJ))', t)

        candidate_offsets = []
        if order_match and order_match.start() > 80:
            candidate_offsets.append(order_match.start())
        if byline_match and byline_match.start() > 80:
            candidate_offsets.append(byline_match.start())

        split_offset = min(candidate_offsets) if candidate_offsets else None

        if split_offset:
            return t[:split_offset].strip(), t[split_offset:].strip()
        elif len(t.split()) < 1000:
            return t, ""
        else:
            return "", t

    @classmethod
    def _detect_paragraph_section(cls, p: str, current_sec: str) -> Tuple[str, Optional[str], str]:
        """
        Determines the structural section for a paragraph based on headings,
        lead-in phrases, and positional progression.
        Returns: (detected_sec, explicit_head, content_without_heading)
        """
        p_clean = p.strip()
        lines = p_clean.split("\n")
        first_line = lines[0].strip()

        # 1. Check explicit heading line
        for sec_type, regex in RE_EXPLICIT_HEADINGS:
            if regex.match(first_line):
                body_after = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
                if sec_type == SECTION_ORDER and first_line.upper() in ("JUDGMENT", "ORDER", "SHORT ORDER"):
                    # Transition from preamble into judgment facts
                    return SECTION_FACTS, first_line.upper(), body_after
                return sec_type, first_line.upper(), body_after

        # 2. Check preamble signatures
        if current_sec == SECTION_PREAMBLE:
            if RE_PREAMBLE_SIGNATURES.search(p_clean[:300]):
                return SECTION_PREAMBLE, "PREAMBLE", p_clean

        # 3. Check structural semantic signals in priority order
        if RE_SIGNAL_ORDER.search(p_clean):
            return SECTION_ORDER, "OPERATIVE ORDER", p_clean

        if RE_SIGNAL_RATIO.search(p_clean):
            return SECTION_RATIO, "RATIO DECIDENDI", p_clean

        if RE_SIGNAL_ARGUMENTS.search(p_clean):
            return SECTION_ARGUMENTS, "COUNSEL ARGUMENTS", p_clean

        if RE_SIGNAL_ISSUES.search(p_clean):
            return SECTION_ISSUES, "ISSUES FRAMED", p_clean

        if RE_SIGNAL_ANALYSIS.search(p_clean):
            return SECTION_ANALYSIS, "JUDICIAL ANALYSIS", p_clean

        if RE_SIGNAL_FACTS.search(p_clean):
            return SECTION_FACTS, "FACTS & PROCEDURAL HISTORY", p_clean

        # 4. Positional fallback progression
        if current_sec == SECTION_PREAMBLE:
            return SECTION_FACTS, "FACTS", p_clean

        return current_sec, None, p_clean

    @classmethod
    def _chunk_section_paragraphs(
        cls,
        paragraphs: List[str],
        max_tokens: int,
        overlap_tokens: int
    ) -> List[str]:
        """
        Packs atomic paragraphs into chunks up to max_tokens.
        Preserves paragraph indivisibility. Splits individual paragraphs
        only if a single paragraph exceeds max_tokens.
        """
        chunks: List[str] = []
        current_chunk_paras: List[str] = []
        current_tokens = 0

        for p in paragraphs:
            if not p.strip():
                continue
            p_tokens = count_tokens(p)

            # If a single paragraph is larger than max_tokens, split it by sentence
            if p_tokens > max_tokens:
                # Flush existing buffer
                if current_chunk_paras:
                    chunks.append("\n\n".join(current_chunk_paras))
                    current_chunk_paras = []
                    current_tokens = 0

                sentence_chunks = cls._split_oversized_paragraph(p, max_tokens, overlap_tokens)
                chunks.extend(sentence_chunks)
                continue

            if current_tokens + p_tokens + (2 if current_chunk_paras else 0) <= max_tokens:
                current_chunk_paras.append(p)
                current_tokens += p_tokens
            else:
                if current_chunk_paras:
                    chunks.append("\n\n".join(current_chunk_paras))

                # Paragraph overlap: seed new chunk with the last paragraph if it fits within overlap
                seed_paras = []
                seed_tokens = 0
                if current_chunk_paras and overlap_tokens > 0:
                    last_p = current_chunk_paras[-1]
                    last_tok = count_tokens(last_p)
                    if last_tok <= overlap_tokens:
                        seed_paras.append(last_p)
                        seed_tokens = last_tok

                current_chunk_paras = seed_paras + [p]
                current_tokens = seed_tokens + p_tokens

        if current_chunk_paras:
            chunks.append("\n\n".join(current_chunk_paras))

        return chunks

    @classmethod
    def _split_oversized_paragraph(
        cls,
        paragraph: str,
        max_tokens: int,
        overlap_tokens: int
    ) -> List[str]:
        """Splits an oversized paragraph along clean sentence boundaries."""
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', paragraph) if s.strip()]
        if not sentences:
            return [paragraph]

        chunks: List[str] = []
        cur_sens: List[str] = []
        cur_tok = 0

        for s in sentences:
            s_tok = count_tokens(s)
            if cur_tok + s_tok <= max_tokens:
                cur_sens.append(s)
                cur_tok += s_tok
            else:
                if cur_sens:
                    chunks.append(" ".join(cur_sens))
                cur_sens = [s]
                cur_tok = s_tok

        if cur_sens:
            chunks.append(" ".join(cur_sens))

        return chunks
