import base64
import json
from pathlib import Path

from core.content_classification import classify_judgment_content
from core.pdf_resolver import fetch_storage_pdf_bytes
from core.provider_ledger import ProviderHealthLedger, ProviderStatus
from core import turso_client
from legal_ai.statutes.statute_injector import StatuteInjector


def test_provider_ledger_marks_degraded_and_redacts_credentials():
    ledger = ProviderHealthLedger()
    ledger.record(
        "dense_conceptual",
        "Pinecone",
        ProviderStatus.PROVIDER_DOWN,
        message="Authorization: Bearer abc123",
    )

    result = ledger.to_dict()
    assert result["status"] == "degraded"
    assert result["events"][0]["status"] == "PROVIDER_DOWN"
    assert "abc123" not in result["events"][0]["message"]


def test_headnote_is_not_classified_as_a_full_judgment():
    assert classify_judgment_content(
        {
            "full_text": "Headnote\nA short editorial summary of the case.",
            "content_level": "full_judgment",
        }
    ) == "headnote_only"
    assert classify_judgment_content({"full_text": ""}) == "unknown"


def test_article_113_is_structured_and_not_quotable():
    data_path = Path(__file__).parents[1] / "data" / "statutes_v2" / "LIMITATION_1908.json"
    records = json.loads(data_path.read_text(encoding="utf-8"))
    article = next(record for record in records if record["canonical_id"] == "LIMITATION_1908_ART_113")

    assert article["text"] == ""
    assert article["text_raw"] == ""
    assert article["text_kind"] == "structured_table_entry"
    assert article["quoting_allowed"] is False
    assert "Period of limitation: Three years" in article["structured_summary"]

    result = StatuteInjector().inject_statutory_framework(
        {"statutory_provisions": ["Article 113 Limitation Act"]}
    )
    assert "Article 113, Limitation Act, 1908" in result["provisions_not_retrieved"]
    assert "Article 113, Limitation Act, 1908" not in result["provisions_with_text"]
    assert "Structured limitation-table entry (not verbatim bare-act text)" in result["statute_block"]
    article_start = result["statute_block"].index("--- PROVISION: Article 113")
    article_end = result["statute_block"].find("--- PROVISION:", article_start + 1)
    article_block = result["statute_block"][article_start:article_end if article_end >= 0 else None]
    assert "Verbatim Bare-Act Text in Force:" not in article_block


def test_turso_pdf_lookup_uses_journal_year_and_page(monkeypatch):
    expected_pdf = b"%PDF-1.7 test"
    captured = {}
    monkeypatch.setattr(turso_client, "is_turso_circuit_open", lambda: False)

    def fake_execute(statements, timeout, max_retries):
        captured["statements"] = statements
        captured["timeout"] = timeout
        return [{"rows": [{"pdf_base64": base64.b64encode(expected_pdf).decode("ascii")}]}]

    monkeypatch.setattr(turso_client, "execute_turso_pipeline", fake_execute)

    result = turso_client.get_case_pdf_bytes(
        "PLD 2020 SC 1",
        target_year="2020",
        target_journal="PLD",
        target_page="1",
    )

    assert result == expected_pdf
    sql = captured["statements"][0]["sql"]
    assert "journal = ? AND year = ? AND page = ?" in sql
    args = captured["statements"][0]["args"]
    assert [arg["value"] for arg in args[-3:]] == ["PLD", 2020, 1]


def test_pdf_resolver_passes_case_id_as_first_turso_argument(monkeypatch):
    captured = {}
    monkeypatch.setattr("core.pdf_resolver.os.path.isdir", lambda _: False)

    def fake_get_pdf(case_id, **kwargs):
        captured["case_id"] = case_id
        captured.update(kwargs)
        return b"%PDF-1.7 test"

    monkeypatch.setattr(turso_client, "get_case_pdf_bytes", fake_get_pdf)

    result = fetch_storage_pdf_bytes(None, "PLD", "2020", "1", "2020_PLD_1")

    assert result == b"%PDF-1.7 test"
    assert captured == {
        "case_id": "2020_PLD_1",
        "target_year": "2020",
        "target_journal": "PLD",
        "target_page": "1",
    }
