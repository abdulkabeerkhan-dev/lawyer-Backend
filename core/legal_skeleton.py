"""
core/legal_skeleton.py

Curated Legal Skeleton Loader & Accessor for Pakistani Jurisprudence.
Enforces Phase 2 requirements:
1. Every skeleton entry carries source, reviewer, and status.
2. Code strictly uses ONLY "Approved" entries with a named human reviewer (never AI).
3. Provides canonical lookups for court hierarchy (post-27th Amendment FCC),
   statute sections, limitations, doctrine elements, and procedure maps.
4. Detects legal routing errors and forbidden procedural claims.
"""

import os
import json
import re
from typing import Dict, Any, List, Optional

AI_REVIEWER_NAMES = {"claude", "gpt", "gemini", "ai", "llm", "chatgpt", "deepseek", "anthropic", "openai", "none", "null"}

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
        if not reviewer or not isinstance(reviewer, str):
            return False
        rev_lower = reviewer.strip().lower()
        if not rev_lower:
            return False
        if any(ai_term in rev_lower for ai_term in AI_REVIEWER_NAMES):
            return False
        return True

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
            # Handle split pattern like "PLD <YEAR> FSC" or "PLD <YEAR> SC"
            parts = prefix.split()
            if len(parts) == 2:
                pattern = rf'\b{parts[0]}\s+(?:\d{{4}}\s+)?{parts[1]}\b'
                if re.search(pattern, cit_clean):
                    return r
        return None

    def validate_memo_claims(self, memo_text: str) -> List[str]:
        """
        Validates a generated memo against curated legal skeleton rules.
        Returns a list of violation messages if any forbidden or incorrect claims appear.
        """
        violations = []
        text_lower = memo_text.lower()

        # 1. Banking court appeal to District Judge or s.109 CPC error
        if ("banking court" in text_lower or "fio" in text_lower):
            if "district judge" in text_lower and not ("not" in text_lower or "barred" in text_lower or "does not lie" in text_lower):
                violations.append("Banking Court decisions cannot be appealed to the District Judge. Under Section 22 FIO 2001, appeal lies strictly to the High Court.")
            if "section 109 cpc" in text_lower or "section 109" in text_lower:
                if not ("not" in text_lower or "never" in text_lower or "does not lie" in text_lower):
                    violations.append("Section 109 CPC governs High Court appeals to the Supreme Court, not Banking Court appeals.")

        # 2. Federal Constitutional Court existence
        if "federal constitutional court" in text_lower and ("proposed" in text_lower or "not established" in text_lower or "pending bill" in text_lower):
            violations.append("Federal Constitutional Court (FCC) was established by the 27th Constitutional Amendment in November 2025 and is not merely proposed.")

        # 3. Section 4 MFLO survival ground
        if "section 4" in text_lower and "mflo" in text_lower:
            if "parliament" in text_lower and ("did not amend" in text_lower or "failed to amend" in text_lower) and "survives" in text_lower:
                if "appeal" not in text_lower:
                    violations.append("Section 4 MFLO survives because an appeal is pending before the Supreme Court Shariat Appellate Bench under Art. 203D(2) proviso, NOT due to parliamentary inaction.")

        return violations

# Global singleton
skeleton = LegalSkeleton()
