"""
scripts/classify_corpus_trust.py

Mission 1 & 1.1 / 1.2 Corpus Trust Classifier
Deterministic categorization across controlled vocabularies and gold regression fixtures:
- authentic clean judgments -> trusted
- portal chrome / scraping artifacts / listing tables / sync stubs -> rejected
- reciprocal swaps / shifted sequences / displaced text -> quarantined
- repairable title / contradictory title on verified text -> restricted
- page slip with verified parties -> restricted
"""

import re
from typing import Dict, Any, Optional

CLASSIFIER_VERSION = "2.0.0"

def _normalize_tokens(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).strip()

def _extract_citation_parts(cit: str) -> Optional[Dict[str, str]]:
    if not cit:
        return None
    clean = re.sub(r'\s+', ' ', cit.strip().upper())
    clean = clean.replace("SUPREME COURT", "SC")
    m1 = re.search(r'\b(19\d\d|20\d\d)\s+([A-Z\s]+?)\s+(\d+)\b', clean)
    if m1:
        rep = re.sub(r'\s+', '', m1.group(2))
        return {"year": m1.group(1), "reporter": rep, "page": m1.group(3)}
    m2 = re.search(r'\b([A-Z\s]+?)\s+(19\d\d|20\d\d)\s+(?:SC|LAHORE|QUETTA|KARACHI|PESHAWAR)?\s*(\d+)\b', clean)
    if m2:
        rep = re.sub(r'\s+', '', m2.group(1))
        return {"year": m2.group(2), "reporter": rep, "page": m2.group(3)}
    return None

def _extract_header_parties(full_text: str) -> Optional[str]:
    lines = [l.strip() for l in full_text.splitlines()[:25] if l.strip()]
    for line in lines:
        if re.search(r'\b(?:versus|vs\.?|v\.)\b', line, re.IGNORECASE):
            m = re.split(r'\s*(?:---|–|\s+)(?:versus|vs\.?|v\.)\s*', line, flags=re.IGNORECASE)
            if len(m) >= 2:
                p1 = " ".join(m[0].split())
                p2 = " ".join(m[1].split())
                p1 = re.sub(r'^(?:[A-Z]\.?\s+)+', '', p1).strip()
                for r in ["Appellant", "Petitioner", "Applicant", "Respondent", "Opposite Party", "and another", "and others"]:
                    p1 = re.sub(r'\b' + r + r'\b', '', p1, flags=re.I).strip(" -")
                    p2 = re.sub(r'\b' + r + r'\b', '', p2, flags=re.I).strip(" -")
                p1 = " ".join(p1.split())
                p2 = " ".join(p2.split())
                if p1 and p2:
                    return f"{p1} v. {p2}"
    return None

def classify_record_trust(record: Dict[str, Any]) -> Dict[str, Any]:
    full_text = (record.get("full_text") or record.get("text") or "").strip()
    title = (record.get("case_title") or record.get("title") or "").strip()
    citation = (record.get("neutral_citation") or record.get("citation") or "").strip()

    res = {
        "classifier_version": CLASSIFIER_VERSION,
        "retrieval_status": "trusted",
        "citation_status": "verified",
        "identity_status": "verified",
        "title_status": "verified",
        "provenance_status": "verified" if record.get("source_url") else "unverified",
        "content_quality": "full_text",
        "header_parties": None,
        "verification_reason": "Clean authentic judgment text matching citation and party headers."
    }

    # 1. Listing table check
    if full_text.startswith("# Citation Title Court") or ("# Citation Title" in full_text[:200]):
        res.update({
            "retrieval_status": "rejected",
            "citation_status": "unverified",
            "identity_status": "unverified",
            "title_status": "unverified",
            "content_quality": "listing_table",
            "verification_reason": "Scraped index or digest table."
        })
        return res

    # 2. Portal chrome / scraping boilerplate check
    chrome_keywords = ["Latest Caselaws from the Journal Section", "Oratier Technologies", "Bookmark this Case", "My Account Feedback"]
    if any(kw in full_text for kw in chrome_keywords):
        res.update({
            "retrieval_status": "rejected",
            "citation_status": "unverified",
            "identity_status": "unverified",
            "title_status": "unverified",
            "content_quality": "portal_chrome",
            "verification_reason": "Scraped website navigation or portal chrome."
        })
        return res

    # 3. Synchronization / stub check
    if "undergoing index synchronization" in full_text.lower() or len(full_text) < 150:
        res.update({
            "retrieval_status": "rejected",
            "citation_status": "unverified",
            "identity_status": "unverified",
            "title_status": "unverified",
            "content_quality": "stub",
            "verification_reason": "Placeholder or incomplete stub record."
        })
        return res

    # Detect headnotes / mixed structure
    is_mixed = False
    judicial_body_words = 0
    if re.search(r'\bHeld\s*,\s*', full_text) or re.search(r'\n\s*(?:ORDER|JUDGMENT)\s*\n', full_text):
        m_body = re.search(r'\n\s*(?:ORDER|JUDGMENT)\s*\n', full_text)
        if m_body:
            is_mixed = True
            body_text = full_text[m_body.end():].strip()
            judicial_body_words = len(body_text.split())
            res["content_quality"] = "mixed"

    # 4. Extract header parties and citation from text
    header_parties = _extract_header_parties(full_text)
    res["header_parties"] = header_parties

    meta_cit = _extract_citation_parts(citation)
    first_lines = "\n".join(full_text.splitlines()[:6])
    body_cit = _extract_citation_parts(first_lines)

    title_norm = _normalize_tokens(title)
    parties_match = False
    if header_parties:
        hp_norm = _normalize_tokens(header_parties)
        hp_words = [w for w in hp_norm.split() if len(w) > 2]
        title_words = [w for w in title_norm.split() if len(w) > 2]
        overlap = set(hp_words).intersection(set(title_words))
        if overlap:
            parties_match = True

    # 5. Contradictory / Displaced identity checks
    if body_cit and meta_cit:
        diff_year = body_cit["year"] != meta_cit["year"]
        diff_rep = body_cit["reporter"] != meta_cit["reporter"]
        diff_page = body_cit["page"] != meta_cit["page"]

        if diff_year or diff_rep or diff_page:
            res["citation_status"] = "mismatch"
            if parties_match:
                res["identity_status"] = "verified"
                res["title_status"] = "verified"
                res["retrieval_status"] = "restricted"
                res["verification_reason"] = "Page/citation mismatch on verified identity. Preserved for restricted analysis."
                return res
            else:
                res["identity_status"] = "conflict"
                res["title_status"] = "contradictory"
                res["retrieval_status"] = "quarantined"
                res["verification_reason"] = "Displaced case identity: internal citation and parties contradict record metadata."
                return res

    # 6. Title checks
    if "civil petition" in title.lower() or "..." in title:
        res["title_status"] = "repairable"
        res["retrieval_status"] = "restricted"
        return res

    if not parties_match and header_parties and meta_cit and body_cit and (meta_cit["page"] == body_cit["page"]):
        res["title_status"] = "contradictory"
        res["retrieval_status"] = "restricted"
        res["verification_reason"] = "Contradictory title on verified judgment text. Metadata repair required."
        return res

    # Mixed body length gate
    if is_mixed:
        if judicial_body_words < 100:
            res["retrieval_status"] = "restricted"
            res["verification_reason"] = "Limited evidence: mixed record with short judicial body (< 100 words). Restricted to prevent headnote fabrication."
        else:
            res["retrieval_status"] = "trusted"
            res["verification_reason"] = "Authentic judicial record with verified body and holdings."

    return res
