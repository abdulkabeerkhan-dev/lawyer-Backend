"""
legal_ai/verification/memo_auditor.py

In-memory Stage-6 legal memorandum auditor.
Runs deterministic sentence, statute, citation, and relevance audits in < 20ms
with ZERO extra LLM calls and ZERO banners injected into user-facing markdown.
"""

from __future__ import annotations
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Callable, Iterable, List, Dict, Optional, Tuple, Any

from legal_ai.verification.doctrinal_rules import (
    CORE_CODES,
    ACT_ALIASES,
    GAP_PHRASES,
    STRONG_PHRASES,
    OVERCLAIM_PHRASES,
    PATTERN_RULES,
    TOPICS_SPEC,
    classify_matter_type,
    detect_topics,
    rule_matches_sentence,
)
from legal_ai.verification.statute_matcher import (
    straighten,
    norm_text,
    normalize_citation,
    find_citations,
    sentences,
    shingles,
    StatuteAuthorityStore,
    get_authority_store,
)

CARDS_RE = re.compile(r"<<<CARDS>>>(.*?)<<<END_CARDS>>>", re.DOTALL)
ERROR, WARN, INFO = "error", "warn", "info"


@dataclass
class Finding:
    code: str
    severity: str
    message: str
    excerpt: str = ""
    fix: str = ""
    rule_status: str = "reviewed"      # "pending_review" for unreviewed doctrinal rules
    auto_fixed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RelevanceResult:
    citation: str
    topic: str
    passes: bool
    reason: str
    method: str = "keyword_prefilter"  # keyword_prefilter | llm_judge | no_source_text

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuditResult:
    topics: List[str]
    findings: List[Finding]
    body: str                          # Clean memo body after auto-fixes, cards block removed
    cards: List[Dict[str, Any]]
    relevance: List[RelevanceResult]
    confidence: str                    # Firm | Qualified | Unresolved
    confidence_reasons: List[str] = field(default_factory=list)
    statute_gaps: List[str] = field(default_factory=list)

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == WARN]

    def render(self, include_cards: bool = True) -> str:
        """Re-emit memo in existing <<<CARDS>>> format without any banners."""
        out = self.body.rstrip()
        if include_cards:
            out += "\n\n<<<CARDS>>> " + json.dumps(self.cards, ensure_ascii=False, indent=1) + " <<<END_CARDS>>>"
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topics": self.topics,
            "confidence": self.confidence,
            "confidence_reasons": self.confidence_reasons,
            "statute_gaps": self.statute_gaps,
            "findings": [f.to_dict() for f in self.findings],
            "relevance": [r.to_dict() for r in self.relevance],
            "cards": self.cards,
        }


# Aliases for API parity
VerificationReport = AuditResult


def split_cards(memo: str) -> Tuple[str, List[Dict[str, Any]], bool]:
    m = CARDS_RE.search(memo)
    if not m:
        return memo, [], True
    body = (memo[:m.start()] + memo[m.end():]).strip()
    raw = straighten(m.group(1)).strip()
    try:
        cards = json.loads(raw)
        return body, cards if isinstance(cards, list) else [cards], True
    except Exception:
        return body, [], False


def _prov_regex(p: Dict[str, Any]) -> Optional[re.Pattern]:
    if p.get("pattern"):
        return re.compile(p["pattern"], re.IGNORECASE)
    ident = re.escape(p["id"])
    lead = r"(?:\d+[\-A-Z]*\s*(?:,|&|and|to)\s*)*"
    if p["kind"] == "section":
        return re.compile(rf"(?:sections?|ss?\.)\s*{lead}{ident}\b", re.IGNORECASE)
    if p["kind"] == "article":
        return re.compile(rf"(?:articles?|arts?\.)\s*{lead}{ident}\b", re.IGNORECASE)
    return None


def _act_near(store: StatuteAuthorityStore, act: str, s: str, start: int, end: int) -> bool:
    win = s[max(0, start - 110): end + 110]
    return any(re.search(a, win, re.IGNORECASE) for a in ACT_ALIASES.get(act, []))


def _quotes(text: str, min_words: int = 8) -> List[Tuple[str, int]]:
    t = straighten(text)
    return [(m.group(1), m.start()) for m in re.finditer(r'"([^"]{20,})"', t) if len(m.group(1).split()) >= min_words]


