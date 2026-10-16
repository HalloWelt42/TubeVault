"""
Beschreibung als Datei (app/services/text_export, Nutzerentscheidung 16.10.2026).

Kontrakt:
- write_description ist die eine Schreibstelle: Datei <texts>/<id>/description.txt
  samt Eintrag in text_files (Größe, sha256); die Spalte videos.description
  wird dabei geleert, nie beschrieben.
- gleicher Text: kein erneutes Schreiben; leerer Text löscht die Beschreibung;
  keep_existing behält einen vorhandenen Text (erneutes Laden).
- move_description_from_column bringt Altbestand aus der Spalte in die Datei
  und leert die Spalte nur, wenn sie sich seither nicht geändert hat.
"""
import pytest

from app.services import text_export, text_resolver


@pytest.fixture
def texte(tmp_path, monkeypatch):
    monkeypatch.setattr(text_export, "TEXTS_DIR", tmp_path)
    return tmp_path


@pytest.fixture
async def video(test_db):
    await test_db.execute("INSERT INTO videos (id, title, description) VALUES ('vidABC', 'T', 'Alt in der Spalte')")
    return "vidABC"


async def _registry(db, video_id):
    return await db.fetch_one("SELECT * FROM text_files WHERE video_id = ? AND kind = 'description'", (video_id,))


async def test_schreibt_datei_und_leert_spalte(test_db, texte, video):
    assert await text_export.write_description(video, "Das ist die Beschreibung.\nZweite Zeile.")
    assert (texte / video / "description.txt").read_text(encoding="utf-8") == "Das ist die Beschreibung.\nZweite Zeile."
    row = await _registry(test_db, video)
    assert row["filename"] == f"{video}/description.txt" and row["size_bytes"] > 0 and len(row["sha256"]) == 64
    assert await test_db.fetch_val("SELECT description FROM videos WHERE id = ?", (video,)) is None
    assert await text_resolver.get_description(video) == "Das ist die Beschreibung.\nZweite Zeile."


async def test_gleicher_text_schreibt_nicht_neu(test_db, texte, video):
    await text_export.write_description(video, "Gleich")
    first = (await _registry(test_db, video))["synced_at"]
    await text_export.write_description(video, "Gleich")
    assert (await _registry(test_db, video))["synced_at"] == first


async def test_leerer_text_loescht(test_db, texte, video):
    await text_export.write_description(video, "Weg damit")
    await text_export.write_description(video, "")
    assert not (texte / video / "description.txt").exists()
    assert await _registry(test_db, video) is None
    assert await text_resolver.get_description(video) is None


async def test_vorhandener_text_bleibt_beim_erneuten_laden(test_db, texte, video):
    await text_export.write_description(video, "Vom Nutzer gepflegt")
    assert not await text_export.write_description(video, "Von der Quelle", keep_existing=True)
    assert await text_resolver.get_description(video) == "Vom Nutzer gepflegt"


async def test_altbestand_wandert_aus_der_spalte(test_db, texte, video):
    assert await text_export.move_description_from_column(video, "Alt in der Spalte")
    assert (texte / video / "description.txt").read_text(encoding="utf-8") == "Alt in der Spalte"
    assert await test_db.fetch_val("SELECT description FROM videos WHERE id = ?", (video,)) is None


async def test_spalte_neuer_als_datei_gewinnt(test_db, texte, video):
    # Bis 2.71 schrieb jede Schreibstelle erst die Spalte: eine abweichende Datei ist veraltet
    (texte / video).mkdir()
    (texte / video / "description.txt").write_text("Veraltet", encoding="utf-8")
    await text_export.move_description_from_column(video, "Alt in der Spalte")
    assert await text_resolver.get_description(video) == "Alt in der Spalte"


async def test_geaenderte_spalte_wird_nicht_geleert(test_db, texte, video):
    # Hat sich die Spalte zwischen Lesen und Leeren geändert, bleibt sie stehen
    await test_db.execute("UPDATE videos SET description = 'Inzwischen anders' WHERE id = ?", (video,))
    assert not await text_export.move_description_from_column(video, "Alt in der Spalte")
    assert await test_db.fetch_val("SELECT description FROM videos WHERE id = ?", (video,)) == "Inzwischen anders"


async def test_viele_auf_einmal_lesen(test_db, texte, video):
    # Export: Dateien gesammelt im Faden lesen, Übergang aus der Spalte
    await test_db.execute("INSERT INTO videos (id, title) VALUES ('ohneText01', 'T')")
    await test_db.execute("INSERT INTO videos (id, title, description) VALUES ('nurSpalte1', 'T', 'Noch in der Spalte')")
    await text_export.write_description(video, "Aus der Datei")
    found = await text_resolver.descriptions_of([video, "ohneText01", "nurSpalte1"])
    assert found == {video: "Aus der Datei", "nurSpalte1": "Noch in der Spalte"}
