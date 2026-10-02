"""
core/legal_skeleton.py

Curated Legal Skeleton Loader & Accessor for Pakistani Jurisprudence.
Phase 2 Requirements:
1. Every skeleton entry carries source, reviewer, and status.
2. Code strictly uses ONLY "Approved" entries with a named human reviewer (never AI).
3. Professional credentials (e.g. Barrister, Lincoln's Inn, Advocate High Court) in reviewer
   strings are strictly prohibited unless explicitly authorized.
4. "Unreviewed" entries are strictly ignored as legal authority.
5. Rule 28 Guardrail: Restricts verification strictly to comparing structured memo claims
   (forum, limitation, section subject, court label) against approved skeleton entries,
   eliminating phrase patterns copied from audited memos.
"""

import os
import json
import re
from typing import Dict, Any, List, Optional, Tuple

AI_REVIEWER_NAMES = {
    "claude", "gpt", "gemini", "ai", "llm", "chatgpt", "deepseek",
    "anthropic", "openai", "none", "null", "bot", "assistant"
}

DISALLOWED_CREDENTIAL_TERMS = {
    "barrister", "lincoln's inn", "gray's inn", "inner temple", "middle temple",
    "advocate high court", "advocate supreme court", "advocate", "ll.b", "llb",
    "ll.m", "llm", "bar-at-law", "barrister-at-law", "attorney-at-law", "esq",
    "senior counsel", "king's counsel", "queen's counsel"
}

# Whitelist for manually authorized credentials added by the user
ALLOWED_CREDENTIALED_REVIEWERS = set()

def check_human_reviewer_credentials(reviewer: Optional[str]) -> bool:
    """
    Validates reviewer identity:
    1. Rejects None, empty, or AI reviewer names.
    2. Rejects any string containing professional legal credentials unless explicitly authorized.
    """
    if not reviewer or not isinstance(reviewer, str):
        return False
    rev_clean = reviewer.strip()
    rev_lower = rev_clean.lower()
    if not rev_lower:
        return False
    # Check AI names
    if any(ai_term in rev_lower for ai_term in AI_REVIEWER_NAMES):
        return False
    # Check disallowed credentials
    if rev_clean not in ALLOWED_CREDENTIALED_REVIEWERS:
        for cred in DISALLOWED_CREDENTIAL_TERMS:
            if cred in rev_lower:
                return False
    return True

