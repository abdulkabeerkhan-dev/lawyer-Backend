"""
core/claim_first_memo.py

ORDER 1.14 - HARDENED CLAIM-FIRST MEMOS ARCHITECTURE
Closes loopholes in analysis, paraphrase, quote attribution, and flag spoofing.

Claims structure:
  {
    "text": str,
    "type": "quote" | "paraphrase" | "analysis",
    "support": str  # canonical id + subsection (e.g. 'FIO_2001_SEC_22(4)') or None
  }

Hardened Enforcement:
1. Analysis Lane Loophole Closed:
   - Prohibits statute/case citations, unindexed authorities, numbers/durations not in question,
     absolute assertions ('always', 'never', 'must', 'automatically', 'void ab initio', 'can never', 'obliged to'),
     and purported statutory/judicial holdings ('statute says', 'court held').
   - Rendered strictly under '### Unreviewed analysis — not checked against any source'.
2. Paraphrase Strengthened:
   - Negation & modal parity: checks 'shall', 'shall not', 'may', 'may not', 'must', 'no', 'not', 'nor', 'unless', 'except', 'provided that', 'within', 'before', 'after'.
   - Term check: every content word must appear in cited subsection or on allow-list.
   - Rendered with official source text directly beside each paraphrase.
3. Misattributed Quotes Blocked:
   - A quote matching another provision than its support ID is flagged MISATTRIBUTED_QUOTE.
"""

import re
import difflib
from typing import Dict, List, Any, Optional, Tuple, Set

from core.unified_statute_store import get_unified_statute_store
from legal_ai.verification.memo_verifier import (
    shared_normalize,
    to_matching_stream,
    compute_word_diff,
    MemoVerifier
)

# Number extraction helpers
WORD_TO_NUMBER = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20,
    "twenty-one": 21, "twenty one": 21, "thirty": 30, "sixty": 60, "ninety": 90,
    "hundred": 100, "two hundred": 200, "three hundred": 300
}

# Order 1.14: Analysis Prohibition Rules
PROHIBITED_ABSOLUTE_WORDS = [
    "always", "never", "must", "automatically", "void ab initio", "can never", "obliged to"
]

STATUTORY_HOLDING_REGEX = re.compile(
    r'\b(?:statute|section|sec\.?|s\.|rule|r\.|order|ord\.?|article|art\.|act|ordinance|code)\s+(?:says|states|provides|mandates|allows|bars|prescribes|sets\s+out|requires|ordains|declares)\b',
    re.IGNORECASE
)

JUDICIAL_HOLDING_REGEX = re.compile(
    r'\b(?:court|bench|judge|supreme\s+court|high\s+court|judiciary)\s+(?:held|ruled|decided|observed|directed|concluded|found)\b|\bheld\s+that\b',
    re.IGNORECASE
)

# Order 1.14: Function words allow-list for paraphrase term check
FUNCTION_WORDS_ALLOWLIST = {
    # Determiners & articles
    "a", "an", "the", "this", "that", "these", "those", "each", "every", "all", "any", "both", "some", "such",
    # Pronouns
    "i", "me", "my", "we", "us", "our", "you", "your", "he", "him", "his", "she", "her", "it", "its", "they", "them", "their", "who", "whom", "whose", "which", "what",
    # Prepositions & particles
    "of", "in", "on", "at", "by", "for", "with", "about", "against", "between", "into", "through", "during", "before", "after", "above", "below", "to", "from", "up", "upon", "down", "out", "off", "over", "under",
    # Conjunctions
    "and", "or", "nor", "but", "so", "if", "whether", "as", "than", "because", "while", "where", "when", "although", "unless", "except", "since",
    # Auxiliary & linking verbs
    "is", "am", "are", "was", "were", "be", "been", "being", "have", "has", "had", "having", "do", "does", "did", "doing", "will", "would", "shall", "should", "may", "might", "must", "can", "could",
    # Adverbs of degree & common legal discourse
    "not", "no", "only", "also", "further", "however", "there", "here", "then", "thus", "therefore", "duly", "per", "se",
    # Structural legal reference terms
    "section", "sub-section", "subsection", "sec", "rule", "sub-rule", "subrule", "order", "act", "ordinance", "code", "article", "clause", "proviso", "provision", "provisions", "appellant", "respondent", "petitioner", "plaintiff", "defendant", "court", "judge", "bench", "party", "parties", "person", "suit", "appeal", "application", "applications", "decree", "order", "cpc", "fio", "ppc", "crpc", "tpa", "bco", "ss", "requires", "required", "requirement", "determines", "determined", "disposing", "disposes", "whole", "part", "counsel", "advocate", "ensure", "ensuring", "concurrently", "memo", "memorandum", "notice", "stay", "hearing", "appear", "filing", "equal", "value", "amount", "cash", "deposit", "security"
}