def case_key(store: StatuteAuthorityStore, raw: str, court: Optional[str] = None) -> str:
    c, ok = normalize_citation(raw, court)
    if not ok:
        m = re.match(r"PLD (\d{4}) \? (\d+)", c)
        if m:
            c = store.resolve_pld(m.group(1), m.group(2)) or c
    return c


def relevance_for(
    store: StatuteAuthorityStore,
    case: Dict[str, Any],
    topics: Iterable[str],
    judge: Optional[Callable[[Dict[str, Any], str], Tuple[bool, str]]] = None
) -> List[RelevanceResult]:
    cit = case.get("citation", "")
    j = store.judgments.get(cit)
    text = j.text if j else (case.get("holding") or case.get("headnote") or case.get("text") or case.get("preview") or "")
    out = []
    for t in topics:
        if t not in TOPICS_SPEC:
            continue
        spec = TOPICS_SPEC[t]
        if not text.strip():
            out.append(RelevanceResult(cit, t, False, "no source text (headnote or full text) available to judge relevance", "no_source_text"))
            continue
        strong = [p for p in spec["relevance"]["strong"] if re.search(p, text, re.IGNORECASE)]
        if not strong:
            out.append(RelevanceResult(cit, t, False, f"source text contains none of the {t} markers", "keyword_prefilter"))
            continue
        if judge:
            ok, why = judge(case, t)
            out.append(RelevanceResult(cit, t, bool(ok), why, "llm_judge"))
        else:
            out.append(RelevanceResult(cit, t, True, "matched: " + "; ".join(strong[:3]), "keyword_prefilter"))
    return out


