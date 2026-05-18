"""
TubeVault – Storage-Abstraktion v1.0.0

Einzige Stelle im Code die physische Pfade kennt.
Alle anderen Services/Router gehen über diesen Service.

Motivation (R1 + R2 in ARCHITECTURE.md):
- Storage-Roots pro Typ sind von außen setzbar (ENV)
  → Videos können auf USB, Texte auf NVMe liegen, unabhängig
- Eine Konvention an EINER Stelle (Video-Ordner, Datei-Namen)
- Services müssen nur noch High-Level-Helpers aufrufen

ENV-Variablen (Fallback jeweils: DATA_DIR/<typ>):
- TUBEVAULT_TEXTS_ROOT
- TUBEVAULT_VIDEOS_ROOT
- TUBEVAULT_THUMBNAILS_ROOT
- TUBEVAULT_SUBTITLES_ROOT
- TUBEVAULT_AVATARS_ROOT
- TUBEVAULT_BANNERS_ROOT
- TUBEVAULT_AUDIO_ROOT
- TUBEVAULT_EXPORTS_ROOT
"""
import os
from pathlib import Path

from app.config import DATA_DIR


# Kind → File-Extension für Text-Dateien
_KIND_EXT = {
    "description": "txt",
    "chapters": "json",
    "tags": "txt",
    "notes": "md",
    "lyrics": "txt",         # konsistent zu lyrics_service
    "lyrics-synced": "lrc",  # LRC-Format für synchronisierte Lyrics
    "subtitles": "vtt",
}


def _env_or_default(env_key: str, default: Path) -> Path:
    val = os.getenv(env_key, "").strip()
    return Path(val) if val else default


class Storage:
    """
    Abstrahiert Storage-Roots und hoch-level Pfad-Helpers.

    Tests können entweder ENVs per monkeypatch setzen, oder eine Instanz
    mit expliziten Roots bauen:

        s = Storage(texts_root=tmp_path/"texts")
    """

    def __init__(
        self,
        *,
        texts_root: Path | None = None,
        videos_root: Path | None = None,
        thumbnails_root: Path | None = None,
        subtitles_root: Path | None = None,
        avatars_root: Path | None = None,
        banners_root: Path | None = None,
        audio_root: Path | None = None,
        exports_root: Path | None = None,
    ):
        self._texts = texts_root
        self._videos = videos_root
        self._thumbnails = thumbnails_root
        self._subtitles = subtitles_root
        self._avatars = avatars_root
        self._banners = banners_root
        self._audio = audio_root
        self._exports = exports_root

    # ─────────────────────── Roots ───────────────────────

    @property
    def texts_root(self) -> Path:
        if self._texts is not None:
            return self._texts
        return _env_or_default("TUBEVAULT_TEXTS_ROOT", DATA_DIR / "texts")

    @property
    def videos_root(self) -> Path:
        if self._videos is not None:
            return self._videos
        return _env_or_default("TUBEVAULT_VIDEOS_ROOT", DATA_DIR / "videos")

    @property
    def thumbnails_root(self) -> Path:
        if self._thumbnails is not None:
            return self._thumbnails
        return _env_or_default("TUBEVAULT_THUMBNAILS_ROOT", DATA_DIR / "thumbnails")

    @property
    def subtitles_root(self) -> Path:
        if self._subtitles is not None:
            return self._subtitles
        return _env_or_default("TUBEVAULT_SUBTITLES_ROOT", DATA_DIR / "subtitles")

    @property
    def avatars_root(self) -> Path:
        if self._avatars is not None:
            return self._avatars
        return _env_or_default("TUBEVAULT_AVATARS_ROOT", DATA_DIR / "avatars")

    @property
    def banners_root(self) -> Path:
        if self._banners is not None:
            return self._banners
        return _env_or_default("TUBEVAULT_BANNERS_ROOT", DATA_DIR / "banners")

    @property
    def audio_root(self) -> Path:
        if self._audio is not None:
            return self._audio
        return _env_or_default("TUBEVAULT_AUDIO_ROOT", DATA_DIR / "audio")

    @property
    def exports_root(self) -> Path:
        if self._exports is not None:
            return self._exports
        return _env_or_default("TUBEVAULT_EXPORTS_ROOT", DATA_DIR / "exports")

    # ─────────────────────── High-Level Helpers ───────────────────────

    def video_dir(self, video_id: str) -> Path:
        """Ordner eines Videos innerhalb texts_root.
        Enthält alle Text-Dokumente (description, chapters, lyrics, ...)."""
        return self.texts_root / video_id

    def ensure_video_dir(self, video_id: str) -> Path:
        """Wie video_dir, aber legt Verzeichnis an falls nicht existiert."""
        d = self.video_dir(video_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def text_file(self, video_id: str, kind: str) -> Path:
        """Vollständiger Pfad zu einer Text-Datei. PURE – kein mkdir."""
        ext = _KIND_EXT.get(kind, "txt")
        return self.video_dir(video_id) / f"{kind}.{ext}"

    def relative_text_path(self, video_id: str, kind: str) -> str:
        """Relativer Pfad ab texts_root, für DB-Registry (text_files.filename)."""
        ext = _KIND_EXT.get(kind, "txt")
        return f"{video_id}/{kind}.{ext}"


# Default-Instanz aus ENV. Services importieren diese.
storage = Storage()
