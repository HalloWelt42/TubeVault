"""
DB-Identitäts-Audit Tests (Phase 0 – Backup-Sicherheitsnetz).

audit_identity() liefert einen Snapshot der verbundenen DB für das
Startup-Log — Schutz gegen versehentlich falsch gemountete/leere DB.
Kontrakt:
- liefert db_path (realpath), size_bytes, videos, subscriptions, schema_version
- Zählungen stimmen mit dem tatsächlichen Inhalt überein
- reine Lesung (keine Schema-/Datenänderung)
"""
import pytest


async def test_audit_identity_reports_counts(test_db):
    await test_db.execute("INSERT INTO videos (id, title, status) VALUES (?, ?, 'ready')", ("v1", "A"))
    await test_db.execute("INSERT INTO videos (id, title, status) VALUES (?, ?, 'ready')", ("v2", "B"))
    await test_db.execute(
        "INSERT INTO subscriptions (channel_id, channel_name) VALUES (?, ?)", ("UC1", "Chan"))

    audit = await test_db.audit_identity()

    assert audit["videos"] == 2
    assert audit["subscriptions"] == 1
    assert audit["schema_version"] >= 1
    assert audit["db_path"].endswith(".db")
    assert audit["size_bytes"] > 0


async def test_audit_identity_empty_db(test_db):
    audit = await test_db.audit_identity()
    assert audit["videos"] == 0
    assert audit["subscriptions"] == 0
    # Schema ist trotzdem initialisiert
    assert audit["schema_version"] >= 1


async def test_audit_identity_is_read_only(test_db):
    """Audit darf nichts verändern."""
    await test_db.execute("INSERT INTO videos (id, title, status) VALUES (?, ?, 'ready')", ("v1", "A"))
    before = await test_db.fetch_val("SELECT COUNT(*) FROM videos")
    await test_db.audit_identity()
    await test_db.audit_identity()
    after = await test_db.fetch_val("SELECT COUNT(*) FROM videos")
    assert before == after == 1