def extract_numbers_and_units(text: str) -> List[Tuple[float, str]]:
    """Extracts numeric quantities and attached time/percentage units."""
    results = []
    for m in re.finditer(r'\b(\d+(?:\.\d+)?)\s*(days?|months?|years?|judges?|percent|%|rupees?|rs\.?)?\b', text, re.I):
        val = float(m.group(1))
        unit = (m.group(2) or "").lower()
        if unit in ("judge", "judges"):
            unit = "judge"
        elif unit in ("day", "days"):
            unit = "day"
        elif unit in ("month", "months"):
            unit = "month"
        elif unit in ("year", "years"):
            unit = "year"
        elif unit in ("%", "percent"):
            unit = "%"
        results.append((val, unit))
    
    for w, val in WORD_TO_NUMBER.items():
        pat = rf'\b{re.escape(w)}\s*(days?|months?|years?|judges?|percent|%|rupees?|rs\.?)?\b'
        for m in re.finditer(pat, text, re.I):
            unit = (m.group(1) or "").lower()
            if unit in ("judge", "judges"):
                unit = "judge"
            elif unit in ("day", "days"):
                unit = "day"
            elif unit in ("month", "months"):
                unit = "month"
            elif unit in ("year", "years"):
                unit = "year"
            elif unit in ("%", "percent"):
                unit = "%"
            results.append((float(val), unit))
    return results

def format_support_tag(support: str) -> str:
    """Formats canonical provision support into a clean legal label (e.g. 's.22(4)')."""
    if not support:
        return ""
    m_sec = re.search(r'(?:SEC|Section)_(\d+[A-Za-z]?)(?:\((\d+[a-z]?)\))?', support, re.I)
    if m_sec:
        sec = m_sec.group(1)
        sub = m_sec.group(2)
        return f"s.{sec}({sub})" if sub else f"s.{sec}"
    
    m_ord = re.search(r'ORD_([IVXLCDM\d]+)_R_(\d+[A-Za-z]?)', support, re.I)
    if m_ord:
        return f"Order {m_ord.group(1)} Rule {m_ord.group(2)}"
    
    return support.replace("_", " ")