def audit_memo(
    memo: str,
    store: Optional[StatuteAuthorityStore] = None,
    query: str = "",
    retrieved: Optional[List[Dict[str, Any]]] = None,
    judge: Optional[Callable] = None,
    drop_irrelevant_cards: bool = True,
    matter_type: Optional[str] = None
) -> AuditResult:
    """
    Stage-6 in-memory legal memorandum auditor.
    Executes in < 20 ms.
    Returns clean body (with zero banners) and rich structured audit findings.
    """
    if store is None:
        store = get_authority_store()

    body, cards, cards_ok = split_cards(memo)
    full_context = query + "\n" + body
    topics = detect_topics(full_context)
    inferred_matter = matter_type or (classify_matter_type(query) if query else classify_matter_type(body))

    F: List[Finding] = []

    def add(code: str, severity: str, message: str, excerpt: str = "", fix: str = "", rule_status: str = "reviewed", auto_fixed: bool = False):
        F.append(Finding(
            code=code,
            severity=severity,
            message=message,
            excerpt=excerpt,
            fix=fix,
            rule_status=rule_status,
            auto_fixed=auto_fixed
        ))

    if not cards_ok:
        add("CARDS_UNPARSEABLE", WARN, "The <<<CARDS>>> block is not valid JSON even after quote normalisation.")

    # Register known citations
    retrieved = retrieved or []
    for c in retrieved:
        if c.get("citation"):
            store.register_citation(c["citation"], c.get("court"), c.get("title", ""))
    for c in cards:
        if c.get("citation"):
            store.register_citation(c["citation"].split(" and ")[0], c.get("court"), c.get("case_name", ""))

    # 1. Sentence-level pattern rules + provision-subject checks
    seen = set()
    sents = sentences(body)
    for s in sents:
        # Pattern rules
        for r in PATTERN_RULES:
            if r.get("topics") and not set(r["topics"]) & set(topics):
                continue
            if rule_matches_sentence(r, s, matter_type=inferred_matter):
                key = (r["id"], s[:80])
                if key not in seen:
                    seen.add(key)
                    add(
                        r["code"],
                        r["severity"],
                        r["message"],
                        s[:260],
                        r.get("fix", ""),
                        rule_status=r.get("status", "pending_review")
                    )

        # Provision subject mismatch checks
        for p in store.provisions:
            if not p.get("not_about"):
                continue
            rx = _prov_regex(p)
            m = rx.search(s) if rx else None
            if not m or not _act_near(store, p["act"], s, m.start(), m.end()):
                continue
            bad = [x for x in p["not_about"] if re.search(x, s, re.IGNORECASE)]
            if bad and not any(re.search(x, s, re.IGNORECASE) for x in p.get("required_if_correct", [])):
                add(
                    "PROVISION_SUBJECT_MISMATCH",
                    p.get("severity", ERROR),
                    f"{p['act'].upper()} {p['kind']} {p['id']} concerns: {p['subject']}. The sentence attributes something else to it.",
                    s[:260],
                    f"Describe it as: {p['subject']}",
                    rule_status="pending_review"
                )

    # 2. Mandatory governing provisions per topic
    for t in topics:
        if t in TOPICS_SPEC:
            for g in TOPICS_SPEC[t]["mandatory_groups"]:
                if not any(re.search(p, body, re.IGNORECASE) for p in g["any"]):
                    add(
                        "MISSING_GOVERNING_PROVISION",
                        ERROR,
                        f"Governing provision never addressed: {g['label']}.",
                        fix="Retrieve and analyse it.",
                        rule_status="pending_review"
                    )

    # 3. Template residue (e.g. criminal bail headings in civil matters)
    for t in topics:
        if t in TOPICS_SPEC:
            for line in body.splitlines():
                if any(re.search(p, line, re.IGNORECASE) for p in TOPICS_SPEC[t]["template_forbid"]):
                    stripped = line.strip()
                    if stripped.startswith(("#", "1", "2", "3", "4", "5", "6", "7", "8", "9")):
                        add(
                            "TEMPLATE_RESIDUE",
                            ERROR,
                            "Heading belongs to a criminal template but the matter is civil.",
                            stripped[:120],
                            "Select headings from topic.template_headings."
                        )
                        break

    # 4. Quotes verification (8+ words against loaded bare acts or judgments)
    statute_norm = [norm_text(x) for x in store.all_statute_texts()]
    judg_norm = [j.norm for j in store.judgments.values()]
    for q, pos in _quotes(body):
        nq = norm_text(q)
        if any(nq in x for x in statute_norm + judg_norm):
            continue
        ctx = body[max(0, pos - 320): pos].lower()
        if re.search(r"(section|article|rule|order)\b", ctx) and re.search(r"provid|state|read|text|stipulat|enact", ctx):
            add(
                "STATUTE_QUOTE_UNVERIFIED",
                ERROR,
                "Quoted statutory text is not in the statute store. It must be pasted verbatim from the loaded source or the quotation marks removed.",
                q[:200],
                "Load the provision text in data/provisions.json, or paraphrase and mark as unverified."
            )
        else:
            add(
                "QUOTE_UNVERIFIED",
                WARN,
                "Quotation not found in any loaded judgment or statute text.",
                q[:200]
            )

    # 5. Citations: format + must come from retrieved set
    known = {case_key(store, c["citation"], c.get("court")) for c in retrieved if c.get("citation")}
    known |= {case_key(store, c["citation"].split(" and ")[0], c.get("court")) for c in cards if c.get("citation")} | set(store.judgments)
    fixes = {}
    for raw, a, b in find_citations(body):
        canon = case_key(store, raw, None)
        if canon != raw and "?" not in canon:
            fixes[raw] = canon
        if "?" in canon:
            add("CITATION_COURT_UNRESOLVED", WARN, "PLD citation lacks a court code and could not be resolved from the index.", raw)
        elif canon not in known:
            add("UNRETRIEVED_CITATION", ERROR, "Case cited in the memo was not in the retrieved set (possible invented or recalled authority).", raw, "Remove or retrieve it.")
    for raw, canon in fixes.items():
        body = body.replace(raw, canon)
        add("CITATION_FORMAT", INFO, f"Normalised '{raw}' to '{canon}'.", auto_fixed=True)

    # 6. Relevance gate over retrieved + cards
    cases: Dict[str, Dict[str, Any]] = {}
    for c in retrieved:
        if c.get("citation"):
            cases[case_key(store, c["citation"], c.get("court"))] = {**c, "citation": case_key(store, c["citation"], c.get("court"))}
    for c in cards:
        if c.get("citation"):
            k = case_key(store, c["citation"].split(" and ")[0], c.get("court"))
            cases.setdefault(k, {"citation": k, "court": c.get("court"), "title": c.get("case_name")})

    relevance: List[RelevanceResult] = []
    passing: Set[str] = set()
    for k, c in cases.items():
        res = relevance_for(store, c, topics, judge)
        relevance += res
        if any(r.passes for r in res):
            passing.add(k)
        else:
            why = res[0].reason if res else "no topic detected"
            add("IRRELEVANT_AUTHORITY", WARN, f"{k}: does not decide the question ({why}).", k)

    for t in topics:
        if not any(r.passes for r in relevance if r.topic == t):
            add("NO_AUTHORITY_FOR_TOPIC", ERROR, f"No retrieved case directly addresses '{t}'. The memo must say so and withhold a firm opinion.", fix="Run topic.extra_queries and re-retrieve.")

    # 7. Precedent cards: computed verification_status, null non-HTTP pdf_url
    out_cards = []
    for c in cards:
        k = case_key(store, (c.get("citation") or "").split(" and ")[0], c.get("court")) if c.get("citation") else ""
        j = store.judgments.get(k)
        if k:
            c["citation"] = k if " and " not in c.get("citation", "") else c["citation"]
        if j:
            claim = norm_text(" ".join(str(c.get(f, "")) for f in ("ratio_decidendi", "important_paragraphs")))
            sh = shingles(claim)
            score = round(len([x for x in sh if x in j.norm]) / max(1, len(sh)), 2)
            c["verification_status"] = f"FULL_TEXT_CHECKED (overlap {score})" if score >= 0.35 else f"FULL_TEXT_CHECKED_LOW_OVERLAP ({score})"
            if score < 0.35:
                add("CARD_NOT_GROUNDED", WARN, "Card ratio/paragraph text has low overlap with the stored judgment.", k)
        elif k in cases and (cases[k].get("holding") or cases[k].get("headnote")):
            c["verification_status"] = "HEADNOTE_ONLY"
        else:
            c["verification_status"] = "UNVERIFIED_NO_SOURCE_TEXT"

        if not str(c.get("pdf_url", "")).startswith("http"):
            c["pdf_url"] = None

        if drop_irrelevant_cards and k and k not in passing:
            continue
        out_cards.append(c)

    # 8. Unsupported "verified" labels in body (removed, not bannered)
    for s in sents:
        if any(re.search(p, s, re.IGNORECASE) for p in OVERCLAIM_PHRASES):
            add("OVERCLAIM_VERIFIED_LABEL", ERROR, "Unsupported verification claim.", s[:200], auto_fixed=True)
            body = body.replace(s, "")
    body = re.sub(r"\n{3,}", "\n\n", body)

    # 9. Appendix-gaps vs headline confidence
    gaps = any(re.search(p, body, re.IGNORECASE) for p in GAP_PHRASES)
    strong = any(re.search(p, body, re.IGNORECASE) for p in STRONG_PHRASES)
    if gaps and strong:
        bad = any(f.code in ("MISSING_GOVERNING_PROVISION", "NO_AUTHORITY_FOR_TOPIC") for f in F)
        add("OVERCONFIDENT_VS_GAPS", ERROR if bad else WARN, "Memo admits research gaps but states its conclusion in absolute terms.", fix="Hedge or withhold the opinion.")

    # 10. Governing statute text availability
    stat_gaps, reasons = [], []
    for t in topics:
        if t in TOPICS_SPEC:
            for key in TOPICS_SPEC[t]["mandatory_keys"]:
                if not store.statute_reviewed(key):
                    stat_gaps.append(key)
    if stat_gaps:
        add("STATUTE_TEXT_NOT_LOADED", INFO, f"{len(stat_gaps)} governing provision(s) have no reviewed verbatim text in the store.", ", ".join(stat_gaps[:8]))

    # 11. Confidence evaluation
    errs = [f for f in F if f.severity == ERROR]
    if any(f.code in CORE_CODES for f in errs):
        level = "Unresolved"
        reasons.append("core statutory/authority error(s): " + ", ".join(sorted({f.code for f in errs if f.code in CORE_CODES})))
    elif errs:
        level = "Qualified"
        reasons.append("non-core errors present")
    elif stat_gaps or not topics:
        level = "Qualified"
        reasons.append("governing statute text not loaded/reviewed" if stat_gaps else "no topic detected")
    else:
        level = "Firm"
        reasons.append("no errors; governing text loaded; relevant authority present")

    return AuditResult(topics, F, body, out_cards, relevance, level, reasons, stat_gaps)
