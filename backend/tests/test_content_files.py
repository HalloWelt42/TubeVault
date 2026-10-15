"""
Inhalte als Datei (app/services/content_files, Nutzerentscheidung 16.10.2026).

Kontrakt:
- Inhalte liegen als Datei neben dem Video: info.json, Beschreibung, Kapitel.
- Was fehlt (Altbestand, Vorgemerktes), zieht der Dienst paketweise nach,
  ohne Knopf; danach ist nichts mehr offen.
- Import und eigene Videos schreiben über write_for alle Dateien.
- Ein Video, dessen Datei sich nicht schreiben lässt, hält die Schleife
  nicht in einer Endlosrunde fest.
"""
import json

import pytest

from app.services import content_files, meta_sidecar, text_export


@pytest.fixture
def ablage(tmp_path, monkeypatch):
    monkeypatch.setattr(text_export, "TEXTS_DIR", tmp_path / "texts")
    monkeypatch.setenv("TUBEVAULT_VIDEOS_ROOT", str(tmp_path / "videos"))
    return tmp_path


async def _video(db, ablage, video_id, description="Hallo Welt", chapters=0):
    (ablage / "videos" / video_id).mkdir(parents=True)
    await db.execute("INSERT INTO videos (id, title, status, description) VALUES (?, 'T', 'ready', ?)", (video_id, description))
    for n in range(chapters):
        await db.execute("INSERT INTO chapters (video_id, title, start_time) VALUES (?, ?, ?)", (video_id, f"Teil {n}", n * 60.0))


async def test_altbestand_wird_nachgezogen(test_db, ablage, monkeypatch):
    monkeypatch.setattr(content_files, "BATCH", 2)
    for n in range(3):
        await _video(test_db, ablage, f"alt{n:08d}", chapters=2 if n == 0 else 0)
    await test_db.execute("INSERT INTO sidecar_stale (video_id) SELECT id FROM videos")   # wie Migration v57
    assert await content_files.remaining() == 3 + 1 + 3

    while await content_files.run_batch():
        pass
    assert await content_files.remaining() == 0
    assert (ablage / "texts" / "alt00000000" / "description.txt").read_text(encoding="utf-8") == "Hallo Welt"
    assert len(json.loads((ablage / "texts" / "alt00000000" / "chapters.json").read_text(encoding="utf-8"))) == 2
    assert json.loads(meta_sidecar.sidecar_path("alt00000002").read_text(encoding="utf-8"))["id"] == "alt00000002"


async def test_write_for_schreibt_alles(test_db, ablage):
    await _video(test_db, ablage, "neu00000001", chapters=1)
    await content_files.write_for("neu00000001")
    assert (ablage / "texts" / "neu00000001" / "description.txt").exists()
    assert (ablage / "texts" / "neu00000001" / "chapters.json").exists()
    assert meta_sidecar.sidecar_path("neu00000001").exists()
    assert await content_files.remaining() == 0


async def test_fehlschlag_kreist_nicht(test_db, ablage, monkeypatch):
    await _video(test_db, ablage, "kaputt00001")

    async def scheitert(video_id):
        raise PermissionError("schreibgeschützt")
    monkeypatch.setattr(text_export, "export_description", scheitert)
    assert await content_files.run_batch() == 0          # Schleife wartet dann, statt zu kreisen
    assert await content_files.remaining() == 1
