"""
tests/test_anti_tamper_scrubbers.py

CI Anti-Tamper Enforcement:
Replaces word-list anti-tamper tests with a general AST rule:
1. Fails CI if ANY post-generation text substitution in the codebase is not on
   the approved registry with a documented purpose.
2. Fails CI if any hardcoded word-patching / eval scrubbers (e.g. TheSubstratum,
   IntactTest, Oppressionvs, etc.) exist in production code.
3. Tests delimiter-only quote sanitizer to ensure it never causes run-together words.
"""

import os
import ast
import re
import unittest

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Authoritative registry of approved post-generation text transformations with documented legal purposes
APPROVED_POST_PROCESSING_SUBSTITUTIONS = {
    ('core/quote_verifier.py', 'sanitize_unverified_quotes'): (
        'Delimiter-only stripping of ungrounded quotation marks around unverified quotes without modifying text.'
    ),
    ('core/quote_verifier.py', 'verify_text_quotes'): (
        'Normalizes quote marks for audit comparison against retrieved text.'
    ),
    ('core/quote_verifier.py', 'normalize_text'): (
        'Whitespace and punctuation normalization strictly for comparison matching.'
    ),
    ('core/quote_verifier.py', 'extract_quotes_from_text'): (
        'Strips bounding quotation mark delimiters from extracted candidate quotes.'
    ),
    ('core/legal_guardrails.py', 'sanitize_unverified_quotes'): (
        'Delimiter-only stripping of ungrounded quotation marks around unverified quotes without modifying text.'
    ),
    ('core/legal_guardrails.py', 'strip_agent_narration'): (
        'Strips internal reasoning scratchpads (<thinking>) and assistant conversational prefixes.'
    ),
    ('core/legal_guardrails.py', 'fail_closed_citation_grounding'): (
        'Fail-closed removal or redaction of citations not present in retrieved context chunks.'
    ),
    ('core/legal_guardrails.py', 'check_memo_completeness'): (
        'Strips <<<CARDS>>> payload block when checking mandatory section headers.'
    ),
    ('core/legal_guardrails.py', 'normalize_statute_citation'): (
        'Canonicalizes statutory section identifiers for authority matching.'
    ),
    ('core/legal_guardrails.py', '_norm'): (
        'Alphanumeric normalization strictly for case-insensitive canonical comparison.'
    ),
    ('core/legal_guardrails.py', 'lint_legal_output'): (
        'Citation normalization for automated lint checking against retrieved context.'
    ),
    ('core/legal_guardrails.py', 'passes_positive_anchor_test'): (
        'Strips escaped backslashes for positive anchor substring comparison.'
    ),
    ('core/legal_guardrails.py', 'verify_case_identity'): (
        'Normalizes party name delimiters for case identity verification.'
    ),
    ('core/legal_guardrails.py', 'count_real_cases_discussed'): (
        'Collapses whitespace in citation strings for unique case counting.'
    ),
}

# Forbidden evaluation scrubbers and ad-hoc word patches
FORBIDDEN_EVAL_SCRUBBERS = [
    'TheSubstratum',
    'IntactTest',
    'Oppressionvs',
    'ofmismanagement',
    'foundno',
    'unilateralwishful',
]

class TestAntiTamperScrubbers(unittest.TestCase):
    def test_all_post_generation_substitutions_are_approved(self):
        """AST Rule: Fail if any substitution occurs in post-processing without approval and documented purpose."""
        target_files = ['core/quote_verifier.py', 'core/legal_guardrails.py']
        unapproved = []

        for rel_path in target_files:
            full_path = os.path.join(WORKSPACE_DIR, rel_path)
            with open(full_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=rel_path)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    fn_name = node.name
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            func = child.func
                            is_sub = False
                            if isinstance(func, ast.Attribute) and func.attr in ('sub', 'subn', 'replace'):
                                is_sub = True
                            if is_sub:
                                key = (rel_path.replace(os.sep, '/'), fn_name)
                                if key not in APPROVED_POST_PROCESSING_SUBSTITUTIONS:
                                    unapproved.append((key, child.lineno, func.attr))

        self.assertEqual(
            unapproved, [],
            f'CI ANTI-TAMPER VIOLATION: Unapproved text substitution found in post-processing code: {unapproved}. '
            'Every substitution must be in APPROVED_POST_PROCESSING_SUBSTITUTIONS with a documented purpose.'
        )

    def test_documented_purpose_validity(self):
        """Asserts that every approved substitution has a documented, non-trivial purpose."""
        for key, purpose in APPROVED_POST_PROCESSING_SUBSTITUTIONS.items():
            self.assertIsInstance(purpose, str)
            self.assertGreaterEqual(
                len(purpose.strip()), 20,
                f'Approved substitution {key} lacks an adequate documented purpose.'
            )

    def test_zero_eval_scrubbers_in_codebase(self):
        """Asserts zero hardcoded evaluation scrubbers or ad-hoc word-patch tokens in production code."""
        scanned_paths = [
            os.path.join(WORKSPACE_DIR, 'main.py'),
            os.path.join(WORKSPACE_DIR, 'core')
        ]
        violations = []

        for target in scanned_paths:
            if os.path.isfile(target):
                with open(target, 'r', encoding='utf-8') as f:
                    content = f.read()
                for token in FORBIDDEN_EVAL_SCRUBBERS:
                    if token.lower() in content.lower():
                        violations.append((os.path.basename(target), token))
            elif os.path.isdir(target):
                for root, _, files in os.walk(target):
                    for fn in files:
                        if fn.endswith('.py'):
                            fpath = os.path.join(root, fn)
                            with open(fpath, 'r', encoding='utf-8') as f:
                                content = f.read()
                            for token in FORBIDDEN_EVAL_SCRUBBERS:
                                if token.lower() in content.lower():
                                    violations.append((fn, token))

        self.assertEqual(
            violations, [],
            f'CI ANTI-TAMPER VIOLATION: Hardcoded evaluation scrubbers detected: {violations}'
        )

    def test_quote_sanitizer_delimiter_only_preserves_spaces(self):
        """Root cause fix test: quotation mark removal must not merge words or corrupt surrounding whitespace."""
        from core.quote_verifier import sanitize_unverified_quotes as qv_sanitize
        from core.legal_guardrails import sanitize_unverified_quotes as lg_sanitize

        test_cases = [
            (
                'The Supreme Court in "XYZ Case" held that the rule was intact.',
                ['XYZ Case'],
                'The Supreme Court in XYZ Case held that the rule was intact.'
            ),
            (
                'Under Section 19 of the Ordinance, "financial institution" is defined.',
                ['financial institution'],
                'Under Section 19 of the Ordinance, financial institution is defined.'
            ),
            (
                'The term “bona fide” purchaser applies.',
                ['bona fide'],
                'The term bona fide purchaser applies.'
            ),
        ]

        for original, unverified_list, expected in test_cases:
            res_qv = qv_sanitize(original, unverified_list)
            res_lg = lg_sanitize(original, unverified_list)
            self.assertEqual(res_qv, expected, f'Quote verifier failed to preserve spaces: {res_qv} != {expected}')
            self.assertEqual(res_lg, expected, f'Legal guardrails failed to preserve spaces: {res_lg} != {expected}')

if __name__ == '__main__':
    unittest.main()
