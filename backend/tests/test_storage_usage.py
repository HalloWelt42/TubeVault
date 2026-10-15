"""Speicherbelegung: die Statistik darf nie den Hauptlauf blockieren."""
from app.services import storage_usage


def test_ordnergroesse_ohne_verknuepfungen(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.bin").write_bytes(b"1" * 300)
    (tmp_path / "y.bin").write_bytes(b"1" * 200)
    (tmp_path / "link").symlink_to(tmp_path / "a")      # nicht doppelt zählen
    assert storage_usage.directory_size(tmp_path) == 500
    assert storage_usage.directory_size(tmp_path / "fehlt") == 0


async def test_statistik_antwortet_sofort_und_misst_im_hintergrund(test_db, monkeypatch, tmp_path):
    measured = []
    monkeypatch.setattr(storage_usage, "MEASURED_DIRS", {"temp": (tmp_path, "meta")})
    monkeypatch.setattr(storage_usage, "_measured_at", None)
    monkeypatch.setattr(storage_usage, "_sizes", {})
    real = storage_usage.directory_size
    monkeypatch.setattr(storage_usage, "directory_size", lambda p: measured.append(p) or real(p))
    await test_db.execute(
        "INSERT INTO videos (id, title, status, file_size) VALUES ('vid00000001', 'x', 'ready', 1000)")

    first = await storage_usage.snapshot()
    assert first.directories["videos"].size == 1000            # aus der Datenbank
    await storage_usage._task                                   # Messung lief im Hintergrund
    second = await storage_usage.snapshot()
    assert second.directories["temp"].size == 0 and second.measured_at
    assert measured == [tmp_path]                              # nur einmal gemessen
