import os
import tempfile
import sqlite3
import pytest
from scripts.zilliz.embed_upsert import IngestManifest, EmbedUpsertPipeline

def test_ingest_manifest_idempotency():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db = f.name

    manifest = IngestManifest(db_path=temp_db)
    try:
        assert manifest.get_completed_count("judgments_v1", "voyage-4-large") == 0

        # Mark chunk done
        row1 = (
            "2024_SCMR_SC_14:headnote:000",
            "2024_SCMR_SC_14",
            "hash123",
            "voyage-4-large",
            "judgments_v1",
            "batch_001",
        )
        manifest.mark_chunks_done([row1])

        assert manifest.is_chunk_done("2024_SCMR_SC_14:headnote:000", "hash123", "voyage-4-large") is True
        assert manifest.is_chunk_done("2024_SCMR_SC_14:headnote:000", "different_hash", "voyage-4-large") is False
        assert manifest.get_completed_count("judgments_v1", "voyage-4-large") == 1

        # Re-marking identical chunk should not duplicate
        manifest.mark_chunks_done([row1])
        assert manifest.get_completed_count("judgments_v1", "voyage-4-large") == 1
    finally:
        manifest.conn.close()
        if os.path.exists(temp_db):
            os.remove(temp_db)

def test_spend_cap_enforcement():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db = f.name

    pipeline = EmbedUpsertPipeline(
        collection_name="test_col",
        embed_model="voyage-4-large",
        spend_cap=1.00,  # $1.00 cap
        manifest_db=temp_db,
        dry_run=True,
    )
    try:
        # 1M tokens @ $0.12/M = $0.12 (OK)
        pipeline.check_and_record_spend(1_000_000)
        assert pipeline.total_tokens_used == 1_000_000
        assert round(pipeline.total_spend_usd, 2) == 0.12

        # 10M tokens @ $0.12/M = $1.20 + $0.12 = $1.32 > $1.00 cap -> should raise RuntimeError
        with pytest.raises(RuntimeError, match="Spending cap exceeded"):
            pipeline.check_and_record_spend(10_000_000)
    finally:
        pipeline.manifest.conn.close()
        if os.path.exists(temp_db):
            os.remove(temp_db)