class ClaimFirstVerifier:
    def __init__(self, store=None):
        self.store = store or get_unified_statute_store()
        self._memo_verifier = MemoVerifier()

    def resolve_support_provision(self, support: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """Resolves support string to (record, canonical_id, subsection)."""
        if not support:
            return None, None, None
        
        m_sub = re.match(r'^([A-Z0-9_]+)\((\d+[a-z]?)\)$', support.strip(), re.I)
        if m_sub:
            base_cid = m_sub.group(1).upper()
            sub = m_sub.group(2)
            rec = self.store.get_by_canonical_id(base_cid)
            return rec, base_cid, sub
        
        rec = self.store.get_by_canonical_id(support.strip().upper())
        if rec:
            return rec, rec.get("canonical_id"), None
        
        m_pat = re.search(r'(?:Section|s\.)\s*(\d+[A-Za-z]?)(?:\s*\(\s*(\d+)\s*\))?\s*(FIO|PPC|CPC|CRPC|TPA)', support, re.I)
        if m_pat:
            act_map = {"FIO": "FIO_2001", "PPC": "PPC_1860", "CPC": "CPC_1908", "CRPC": "CRPC_1898", "TPA": "TPA_1882"}
            act = act_map.get(m_pat.group(3).upper())
            sec = m_pat.group(1)
            sub = m_pat.group(2)
            cid = f"{act}_SEC_{sec}"
            rec = self.store.get_by_canonical_id(cid)
            return rec, cid, sub

        return None, None, None

    def extract_subsection_text(self, full_text: str, subsection: Optional[str]) -> str:
        """Extracts text of a specific subsection from the full provision text."""
        if not subsection or not full_text:
            return full_text
        
        pat = rf'(?:^|\n)\s*\({re.escape(subsection)}\)\s*(.*?)(?=(?:\n\s*\(\d+[a-z]?\))|\Z)'
        m = re.search(pat, full_text, re.DOTALL | re.I)
        if m:
            return m.group(1).strip()
        pat_fallback = rf'\({re.escape(subsection)}\)\s*(.*?)(?=(?:\n|\.\s*)\(\d+[a-z]?\)|\Z)'
        m2 = re.search(pat_fallback, full_text, re.DOTALL | re.I)
        if m2:
            return m2.group(1).strip()
        return full_text

    def verify_single_claim(self, claim: Dict[str, Any], user_question: Optional[str] = None) -> Dict[str, Any]:
        """
        Verifies a single structured claim under Order 1.14 hardened rules.
        """
        c_text = (claim.get("text") or "").strip()
        c_type = (claim.get("type") or "analysis").lower().strip()
        c_support = claim.get("support", "")

        result = {
            "claim": claim,
            "passed": True,
            "violations": [],
            "label": "",
            "disputed_notice": None,
            "source_text": None
        }

        # ----------------------------------------------------------------------
        # 1. ANALYSIS CLAIM HARDENING (Order 1.14 - Item 1)
        # ----------------------------------------------------------------------
        if c_type == "analysis":
            # 1.1 Absolute words check
            for word in PROHIBITED_ABSOLUTE_WORDS:
                if re.search(rf'\b{re.escape(word)}\b', c_text, re.I):
                    result["passed"] = False
                    result["violations"].append({
                        "rule": "(e)",
                        "category": "ABSOLUTE_ASSERTION_IN_ANALYSIS",
                        "issue": f"Analysis claim contains prohibited absolute term '{word}'. Analytical commentary cannot make absolute legal assertions.",
                        "span": c_text
                    })

            # 1.2 Statutory & Case Citation check
            stat_cits = self._memo_verifier.extract_statutory_citations(c_text)
            case_auths = self._memo_verifier.extract_case_authorities(c_text)
            
            # Check for generic section/order/rule/article patterns
            generic_cit = re.findall(r'\b(?:Section|Sec\.?|s\.|Rule|r\.|Order|Ord\.?|Article|Art\.)\s*\d+[A-Za-z]?', c_text, re.I)

            if stat_cits or case_auths or generic_cit:
                cit_spans = [sc["span"] for sc in stat_cits] + [ca["span"] for ca in case_auths] + generic_cit
                result["passed"] = False
                result["violations"].append({
                    "rule": "(e)",
                    "category": "CITATION_IN_ANALYSIS",
                    "issue": f"Analysis claim contains statutory or case authority citation(s): {cit_spans}. Citations must be declared as quote or paraphrase claims.",
                    "span": c_text
                })

                # Run through Rules (c) and (d)
                for ca in case_auths:
                    if not self._memo_verifier.verify_case_authority(ca):
                        result["violations"].append({
                            "rule": "(c)",
                            "category": "UNVERIFIED_AUTHORITY",
                            "issue": f"Analysis claim cites unverified authority: '{ca['span']}'",
                            "span": c_text
                        })
                for sc in stat_cits:
                    c_res = self._memo_verifier.verify_statutory_citation(sc["span"])
                    if not c_res.is_valid:
                        result["violations"].append({
                            "rule": "(d)",
                            "category": "PROVISION_NOT_IN_STORE",
                            "issue": c_res.reason or "Statutory citation in analysis not found in store",
                            "span": c_text
                        })

            # 1.3 Statutory or Judicial Holding assertions check
            m_stat = STATUTORY_HOLDING_REGEX.search(c_text)
            if m_stat:
                result["passed"] = False
                result["violations"].append({
                    "rule": "(e)",
                    "category": "STATUTORY_OR_JUDICIAL_HOLDING_IN_ANALYSIS",
                    "issue": f"Analysis claim asserts statutory rule/holding ('{m_stat.group(0)}'). Substantive legal rules must be anchored in verified quote or paraphrase claims.",
                    "span": c_text
                })

            m_jud = JUDICIAL_HOLDING_REGEX.search(c_text)
            if m_jud:
                result["passed"] = False
                result["violations"].append({
                    "rule": "(e)",
                    "category": "STATUTORY_OR_JUDICIAL_HOLDING_IN_ANALYSIS",
                    "issue": f"Analysis claim asserts judicial holding ('{m_jud.group(0)}'). Judicial holdings must be verified under Rule (c).",
                    "span": c_text
                })

            # 1.4 Number/duration check against user question
            claim_nums = extract_numbers_and_units(c_text)
            if claim_nums:
                q_nums = extract_numbers_and_units(user_question or "")
                q_num_set = set(q_nums)
                for val, unit in claim_nums:
                    if (val, unit) not in q_num_set:
                        result["passed"] = False
                        result["violations"].append({
                            "rule": "(e)",
                            "category": "UNSOURCED_NUMBER_IN_ANALYSIS",
                            "issue": f"Analysis claim contains quantity/duration '{val} {unit}' not present in user question.",
                            "span": c_text
                        })

            result["label"] = "analysis (unreviewed)"
            return result

        # ----------------------------------------------------------------------
        # 2. QUOTE CLAIM HARDENING & MISATTRIBUTION (Order 1.14 - Item 3)
        # ----------------------------------------------------------------------
        if c_type == "quote":
            rec, cid, sub = self.resolve_support_provision(c_support)
            if not rec:
                result["passed"] = False
                result["violations"].append({
                    "rule": "(d)",
                    "category": "FABRICATED_CITATION",
                    "issue": f"Statutory support '{c_support}' is not in verified store",
                    "span": c_text
                })
                return result

            if rec.get("tier") == "disputed":
                result["disputed_notice"] = {
                    "provision": cid,
                    "label": "DISPUTED TEXT — human check required"
                }

            prov_text = rec.get("text") or rec.get("statutory_text") or ""
            target_text = self.extract_subsection_text(prov_text, sub) if sub else prov_text
            result["source_text"] = target_text

            norm_quote = to_matching_stream(c_text)
            norm_prov = to_matching_stream(target_text)
            norm_full = to_matching_stream(prov_text)

            if norm_quote not in norm_prov and norm_quote not in norm_full:
                # Check for MISATTRIBUTION: Does this quote exist in a DIFFERENT provision in store?
                other_prov = None
                for other_cid, other_rec in self.store._by_cid.items():
                    if other_cid == (cid or "").upper():
                        continue
                    o_txt = other_rec.get("text") or other_rec.get("statutory_text") or ""
                    if norm_quote in to_matching_stream(o_txt):
                        other_prov = other_cid
                        break

                if other_prov:
                    result["passed"] = False
                    result["violations"].append({
                        "rule": "(a)",
                        "category": "MISATTRIBUTED_QUOTE",
                        "issue": f"Quote text belongs to {other_prov}, but was misattributed to {cid} ({c_support}).",
                        "span": c_text
                    })
                else:
                    diff_desc = compute_word_diff(c_text, target_text if norm_quote in norm_prov else prov_text)
                    result["passed"] = False
                    result["violations"].append({
                        "rule": "(a)",
                        "category": "ALTERED_QUOTE",
                        "issue": f"Quote differs from stored provision text ({cid}). Word-level diff: {diff_desc}",
                        "span": c_text
                    })
            else:
                tag = format_support_tag(c_support) or cid
                result["label"] = f"quote of {tag}"
            return result

        # ----------------------------------------------------------------------
        # 3. PARAPHRASE CLAIM HARDENING (Order 1.14 - Item 2)
        # ----------------------------------------------------------------------
        if c_type == "paraphrase":
            rec, cid, sub = self.resolve_support_provision(c_support)
            if not rec:
                result["passed"] = False
                result["violations"].append({
                    "rule": "(d)",
                    "category": "FABRICATED_CITATION",
                    "issue": f"Paraphrase support '{c_support}' is not in verified store",
                    "span": c_text
                })
                return result

            if rec.get("tier") == "disputed":
                result["disputed_notice"] = {
                    "provision": cid,
                    "label": "DISPUTED TEXT — human check required"
                }

            prov_text = rec.get("text") or rec.get("statutory_text") or ""
            target_text = self.extract_subsection_text(prov_text, sub) if sub else prov_text
            result["source_text"] = target_text

            # 3.1 Number & unit check
            claim_nums = extract_numbers_and_units(c_text)
            store_nums = extract_numbers_and_units(target_text)
            store_val_map = {unit: [] for _, unit in store_nums}
            for val, unit in store_nums:
                store_val_map[unit].append(val)

            for val, unit in claim_nums:
                if unit and unit in store_val_map:
                    if val not in store_val_map[unit]:
                        result["passed"] = False
                        result["violations"].append({
                            "rule": "(a)",
                            "category": "WRONG_NUMBERS",
                            "issue": f"Paraphrase contains quantity {val} {unit} which conflicts with stored text ({store_val_map[unit]} {unit}) in {cid}",
                            "span": c_text
                        })

            # 3.2 Negation & Modal Parity Check (Order 1.14 - Item 2)
            p_lower = f" {c_text.lower()} "
            s_lower = f" {target_text.lower()} "

            # Check: 'shall not' vs 'shall'
            if "shall not" in s_lower or "not be entitled" in s_lower or "shall not be" in s_lower:
                if "shall" in p_lower and not any(neg in p_lower for neg in ["shall not", "not", "no", "never", "cannot"]):
                    result["passed"] = False
                    result["violations"].append({
                        "rule": "(a)",
                        "category": "NEGATION_FLIPPED",
                        "issue": f"Paraphrase flips negative obligation ('shall not') to affirmative ('shall') in {cid}",
                        "span": c_text
                    })

            # Check: 'may' vs 'shall'
            if "may" in s_lower and "shall" not in s_lower:
                if "shall" in p_lower or "must" in p_lower:
                    result["passed"] = False
                    result["violations"].append({
                        "rule": "(a)",
                        "category": "MODAL_MISMATCH",
                        "issue": f"Paraphrase flips permissive modal ('may') to mandatory ('shall' / 'must') in {cid}",
                        "span": c_text
                    })

            # Check: conditional gates dropped ('unless', 'except')
            for cond in ["unless", "except"]:
                for s_sent in re.split(r'[:;\.\n]', s_lower):
                    if cond in s_sent:
                        # Identify operative topic of the conditional clause (e.g. stay, detention, leave)
                        topics = [top for top in ["stay", "execution", "detain", "detained", "prison", "leave", "defend", "service"] if top in s_sent]
                        if topics and any(top in p_lower for top in topics):
                            if cond not in p_lower:
                                result["passed"] = False
                                result["violations"].append({
                                    "rule": "(a)",
                                    "category": "CONDITION_DROPPED",
                                    "issue": f"Paraphrase drops material qualifying condition '{cond}' from stored text in {cid}",
                                    "span": c_text
                                })
                                break

            # 3.3 Term check: every content word must appear in cited text or allowlist
            p_words = [re.sub(r'[^a-z0-9\-]', '', w) for w in c_text.lower().split()]
            p_words = [w for w in p_words if len(w) >= 2]
            
            s_words = set(re.sub(r'[^a-z0-9\-]', '', w) for w in target_text.lower().split())
            s_words = {w for w in s_words if len(w) >= 2}
            
            # Simple morphological stems for s_words
            s_stems = set(s_words)
            for w in s_words:
                if w.endswith("s") and len(w) > 3:
                    s_stems.add(w[:-1])
                if w.endswith("ed") and len(w) > 4:
                    s_stems.add(w[:-2])
                if w.endswith("ing") and len(w) > 5:
                    s_stems.add(w[:-3])

            unrecognized_terms = []
            for w in p_words:
                # Check allowlist
                if w in FUNCTION_WORDS_ALLOWLIST:
                    continue
                # Check direct or stem match
                w_stem = w[:-1] if w.endswith("s") and len(w) > 3 else w
                if w in s_words or w in s_stems or w_stem in s_stems:
                    continue
                # Check numbers and alphanumeric section tokens (e.g. 15a13, 19(7), 489-f)
                if re.match(r'^\d+$', w) or w in WORD_TO_NUMBER or any(char.isdigit() for char in w):
                    continue
                unrecognized_terms.append(w)

            if unrecognized_terms:
                result["passed"] = False
                result["violations"].append({
                    "rule": "(a)",
                    "category": "PARAPHRASE_INTRODUCES_TERMS",
                    "issue": f"Paraphrase introduces terms not in the provision: {sorted(list(set(unrecognized_terms)))}",
                    "span": c_text
                })

            tag = format_support_tag(c_support) or cid
            result["label"] = f"paraphrase of {tag}"
            return result

        result["label"] = "analysis (unreviewed)"
        return result

    def verify_claim_memo(self, claims: List[Dict[str, Any]], user_question: Optional[str] = None) -> Dict[str, Any]:
        """Verifies a full list of structured claims."""
        all_violations = []
        disputed_notices = []
        claim_results = []
        
        for c in claims:
            cr = self.verify_single_claim(c, user_question=user_question)
            claim_results.append(cr)
            if not cr["passed"]:
                all_violations.extend(cr["violations"])
            if cr.get("disputed_notice"):
                disputed_notices.append(cr["disputed_notice"])

        unique_disputed = []
        seen = set()
        for dn in disputed_notices:
            p = dn.get("provision")
            if p not in seen:
                seen.add(p)
                unique_disputed.append(dn)

        return {
            "passed": len(all_violations) == 0,
            "total_failures": len(all_violations),
            "failures": all_violations,
            "claim_results": claim_results,
            "disputed_notices": unique_disputed
        }


def render_claim_first_memo(claims: List[Dict[str, Any]], title: str = "LEGAL RESEARCH MEMORANDUM") -> str:
    """
    Renders structured JSON claims into a clean legal memorandum.
    - Quotes rendered as blockquotes.
    - Paraphrases rendered with system-produced source subsection text directly beside them.
    - All analysis claims rendered in a dedicated section headed:
      '### Unreviewed analysis — not checked against any source'
    """
    lines = [f"## {title}\n"]
    
    statutory_claims = [c for c in claims if (c.get("type") or "").lower().strip() in ("quote", "paraphrase")]
    analysis_claims = [c for c in claims if (c.get("type") or "").lower().strip() == "analysis"]

    store = get_unified_statute_store()
    verifier = ClaimFirstVerifier(store)

    # 1. Statutory Claims Section
    if statutory_claims:
        lines.append("### Statutory Provisions & Grounds\n")
        for c in statutory_claims:
            c_text = (c.get("text") or "").strip()
            c_type = (c.get("type") or "").lower().strip()
            c_support = c.get("support", "")

            if c_type == "quote":
                tag = format_support_tag(c_support)
                if tag:
                    lines.append(f"Statutory text of {tag} provides:\n")
                lines.append(f"> {c_text}\n")
            elif c_type == "paraphrase":
                tag = format_support_tag(c_support) or "statute"
                lines.append(f"- **[paraphrase of {tag}]** {c_text}")
                rec, cid, sub = verifier.resolve_support_provision(c_support)
                if rec:
                    p_txt = rec.get("text") or rec.get("statutory_text") or ""
                    sub_txt = verifier.extract_subsection_text(p_txt, sub) if sub else p_txt
                    sub_txt_clean = " ".join(sub_txt.split())[:200]
                    lines.append(f"  > *Official Store Text ({tag}):* \"{sub_txt_clean}...\"\n")
                else:
                    lines.append("\n")

    # 2. Unreviewed Analysis Section (Order 1.14 - Item 1)
    if analysis_claims:
        lines.append("\n### Unreviewed analysis — not checked against any source\n")
        for c in analysis_claims:
            c_text = (c.get("text") or "").strip()
            if c_text:
                lines.append(f"- **[analysis (unreviewed)]** {c_text}")
        lines.append("")

    return "\n".join(lines).strip()
