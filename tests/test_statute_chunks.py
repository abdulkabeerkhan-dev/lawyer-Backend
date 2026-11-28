"""Chunk lane for long statute provisions (statutes_v3_chunks)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "zilliz")))


def test_chunk_lane_fills_reserved_slots_without_reordering():
    from legal_ai.retrieval.statute_search import fuse_provision_and_chunk_ranks
    main = ["A", "B", "C", "D", "E"]
    assert fuse_provision_and_chunk_ranks(main, ["C", "X", "X", "Y", "Z", "W"], 5) == ["A", "B", "X", "Y", "Z"]
    assert fuse_provision_and_chunk_ranks(main, ["A", "B"], 5) == main          # nothing new: unchanged
    assert fuse_provision_and_chunk_ranks(main, [], 3) == ["A", "B", "C"]


def test_chunks_split_on_subsections_and_carry_the_heading():
    import build_statute_chunks as b
    text = " ".join(f"({i}) " + "The court may pass such order as it deems fit in the matter. " * 6 for i in range(1, 9))
    rows = b.rows_for({"canonical_id": "X_SEC_1", "act_name": "Test Act, 2000", "section": "1",
                       "heading": "Powers", "text": text, "in_force": True})
    assert len(rows) >= 3
    for r in rows:
        assert r["text"].startswith("Test Act, 2000\nSection 1: Powers\n\n")
        assert r["parent_id"] == "X_SEC_1" and len(r["text"]) < 2200
    assert b.rows_for({"canonical_id": "Y", "text": "short", "in_force": True}) == []
    assert b.rows_for({"canonical_id": "Z", "text": text, "in_force": False}) == []


class _Hit(dict):
    pass


class _Client:
    """Main index ranks A, B; the chunk index points at C (not in the main top list)."""

    def __init__(self, chunk_fail=False):
        self.chunk_fail = chunk_fail

    def describe_collection(self, name):
        return {"fields": [{"name": n} for n in ("canonical_id", "in_force", "historical", "omitted", "text")]}

    def hybrid_search(self, collection_name, **kw):
        if collection_name.endswith("_chunks"):
            if self.chunk_fail:
                raise RuntimeError("collection not found")
            return [[_Hit(entity={"parent_id": "C"}, distance=0.9), _Hit(entity={"parent_id": "C"}, distance=0.8)]]
        return [[_Hit(entity={"canonical_id": "A", "text": "a"}, distance=0.5),
                 _Hit(entity={"canonical_id": "B", "text": "b"}, distance=0.4)]]

    def query(self, collection_name, filter, output_fields):
        assert '"C"' in filter
        return [{"canonical_id": "C", "text": "c"}]


def _run(monkeypatch, client):
    from legal_ai.retrieval import statute_search as ss

    async def fake_embed(q, input_type="query"):
        return [0.0] * 1024
    monkeypatch.setattr(ss, "get_zilliz_client", lambda: client)
    monkeypatch.setattr(ss, "get_voyage_embedding", fake_embed)
    monkeypatch.setattr(ss, "_get_collection_fields", lambda c, n: {"canonical_id", "in_force", "historical", "omitted", "text"})
    return [h["canonical_id"] for h in asyncio.run(ss.search_statutes_hybrid("q", top_k=3))]


def test_search_returns_parent_of_matching_chunk(monkeypatch):
    ids = _run(monkeypatch, _Client())
    assert "C" in ids and set(ids) <= {"A", "B", "C"}


def test_search_works_without_the_chunk_collection(monkeypatch):
    assert _run(monkeypatch, _Client(chunk_fail=True)) == ["A", "B"]


def test_claude_usage_is_logged(capsys):
    from legal_ai.config import instrument_usage

    class Usage:
        input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens = 1200, 300, 0, 0

    class Resp:
        model, usage = "claude-x", Usage()

    class Messages:
        async def create(self, **kw):
            return Resp()

    class Client:
        messages = Messages()

    c = instrument_usage(Client())
    assert instrument_usage(c) is c
    asyncio.run(c.messages.create(model="claude-x"))
    assert "[claude-usage] model=claude-x in=1200 out=300" in capsys.readouterr().err


def test_model_compat_for_claude_5_models(monkeypatch):
    from legal_ai.config import apply_model_compat
    monkeypatch.setenv("CLAUDE_EFFORT", "medium")
    new = apply_model_compat({"model": "claude-sonnet-5-5", "temperature": 0.0, "max_tokens": 10})
    assert "temperature" not in new and new["extra_body"]["output_config"] == {"effort": "medium"}
    old = apply_model_compat({"model": "claude-haiku-4-5-20251001", "temperature": 0.0})
    assert old["temperature"] == 0.0 and "extra_body" not in old


def test_answer_calls_use_the_synthesis_model():
    """CLAUDE_SYNTHESIS_MODEL writes the answer; the planner and the reviewer keep CLAUDE_MODEL."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    qp = open(os.path.join(root, "legal_ai/query_engine/query_processor.py"), encoding="utf-8").read()
    main = open(os.path.join(root, "main.py"), encoding="utf-8").read()
    assert qp.count("model=CLAUDE_SYNTHESIS_MODEL") == 2 and main.count("model=CLAUDE_SYNTHESIS_MODEL") == 4
    assert "safe_create_anthropic_message(model=CLAUDE_MODEL, **kwargs)" in qp      # planner unchanged
