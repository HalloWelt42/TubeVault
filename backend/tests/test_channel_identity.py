"""
Kanal-Zuordnung (app/services/channel_identity.py).

Kontrakt: Ist der Kanal eines Videos bekannt, steht sein Name am Video -
unabhängig vom Schreibweg.
"""
import pytest

CH = "UCkanal0000000000000001"


async def _sub(db, name="Werkbank Nord", channel_id=CH):
    await db.execute(
        "INSERT INTO subscriptions (channel_id, channel_name) VALUES (?, ?)", (channel_id, name))


async def _name(db, vid):
    return await db.fetch_val("SELECT channel_name FROM videos WHERE id = ?", (vid,))


async def test_name_aus_abo_beim_anlegen(test_db):
    await _sub(test_db)
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_name, channel_id) VALUES ('v1', 'T', '', ?)", (CH,))
    assert await _name(test_db, "v1") == "Werkbank Nord"


async def test_name_aus_abo_bei_null(test_db):
    await _sub(test_db)
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_id) VALUES ('v1', 'T', ?)", (CH,))
    assert await _name(test_db, "v1") == "Werkbank Nord"


async def test_bekannter_name_wird_nicht_geleert(test_db):
    """Der Download-Abschluss schrieb den leeren Namen der Quelle über einen
    bekannten Namen."""
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_name, channel_id) VALUES ('v1', 'T', 'Alter Name', 'UCfremd')")
    await test_db.execute("UPDATE videos SET channel_name = '', status = 'ready' WHERE id = 'v1'")
    assert await _name(test_db, "v1") == "Alter Name"


async def test_name_vom_geschwister_video(test_db):
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_name, channel_id) VALUES ('v1', 'T', 'Gleisplan', 'UCohneabo')")
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_name, channel_id) VALUES ('v2', 'T', NULL, 'UCohneabo')")
    assert await _name(test_db, "v2") == "Gleisplan"


async def test_kanal_id_aus_feed(test_db):
    await _sub(test_db)
    await test_db.execute(
        "INSERT INTO rss_entries (video_id, channel_id, title) VALUES ('v1', ?, 'T')", (CH,))
    await test_db.execute("INSERT INTO videos (id, title) VALUES ('v1', 'Stub')")
    row = await test_db.fetch_one("SELECT channel_id, channel_name FROM videos WHERE id = 'v1'")
    assert row["channel_id"] == CH and row["channel_name"] == "Werkbank Nord"


async def test_unbekannter_kanal_bleibt_leer(test_db):
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_id) VALUES ('v1', 'T', 'UCniemand')")
    assert await _name(test_db, "v1") is None


async def test_neues_abo_fuellt_namenlose_videos(test_db):
    await test_db.execute("INSERT INTO videos (id, title, channel_id) VALUES ('v1', 'T', ?)", (CH,))
    await _sub(test_db)
    assert await _name(test_db, "v1") == "Werkbank Nord"


async def test_umbenennung_zieht_nach_aber_schont_eigene_namen(test_db):
    await _sub(test_db, "Alter Kanalname")
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_name, channel_id) VALUES ('auto', 'T', 'Alter Kanalname', ?)", (CH,))
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_name, channel_id) VALUES ('eigen', 'T', 'Von Hand gesetzt', ?)", (CH,))

    await test_db.execute(
        "UPDATE subscriptions SET channel_name = 'Neuer Kanalname' WHERE channel_id = ?", (CH,))

    assert await _name(test_db, "auto") == "Neuer Kanalname"
    assert await _name(test_db, "eigen") == "Von Hand gesetzt"


async def test_kanal_id_als_name_gilt_nicht(test_db):
    await _sub(test_db, CH)   # Abo kennt (noch) nur die ID
    await test_db.execute("INSERT INTO videos (id, title, channel_id) VALUES ('v1', 'T', ?)", (CH,))
    assert await _name(test_db, "v1") is None


async def test_bestandsreparatur_fuellt_nur_leeres(test_db):
    from app.services import channel_identity
    await _sub(test_db)
    # Bestand wie vor der Regel: Trigger kurz entfernen
    for trg in ("trg_video_channel_insert", "trg_video_channel_update",
                "trg_subscription_name_insert", "trg_subscription_name_update"):
        await test_db.execute(f"DROP TRIGGER {trg}")
    await test_db.execute("INSERT INTO videos (id, title, channel_name, channel_id) VALUES ('leer', 'T', '', ?)", (CH,))
    await test_db.execute("INSERT INTO videos (id, title, channel_name, channel_id) VALUES ('anders', 'T', 'Abweichend', ?)", (CH,))

    repaired = await channel_identity.install(test_db.conn, repair=True)
    await test_db.conn.commit()

    assert repaired == 1
    assert await _name(test_db, "leer") == "Werkbank Nord"
    assert await _name(test_db, "anders") == "Abweichend"


async def test_suchindex_kennt_den_ergaenzten_namen(test_db):
    from app.services import search_index
    await _sub(test_db)
    await test_db.execute(
        "INSERT INTO videos (id, title, channel_id, status) VALUES ('v1', 'Folge 1', ?, 'ready')", (CH,))
    result = await search_index.search_videos("Werkbank")
    assert [v["id"] for v in result["videos"]] == ["v1"]
