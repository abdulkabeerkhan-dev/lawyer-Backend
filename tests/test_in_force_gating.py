"""
tests/test_in_force_gating.py

Tests in_force gating for statutory provisions:
1. Verifies that Limitation Act Article 182 is stored with in_force=False.
2. Verifies that StatuteInjector refuses to quote in_force=False provisions as operative law.
3. Verifies that in_force=True provisions are injected with operative text.
"""

import os
import sys
import json
import pytest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)

from legal_ai.statutes.statute_injector import StatuteInjector

def test_article_182_marked_false():
    p = os.path.join(REPO_DIR, "data", "unified_statutes", "LIMITATION_1908.json")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    art182 = [r for r in data if r.get("canonical_id") == "LIMITATION_1908_ART_182"][0]
    assert art182.get("in_force") is False, f"Expected in_force=False, got {art182.get('in_force')}"

def test_injector_refuses_to_quote_repealed_article_182():
    injector = StatuteInjector(workspace_root=REPO_DIR)
    
    # Create mock plan requesting Article 182
    class MockPlan:
        premise_corrections = []
        provisions = ["Article 182 Limitation Act"]

    res = injector.inject_statutory_framework(query_plan=MockPlan(), query_text="What is limitation under Article 182?")
    block = res["statute_block"]

    # Verify refusal banner is present
    assert "CRITICAL REFUSAL" in block
    assert "IS NOT IN FORCE (REPEALED / OMITTED)" in block
    assert "refuses to quote repealed or omitted provisions as operative law" in block
    assert "[REPEALED / OMITTED - NOT IN FORCE" in block

def test_injector_quotes_in_force_provision():
    injector = StatuteInjector(workspace_root=REPO_DIR)
    
    class MockPlan:
        premise_corrections = []
        provisions = ["Order XXXIX Rule 2A CPC"]

    res = injector.inject_statutory_framework(query_plan=MockPlan(), query_text="What is duration of interim injunction?")
    block = res["statute_block"]

    assert "CRITICAL REFUSAL" not in block
    assert "Verbatim Bare-Act Text in Force:" in block
    assert "fifteen days" in block

if __name__ == "__main__":
    test_article_182_marked_false()
    test_injector_refuses_to_quote_repealed_article_182()
    test_injector_quotes_in_force_provision()
    print("ALL IN_FORCE GATING TESTS PASSED!")
