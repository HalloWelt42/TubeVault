"""
Storage-Abstraktion Tests (Phase 3a).

Invarianten:
- Jeder Storage-Typ hat eine eigene Root, per ENV setzbar
- Fallback auf DATA_DIR/<typ> wenn ENV nicht gesetzt
- High-Level-Helpers (text_file etc.) liefern konsistente Pfade
- Video-Ordner-Konvention: <texts_root>/<video_id>/<kind>.<ext>
- Pure Funktion, keine mkdir-Side-Effects beim Pfad-Bauen
"""
import os
from pathlib import Path

import pytest


@pytest.fixture
def fresh_storage(tmp_path, monkeypatch):
    """Neue Storage-Instanz mit tmp-Roots per ENV."""
    monkeypatch.setenv("TUBEVAULT_TEXTS_ROOT", str(tmp_path / "texts"))
    monkeypatch.setenv("TUBEVAULT_VIDEOS_ROOT", str(tmp_path / "videos"))
    monkeypatch.setenv("TUBEVAULT_THUMBNAILS_ROOT", str(tmp_path / "thumbnails"))
    monkeypatch.setenv("TUBEVAULT_SUBTITLES_ROOT", str(tmp_path / "subtitles"))
    # Wichtig: Storage nach Env-Änderung neu bauen
    from app.services.storage import Storage
    return Storage()


# ─────────────────────── Root-Resolution ───────────────────────

def test_texts_root_from_env(fresh_storage, tmp_path):
    assert fresh_storage.texts_root == tmp_path / "texts"


def test_videos_root_from_env(fresh_storage, tmp_path):
    assert fresh_storage.videos_root == tmp_path / "videos"


def test_default_texts_root_when_no_env(monkeypatch):
    monkeypatch.delenv("TUBEVAULT_TEXTS_ROOT", raising=False)
    from app.config import DATA_DIR
    from app.services.storage import Storage
    s = Storage()
    assert s.texts_root == DATA_DIR / "texts"


# ─────────────────────── text_file() ───────────────────────

def test_text_file_description(fresh_storage):
    p = fresh_storage.text_file("vidABC", "description")
    assert p.name == "description.txt"
    assert p.parent.name == "vidABC"
    assert p.parent.parent == fresh_storage.texts_root


def test_text_file_chapters_is_json(fresh_storage):
    p = fresh_storage.text_file("vidABC", "chapters")
    assert p.name == "chapters.json"


def test_text_file_lyrics_is_txt(fresh_storage):
    """Muss zum existierenden lyrics_service passen: lyrics.txt im Video-Ordner."""
    p = fresh_storage.text_file("vidABC", "lyrics")
    assert p.name == "lyrics.txt"
    assert p.parent.name == "vidABC"


def test_text_file_notes_is_md(fresh_storage):
    p = fresh_storage.text_file("vidABC", "notes")
    assert p.name == "notes.md"


def test_text_file_unknown_kind_defaults_to_txt(fresh_storage):
    p = fresh_storage.text_file("vidABC", "unknown_kind")
    assert p.suffix == ".txt"


# ─────────────────────── Side-Effect-freie Pfad-Bildung ───────────────────────

def test_text_file_does_not_create_directories(fresh_storage, tmp_path):
    """Pfad zu bauen darf keine Ordner anlegen – das tut erst der Writer."""
    fresh_storage.text_file("xyz", "description")
    assert not (tmp_path / "texts" / "xyz").exists()


# ─────────────────────── video_dir() ───────────────────────

def test_video_dir(fresh_storage):
    d = fresh_storage.video_dir("vidABC")
    assert d == fresh_storage.texts_root / "vidABC"


def test_video_dir_same_parent_for_all_kinds(fresh_storage):
    """Alle kinds landen im gleichen Video-Ordner (→ ein Video = ein Paket)."""
    desc = fresh_storage.text_file("v1", "description")
    lyr = fresh_storage.text_file("v1", "lyrics")
    chap = fresh_storage.text_file("v1", "chapters")
    assert desc.parent == lyr.parent == chap.parent == fresh_storage.video_dir("v1")


# ─────────────────────── relative_text_path() (für text_files.filename) ───────

def test_relative_text_path(fresh_storage):
    """filename in text_files: rel. zum texts_root, z.B. 'v1/description.txt'."""
    rel = fresh_storage.relative_text_path("v1", "description")
    assert rel == "v1/description.txt"


def test_relative_text_path_lyrics(fresh_storage):
    rel = fresh_storage.relative_text_path("v1", "lyrics")
    assert rel == "v1/lyrics.txt"


# ─────────────────────── ensure_video_dir() ───────────────────────

def test_ensure_video_dir_creates_dir(fresh_storage, tmp_path):
    d = fresh_storage.ensure_video_dir("newvid")
    assert d.exists()
    assert d.is_dir()
    assert d == tmp_path / "texts" / "newvid"


def test_ensure_video_dir_idempotent(fresh_storage, tmp_path):
    d1 = fresh_storage.ensure_video_dir("idem")
    d2 = fresh_storage.ensure_video_dir("idem")
    assert d1 == d2  # kein Fehler wenn schon da


# ─────────────────────── Override per DI ───────────────────────

def test_storage_accepts_custom_roots(tmp_path):
    """Tests können Storage mit expliziten Roots bauen (kein ENV-Setup)."""
    from app.services.storage import Storage
    s = Storage(
        texts_root=tmp_path / "x-texts",
        videos_root=tmp_path / "x-videos",
    )
    assert s.texts_root == tmp_path / "x-texts"
    assert s.videos_root == tmp_path / "x-videos"
