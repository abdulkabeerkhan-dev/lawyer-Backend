"""
tests/test_gold_set_leak.py

Continuous Integration Leak Prevention Test:
Guarantees that no gold-set citation appears in:
1. Application source code (main.py, core/*.py)
2. Prompt strings or guardrail dictionaries
3. Legal skeleton files (data/legal_skeleton/*.json)
4. Statute versions (data/statute_versions/*.json)
5. Agent-created curated corpus records (data/curated_historical_cases.json)

Fails CI if benchmark ground truth has leaked into production code or retrieval stores.
"""

import os
import re
import json
import unittest
from typing import Set, List

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def extract_gold_set_citations() -> Set[str]:
    gold_path = os.path.join(WORKSPACE_DIR, "eval", "gold_set_examples.json")
    if not os.path.exists(gold_path):
        return set()
        
    with open(gold_path, "r", encoding="utf-8") as f:
        gold_data = json.load(f)
        
    citations = set()
    for case in gold_data:
        for auth in case.get("required_authorities", []):
            raw = auth.get("citation", "")
            # Find year + journal + page patterns (e.g. 2024 SCMR 1218, PLD 2000 FSC 1)
            matches = re.findall(r'\b(?:\d{4}\s+[A-Za-z]+(?:\s+[A-Za-z]+)?\s+\d+|[A-Za-z]+\s+\d{4}\s+[A-Za-z]+\s+\d+)\b', raw)
            for m in matches:
                citations.add(m.strip())
    return citations

class TestGoldSetLeakPrevention(unittest.TestCase):
    def setUp(self):
        self.gold_citations = extract_gold_set_citations()
        self.assertGreater(len(self.gold_citations), 0, "Gold set citations must be non-empty.")

    def test_no_gold_citations_in_main_application_code(self):
        """Scans main.py for hardcoded gold set citations."""
        main_path = os.path.join(WORKSPACE_DIR, "main.py")
        with open(main_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        leaks = []
        for cit in self.gold_citations:
            # Check space-delimited and underscore-delimited variants
            cit_norm = cit.lower()
            cit_under = cit_norm.replace(" ", "_")
            if cit_norm in content.lower() or cit_under in content.lower():
                leaks.append(cit)
                
        self.assertEqual(leaks, [], f"LEAK DETECTED in main.py: Gold set citations hardcoded in application code: {leaks}")

    def test_no_gold_citations_in_core_modules(self):
        """Scans core/*.py (excluding test/eval modules) for gold citations."""
        core_dir = os.path.join(WORKSPACE_DIR, "core")
        leaks = []
        for root, _, files in os.walk(core_dir):
            for file in files:
                if file.endswith(".py") and not file.startswith("test_"):
                    fpath = os.path.join(root, file)
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    for cit in self.gold_citations:
                        cit_norm = cit.lower()
                        cit_under = cit_norm.replace(" ", "_")
                        if cit_norm in content.lower() or cit_under in content.lower():
                            leaks.append((file, cit))
                            
        self.assertEqual(leaks, [], f"LEAK DETECTED in core modules: {leaks}")

    def test_no_gold_citations_in_skeleton_files(self):
        """Scans data/legal_skeleton/*.json for gold set citations."""
        skel_dir = os.path.join(WORKSPACE_DIR, "data", "legal_skeleton")
        leaks = []
        for root, _, files in os.walk(skel_dir):
            for file in files:
                if file.endswith(".json"):
                    fpath = os.path.join(root, file)
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    for cit in self.gold_citations:
                        cit_norm = cit.lower()
                        cit_under = cit_norm.replace(" ", "_")
                        if cit_norm in content.lower() or cit_under in content.lower():
                            leaks.append((file, cit))
                            
        self.assertEqual(leaks, [], f"LEAK DETECTED in legal skeleton data: {leaks}")

    def test_no_gold_citations_in_curated_historical_cases(self):
        """Ensures data/curated_historical_cases.json does not contain gold set authorities."""
        curated_path = os.path.join(WORKSPACE_DIR, "data", "curated_historical_cases.json")
        if not os.path.exists(curated_path):
            return
            
        with open(curated_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        leaks = []
        for cit in self.gold_citations:
            cit_norm = cit.lower()
            cit_under = cit_norm.replace(" ", "_")
            if cit_norm in content.lower() or cit_under in content.lower():
                leaks.append(cit)
                
        self.assertEqual(leaks, [], f"LEAK DETECTED in curated_historical_cases.json: {leaks}")

    def test_no_gold_citations_in_statute_versions(self):
        """Scans data/statute_versions/*.json for gold set citations."""
        vers_dir = os.path.join(WORKSPACE_DIR, "data", "statute_versions")
        leaks = []
        for root, _, files in os.walk(vers_dir):
            for file in files:
                if file.endswith(".json") and not file.startswith("audit_"):
                    fpath = os.path.join(root, file)
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    for cit in self.gold_citations:
                        cit_norm = cit.lower()
                        cit_under = cit_norm.replace(" ", "_")
                        if cit_norm in content.lower() or cit_under in content.lower():
                            leaks.append((file, cit))
                            
        self.assertEqual(leaks, [], f"LEAK DETECTED in statute versions data: {leaks}")

if __name__ == "__main__":
    unittest.main()