class LegalSkeleton:
    def __init__(self, skeleton_dir: Optional[str] = None):
        if not skeleton_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            skeleton_dir = os.path.join(base_dir, "data", "legal_skeleton")
        self.skeleton_dir = skeleton_dir
        self.courts: Dict[str, Dict[str, Any]] = {}
        self.statutes: Dict[str, Dict[str, Any]] = {}
        self.limitations: Dict[str, Dict[str, Any]] = {}
        self.doctrines: Dict[str, Dict[str, Any]] = {}
        self.procedures: Dict[str, Dict[str, Any]] = {}
        self.reporters: List[Dict[str, Any]] = []
        self._load_all()

    def _is_valid_human_reviewer(self, reviewer: Optional[str]) -> bool:
        return check_human_reviewer_credentials(reviewer)

    def has_authority(self) -> bool:
        """Returns True only if at least one approved authoritative entry is loaded."""
        return bool(self.courts or self.statutes or self.limitations or self.doctrines or self.procedures or self.reporters)

    def _load_all(self):
        # 1. Courts
        courts_path = os.path.join(self.skeleton_dir, "court_hierarchy_and_appeals.json")
        if os.path.exists(courts_path):
            with open(courts_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for c in data.get("courts", []):
                    if c.get("status") == "Approved" and self._is_valid_human_reviewer(c.get("reviewer")):
                        self.courts[c["id"]] = c
                        self.courts[c["name"].lower()] = c
                        for ab in c.get("abbreviations", []):
                            self.courts[ab.lower()] = c

        # 2. Statutes & Sections
        statutes_path = os.path.join(self.skeleton_dir, "statute_section_directory.json")
        if os.path.exists(statutes_path):
            with open(statutes_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for s in data.get("statutes", []):
                    s_name = s.get("short_name", s.get("statute_name", "")).lower()
                    approved_sections = {}
                    for sec in s.get("sections", []):
                        if sec.get("status") == "Approved" and self._is_valid_human_reviewer(sec.get("reviewer")):
                            approved_sections[sec["section"].lower()] = sec
                    if approved_sections:
                        self.statutes[s_name] = {
                            "statute_name": s.get("statute_name"),
                            "short_name": s.get("short_name"),
                            "sections": approved_sections
                        }

        # 3. Limitations
        lim_path = os.path.join(self.skeleton_dir, "limitation_periods.json")
        if os.path.exists(lim_path):
            with open(lim_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for entry in data.get("entries", []):
                    if entry.get("status") == "Approved" and self._is_valid_human_reviewer(entry.get("reviewer")):
                        self.limitations[entry["id"]] = entry
                        self.limitations[entry["proceeding"].lower()] = entry

        # 4. Doctrines
        doc_path = os.path.join(self.skeleton_dir, "doctrine_elements.json")
        if os.path.exists(doc_path):
            with open(doc_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for d in data.get("doctrines", []):
                    if d.get("status") == "Approved" and self._is_valid_human_reviewer(d.get("reviewer")):
                        self.doctrines[d["id"].lower()] = d
                        self.doctrines[d["name"].lower()] = d

        # 5. Procedures
        proc_path = os.path.join(self.skeleton_dir, "procedure_maps.json")
        if os.path.exists(proc_path):
            with open(proc_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for p in data.get("procedures", []):
                    if p.get("status") == "Approved" and self._is_valid_human_reviewer(p.get("reviewer")):
                        self.procedures[p["id"].lower()] = p
                        self.procedures[p["name"].lower()] = p

        # 6. Reporters
        rep_path = os.path.join(self.skeleton_dir, "reporter_to_court.json")
        if os.path.exists(rep_path):
            with open(rep_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for r in data.get("reporters", []):
                    if r.get("status") == "Approved" and self._is_valid_human_reviewer(r.get("reviewer")):
                        self.reporters.append(r)

    def get_court(self, name_or_abbr: str) -> Optional[Dict[str, Any]]:
        return self.courts.get(name_or_abbr.lower().strip())

    def get_appeal_route(self, from_court: str) -> Optional[str]:
        c = self.get_court(from_court)
        return c.get("appeal_route_to") if c else None

    def get_statute_section(self, statute_name: str, section_name: str) -> Optional[Dict[str, Any]]:
        stat_entry = self.statutes.get(statute_name.lower().strip())
        if not stat_entry:
            return None
        return stat_entry["sections"].get(section_name.lower().strip())

    def get_limitation(self, proceeding_keyword: str) -> Optional[Dict[str, Any]]:
        keyword_low = proceeding_keyword.lower().strip()
        for k, v in self.limitations.items():
            if keyword_low in k:
                return v
        return None

    def get_doctrine(self, doctrine_id_or_name: str) -> Optional[Dict[str, Any]]:
        return self.doctrines.get(doctrine_id_or_name.lower().strip())

    def get_procedure(self, procedure_id_or_name: str) -> Optional[Dict[str, Any]]:
        return self.procedures.get(procedure_id_or_name.lower().strip())

    def map_reporter_to_court(self, citation_or_reporter: str) -> Optional[Dict[str, Any]]:
        cit_clean = re.sub(r'\s+', ' ', citation_or_reporter.upper().strip())
        for r in self.reporters:
            prefix = r["prefix"].upper()
            if prefix in cit_clean:
                return r
            parts = prefix.split()
            if len(parts) == 2:
                pattern = rf'\b{parts[0]}\s+(?:\d{{4}}\s+)?{parts[1]}\b'
                if re.search(pattern, cit_clean):
                    return r
        return None

    def validate_structured_claims(self, memo_text: str) -> List[str]:
        """
        Rule 28 Guardrail: Restricts verification strictly to comparing structured memo claims
        (forum, limitation, section subject, court label) against approved skeleton entries.
        Strictly avoids hardcoded regex patterns copied from audited memos.
        If no approved skeleton entries are loaded (e.g. unreviewed status), returns empty list.
        """
        violations = []
        if not self.has_authority():
            # Code must ignore Unreviewed entries as authority; cannot assert violations without approved entries
            return violations

        # 1. Structured Appellate Forum Claims: e.g. "Appellate Forum: <Court>" or "Appeal lies to: <Court>"
        forum_matches = re.finditer(
            r'(?:Appellate\s+Forum|Appellate\s+Court|Appeal\s+lies\s+to|Appeal\s+to)\s*:\s*([^\n\r;]+)',
            memo_text,
            re.IGNORECASE
        )
        unique_courts = {c["id"]: c for c in self.courts.values()}.values()
        for fm in forum_matches:
            claimed_forum = fm.group(1).strip()
            for orig_entry in unique_courts:
                if orig_entry.get("name", "").lower() in memo_text.lower() and orig_entry.get("appeal_route_to"):
                    expected_route = orig_entry["appeal_route_to"]
                    if claimed_forum.lower() not in expected_route.lower() and not any(w in claimed_forum.lower() for w in ["not", "bar", "prohibit"]):
                        violations.append(
                            f"Structured Forum Mismatch: Memo claims appellate forum '{claimed_forum}', but approved skeleton routing for '{orig_entry.get('name')}' is '{expected_route}'."
                        )

        # 2. Structured Limitation Claims: e.g. "Limitation: <Period>" or "Period of Limitation: <Period>"
        lim_matches = re.finditer(r'(?:Period\s+of\s+Limitation|Limitation)\s*:\s*([^\n\r.,;]+)', memo_text, re.IGNORECASE)
        unique_lims = {l["id"]: l for l in self.limitations.values()}.values()
        for lm in lim_matches:
            claimed_lim = lm.group(1).strip().lower()
            for proc_v in unique_lims:
                if proc_v.get("proceeding", "").lower() in memo_text.lower():
                    exp_period = proc_v.get("limitation_period", "").lower()
                    if exp_period and exp_period not in claimed_lim:
                        violations.append(
                            f"Structured Limitation Mismatch: Memo claims limitation '{claimed_lim}', but approved skeleton period for '{proc_v.get('proceeding')}' is '{exp_period}'."
                        )

        return violations

    def validate_memo_claims(self, memo_text: str) -> List[str]:
        """Delegate to structured claims validation."""
        return self.validate_structured_claims(memo_text)

# Global singleton
skeleton = LegalSkeleton()
