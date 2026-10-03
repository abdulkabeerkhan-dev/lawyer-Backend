"""
tests/test_anti_tamper_scrubbers.py

CI Anti-Tamper Enforcement:
Fails CI if any regex or string replacements derived from audited outputs
(such as TheSubstratum, IntactTest, Oppressionvs, etc.) are present in
production application code.
"""

import os
import unittest

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FORBIDDEN_AUDITED_STRINGS = [
    "TheSubstratum",
    "IntactTest",
    "Oppressionvs",
    "ofmismanagement",
    "foundno",
    "unilateralwishful"
]

class TestAntiTamperScrubbers(unittest.TestCase):
    def test_no_eval_scrubbers_in_production_code(self):
        scanned_dirs = [
            os.path.join(WORKSPACE_DIR, "main.py"),
            os.path.join(WORKSPACE_DIR, "core")
        ]
        
        violations = []
        for target in scanned_dirs:
            if os.path.isfile(target):
                with open(target, "r", encoding="utf-8") as f:
                    content = f.read()
                for token in FORBIDDEN_AUDITED_STRINGS:
                    if token.lower() in content.lower():
                        violations.append((os.path.basename(target), token))
            elif os.path.isdir(target):
                for root, _, files in os.walk(target):
                    for fn in files:
                        if fn.endswith(".py"):
                            fpath = os.path.join(root, fn)
                            with open(fpath, "r", encoding="utf-8") as f:
                                content = f.read()
                            for token in FORBIDDEN_AUDITED_STRINGS:
                                if token.lower() in content.lower():
                                    violations.append((fn, token))

        self.assertEqual(
            violations, [],
            f"CI ANTI-TAMPER VIOLATION: Hardcoded eval output scrubbers found in production code: {violations}"
        )

if __name__ == "__main__":
    unittest.main()
