"""
DB-Index Existenz-Tests.

Sichert ab dass kritische Composite-Indexe beim Schema-Init angelegt werden.
Ein Regression-Test: wenn jemand die INDEXES_SQL aus database.py entfernt,
sehen wir das sofort.

Kein Performance-Test hier – nur Existenz.
"""


async def _index_names(db) -> set[str]:
    rows = await db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
    )
    return {r["name"] for r in rows}


async def test_standard_single_indexes_exist(test_db):
    names = await _index_names(test_db)
    # Einzelindexe die vor Phase 2c schon da waren
    for idx in [
        "idx_videos_status",
        "idx_videos_channel",
        "idx_videos_archived",
        "idx_jobs_status",
        "idx_jobs_type",
        "idx_rss_entries_channel",
    ]:
        assert idx in names, f"Index {idx} fehlt"


async def test_composite_indexes_exist(test_db):
    """Phase 2c: neue Composite-Indexe fuer die wichtigsten Queries."""
    names = await _index_names(test_db)
    assert "idx_videos_status_archived_upload" in names
    assert "idx_videos_channel_archived" in names
    assert "idx_jobs_queue_pick" in names
    assert "idx_jobs_metadata_video_id" in names
    assert "idx_rss_entries_channel_feed_status" in names


async def test_library_query_uses_composite_index(test_db):
    """EXPLAIN QUERY PLAN fuer die Library-Standard-Query sollte den neuen
    Composite-Index verwenden (kein Full-Scan)."""
    # EXPLAIN QUERY PLAN liefert Strings wie "SEARCH videos USING INDEX ..."
    rows = await test_db.fetch_all(
        "EXPLAIN QUERY PLAN "
        "SELECT * FROM videos WHERE status='ready' AND is_archived=0 "
        "ORDER BY upload_date DESC LIMIT 24"
    )
    plan = " ".join(r["detail"] for r in rows if "detail" in r.keys())
    # Idealerweise nutzt er idx_videos_status_archived_upload.
    # Mindestens MUSS ein Index genutzt werden (kein SCAN TABLE).
    assert "INDEX" in plan.upper(), (
        f"Query-Plan nutzt keinen Index: {plan}"
    )


async def test_jobs_queue_pick_uses_composite(test_db):
    """Die Worker-Query findet den naechsten Job.
    Muss einen Index nutzen – sonst wird der Queue-Worker bei 13k+ Jobs langsam."""
    rows = await test_db.fetch_all(
        "EXPLAIN QUERY PLAN "
        "SELECT * FROM jobs WHERE type='download' AND status='queued' "
        "ORDER BY priority DESC, created_at ASC LIMIT 1"
    )
    plan = " ".join(r["detail"] for r in rows if "detail" in r.keys())
    assert "INDEX" in plan.upper(), (
        f"Queue-Pick-Query nutzt keinen Index: {plan}"
    )
