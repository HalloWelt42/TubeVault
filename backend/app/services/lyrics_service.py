"""
TubeVault -  Lyrics Service v1.8.20
Multi-Provider: YouTube Music (ytmusicapi) + LRCLIB + Untertitel.
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

import re
import json
import logging
import asyncio
from pathlib import Path
from typing import Optional

import httpx

from app.config import TEXTS_DIR
from app.database import db
from app.services.endpoint_service import get_service_url

logger = logging.getLogger(__name__)

LRCLIB_BASE = "https://lrclib.net/api"


async def _get_lrclib_url() -> str | None:
    """LRCLIB-URL aus api_endpoints lesen. None = deaktiviert."""
    url = await get_service_url("lrclib_api")
    return url if url else LRCLIB_BASE

# ─── YouTube Music Provider ─────────────────────────────────

_ytm = None

def _get_ytmusic():
    """Lazy-Init YTMusic (kein Auth nötig für Lyrics)."""
    global _ytm
    if _ytm is None:
        try:
            from ytmusicapi import YTMusic
            _ytm = YTMusic()
            logger.info("YTMusic initialisiert (no-auth)")
        except Exception as e:
            logger.warning(f"YTMusic init fehlgeschlagen: {e}")
            return None
    return _ytm


def _timed_lyrics_to_lrc(lyrics_list) -> tuple[str, str]:
    """Konvertiert ytmusicapi LyricLine-Liste → (plain, synced_lrc).

    LyricLine hat .text, .start_time (ms), .end_time (ms).
    """
    plain_lines = []
    lrc_lines = []

    for line in lyrics_list:
        # LyricLine object oder dict
        text = getattr(line, 'text', None) or (line.get('text', '') if isinstance(line, dict) else '')
        start_ms = getattr(line, 'start_time', None)
        if start_ms is None:
            start_ms = line.get('start_time', 0) if isinstance(line, dict) else 0

        if isinstance(start_ms, str):
            start_ms = int(start_ms)

        secs = start_ms / 1000.0
        mins = int(secs // 60)
        remainder = secs % 60
        lrc_lines.append(f"[{mins:02d}:{remainder:05.2f}] {text}")
        plain_lines.append(text)

    return '\n'.join(plain_lines), '\n'.join(lrc_lines)


async def search_ytmusic(video_id: str) -> Optional[dict]:
    """Lyrics via YouTube Music API holen (per Video-ID).

    Returns: { plain, synced, source: 'ytmusic' } oder None
    """
    yt = _get_ytmusic()
    if not yt:
        return None

    try:
        def _fetch():
            # Watch-Playlist holen → enthält lyrics browseId
            watch = yt.get_watch_playlist(video_id)
            if not watch or not watch.get("lyrics"):
                return None

            browse_id = watch["lyrics"]

            # Erst Timed Lyrics probieren
            try:
                timed = yt.get_lyrics(browse_id, timestamps=True)
                if timed and timed.get("hasTimestamps") and timed.get("lyrics"):
                    plain, synced = _timed_lyrics_to_lrc(timed["lyrics"])
                    source_info = timed.get("source", "ytmusic")
                    return {"plain": plain, "synced": synced, "source": f"ytmusic:{source_info}"}
            except Exception as e:
                logger.debug(f"YTMusic timed lyrics nicht verfügbar: {e}")

            # Fallback: Plain Lyrics
            try:
                plain_result = yt.get_lyrics(browse_id)
                if plain_result and plain_result.get("lyrics"):
                    return {
                        "plain": plain_result["lyrics"],
                        "synced": None,
                        "source": f"ytmusic:{plain_result.get('source', 'unknown')}",
                    }
            except Exception as e:
                logger.debug(f"YTMusic plain lyrics nicht verfügbar: {e}")

            return None

        result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return result

    except Exception as e:
        logger.warning(f"YTMusic Fehler für {video_id}: {e}")
        return None


async def search_ytmusic_by_name(artist: str, title: str) -> Optional[dict]:
    """Lyrics via YouTube Music API holen (per Suche nach Artist + Title).

    Returns: { plain, synced, source: 'ytmusic' } oder None
    """
    yt = _get_ytmusic()
    if not yt:
        return None

    try:
        def _fetch():
            # Suche nach Song
            results = yt.search(f"{artist} {title}", filter="songs", limit=3)
            if not results:
                return None

            for song in results:
                vid = song.get("videoId")
                if not vid:
                    continue
                try:
                    watch = yt.get_watch_playlist(vid)
                    if not watch or not watch.get("lyrics"):
                        continue

                    browse_id = watch["lyrics"]

                    # Timed
                    try:
                        timed = yt.get_lyrics(browse_id, timestamps=True)
                        if timed and timed.get("hasTimestamps") and timed.get("lyrics"):
                            plain, synced = _timed_lyrics_to_lrc(timed["lyrics"])
                            source_info = timed.get("source", "ytmusic")
                            return {"plain": plain, "synced": synced, "source": f"ytmusic:{source_info}"}
                    except Exception:
                        pass

                    # Plain fallback
                    try:
                        plain_result = yt.get_lyrics(browse_id)
                        if plain_result and plain_result.get("lyrics"):
                            return {
                                "plain": plain_result["lyrics"],
                                "synced": None,
                                "source": f"ytmusic:{plain_result.get('source', 'unknown')}",
                            }
                    except Exception:
                        pass
                except Exception:
                    continue

            return None

        return await asyncio.get_event_loop().run_in_executor(None, _fetch)

    except Exception as e:
        logger.warning(f"YTMusic Name-Suche Fehler: {e}")
        return None

# ─── Musik-Erkennung ────────────────────────────────────────

# Muster die auf Musik hindeuten
MUSIC_PATTERNS = [
    r"(?:official\s+)?(?:music\s+)?video",
    r"official\s+audio",
    r"lyric(?:s)?\s+video",
    r"audio\s+(?:only|oficial)",
    r"(?:feat|ft)\.?\s+",
    r"\((?:prod|remix|cover|acoustic|live|unplugged)\b",
    r"(?:m[/\\]v|mv)\b",
    r"lyrics?\b",
]
MUSIC_RE = re.compile("|".join(MUSIC_PATTERNS), re.IGNORECASE)

# Typische YouTube-Trennzeichen: "Artist - Title", "Artist -  Title", "Artist | Title"
ARTIST_TITLE_RE = re.compile(
    r"^(.+?)\s*[-–—|]\s*(.+?)(?:\s*[\(\[].*)?$"
)

# Zusätzliche Fragmente die wir aus dem Titel entfernen
CLEAN_FRAGMENTS = re.compile(
    r"\s*[\(\[]\s*(?:official|music|lyric|audio|video|hd|4k|hq|remaster|"
    r"visualizer|clip|explicit|clean|radio\s+edit|extended|remix|"
    r"feat\.?|ft\.?|prod\.?|acoustic|live|unplugged|m/?v)[^\)\]]*[\)\]]",
    re.IGNORECASE,
)


def detect_music(title: str, tags: str = "[]") -> dict:
    """Erkennt ob ein Video Musik ist und extrahiert Artist/Title.

    Returns: { is_music: bool, artist: str|None, song_title: str|None }
    """
    if not title:
        return {"is_music": False, "artist": None, "song_title": None}

    # Tags prüfen
    try:
        tag_list = json.loads(tags) if isinstance(tags, str) else (tags or [])
    except (json.JSONDecodeError, TypeError):
        tag_list = []

    music_tags = {"music", "musik", "song", "hip hop", "rap", "pop", "rock",
                  "electronic", "edm", "r&b", "rnb", "jazz", "classical",
                  "reggae", "metal", "punk", "indie", "folk", "country",
                  "soundtrack", "ost"}
    has_music_tag = any(t.lower().strip() in music_tags for t in tag_list)

    # Muster im Titel prüfen
    has_pattern = bool(MUSIC_RE.search(title))

    # Artist - Title Muster prüfen
    m = ARTIST_TITLE_RE.match(title)
    has_separator = m is not None

    # Entscheidung: mindestens 2 von 3 Signalen
    signals = sum([has_music_tag, has_pattern, has_separator])
    is_music = signals >= 1 and has_separator  # Muss zumindest Artist-Title haben

    artist = None
    song_title = None

    if is_music and m:
        artist = m.group(1).strip()
        raw_title = m.group(2).strip()
        # Fragmente entfernen
        song_title = CLEAN_FRAGMENTS.sub("", raw_title).strip()
        # Falls Artist auch Fragmente hat
        artist = CLEAN_FRAGMENTS.sub("", artist).strip()

    return {"is_music": is_music, "artist": artist, "song_title": song_title}


# ─── LRCLIB API ──────────────────────────────────────────────

async def search_lyrics(
    artist: str,
    title: str,
    album: str = "",
    duration: int = 0,
) -> Optional[dict]:
    """Sucht Lyrics bei LRCLIB.

    Returns: { plain: str, synced: str|None, source: 'lrclib', id: int } oder None
    """
    params = {"artist_name": artist, "track_name": title}
    if album:
        params["album_name"] = album
    if duration and duration > 0:
        params["duration"] = duration

    try:
        lrclib_url = await _get_lrclib_url()
        async with httpx.AsyncClient(timeout=10) as client:
            # Erst exakte Suche per GET /api/get
            resp = await client.get(f"{lrclib_url}/get", params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("plainLyrics") or data.get("syncedLyrics"):
                    return {
                        "plain": data.get("plainLyrics", ""),
                        "synced": data.get("syncedLyrics"),
                        "source": "lrclib",
                        "lrclib_id": data.get("id"),
                        "artist": data.get("artistName", artist),
                        "title": data.get("trackName", title),
                        "album": data.get("albumName", ""),
                    }

            # Fallback: Suche
            resp = await client.get(
                f"{lrclib_url}/search",
                params={"artist_name": artist, "track_name": title},
            )
            if resp.status_code == 200:
                results = resp.json()
                for r in results[:5]:
                    if r.get("plainLyrics") or r.get("syncedLyrics"):
                        return {
                            "plain": r.get("plainLyrics", ""),
                            "synced": r.get("syncedLyrics"),
                            "source": "lrclib",
                            "lrclib_id": r.get("id"),
                            "artist": r.get("artistName", artist),
                            "title": r.get("trackName", title),
                            "album": r.get("albumName", ""),
                        }

    except Exception as e:
        logger.warning(f"LRCLIB Fehler: {e}")

    return None


async def search_lyrics_all(
    artist: str,
    title: str,
) -> list[dict]:
    """Sucht ALLE Lyrics-Versionen bei LRCLIB (für Auswahl-Dialog)."""
    results = []
    try:
        lrclib_url = await _get_lrclib_url()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{lrclib_url}/search",
                params={"artist_name": artist, "track_name": title},
            )
            if resp.status_code == 200:
                for r in resp.json()[:20]:
                    if r.get("plainLyrics") or r.get("syncedLyrics"):
                        dur = r.get("duration", 0)
                        results.append({
                            "lrclib_id": r.get("id"),
                            "artist": r.get("artistName", artist),
                            "title": r.get("trackName", title),
                            "album": r.get("albumName", ""),
                            "duration": dur,
                            "has_synced": bool(r.get("syncedLyrics")),
                            "plain": r.get("plainLyrics", ""),
                            "synced": r.get("syncedLyrics"),
                        })
    except Exception as e:
        logger.warning(f"LRCLIB multi-search Fehler: {e}")
    return results


# ─── Dateisystem ─────────────────────────────────────────────

def _text_dir(video_id: str) -> Path:
    """Verzeichnis für Textdateien eines Videos."""
    d = TEXTS_DIR / video_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_lyrics(video_id: str, plain: str, synced: str = None):
    """Speichert Lyrics als Textdateien."""
    d = _text_dir(video_id)
    if plain:
        (d / "lyrics.txt").write_text(plain, encoding="utf-8")
    if synced:
        (d / "lyrics.lrc").write_text(synced, encoding="utf-8")


def load_lyrics(video_id: str) -> dict:
    """Lädt Lyrics aus dem Dateisystem."""
    d = TEXTS_DIR / video_id
    plain = ""
    synced = ""
    offset = 0.0
    if (d / "lyrics.txt").exists():
        plain = (d / "lyrics.txt").read_text(encoding="utf-8")
    if (d / "lyrics.lrc").exists():
        synced = (d / "lyrics.lrc").read_text(encoding="utf-8")
    if (d / "offset.txt").exists():
        try:
            offset = float((d / "offset.txt").read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            offset = 0.0
    return {"plain": plain, "synced": synced, "offset": offset}


def save_offset(video_id: str, offset: float):
    """Speichert Sync-Offset als Datei."""
    d = _text_dir(video_id)
    if abs(offset) < 0.01:
        p = d / "offset.txt"
        if p.exists():
            p.unlink()
    else:
        (d / "offset.txt").write_text(str(round(offset, 2)), encoding="utf-8")


def delete_lyrics(video_id: str):
    """Löscht Lyrics-Dateien."""
    d = TEXTS_DIR / video_id
    for f in ["lyrics.txt", "lyrics.lrc", "offset.txt"]:
        p = d / f
        if p.exists():
            p.unlink()


def vtt_to_lrc(vtt_text: str) -> tuple[str, str]:
    """Konvertiert VTT/SRT-Untertitel zu LRC + Plain.

    Returns: (plain, synced_lrc)
    """
    import re
    lines_out = []
    plain_lines = []
    # Parse VTT timestamps: 00:01:23.456 --> 00:01:25.789
    pattern = re.compile(
        r'(\d+):(\d+):(\d+)[.,](\d+)\s*-->\s*\d+:\d+:\d+[.,]\d+'
    )
    current_time = None
    buffer = []

    for line in vtt_text.split('\n'):
        line = line.strip()
        # Skip WEBVTT header, NOTE, STYLE, numeric cue IDs
        if not line or line.startswith(('WEBVTT', 'NOTE', 'STYLE', 'Kind:', 'Language:')) or line.isdigit():
            if buffer and current_time is not None:
                text = ' '.join(buffer).strip()
                # Remove HTML tags
                text = re.sub(r'<[^>]+>', '', text)
                if text and text not in [t for _, t in lines_out[-3:] if lines_out]:
                    lines_out.append((current_time, text))
                    plain_lines.append(text)
                buffer = []
            continue

        m = pattern.match(line)
        if m:
            if buffer and current_time is not None:
                text = ' '.join(buffer).strip()
                text = re.sub(r'<[^>]+>', '', text)
                if text:
                    # Deduplicate consecutive identical lines
                    if not lines_out or lines_out[-1][1] != text:
                        lines_out.append((current_time, text))
                        plain_lines.append(text)
                buffer = []
            h, mn, s, ms = int(m[1]), int(m[2]), int(m[3]), int(m[4][:2])
            current_time = h * 3600 + mn * 60 + s + ms / 100
        else:
            if line and not line.startswith(('WEBVTT', 'NOTE')):
                buffer.append(line)

    # Flush last buffer
    if buffer and current_time is not None:
        text = ' '.join(buffer).strip()
        text = re.sub(r'<[^>]+>', '', text)
        if text and (not lines_out or lines_out[-1][1] != text):
            lines_out.append((current_time, text))
            plain_lines.append(text)

    # Build LRC
    lrc_lines = []
    for t, text in lines_out:
        mins = int(t // 60)
        secs = t % 60
        lrc_lines.append(f"[{mins:02d}:{secs:05.2f}] {text}")

    return '\n'.join(plain_lines), '\n'.join(lrc_lines)


# ─── DB-Operationen ──────────────────────────────────────────

async def get_music_info(video_id: str) -> dict:
    """Gibt Musik-Metadaten eines Videos zurück."""
    try:
        row = await db.fetch_one(
            """SELECT is_music, music_artist, music_title, music_album,
                      has_lyrics, lyrics_source, lrclib_id
               FROM videos WHERE id = ?""",
            (video_id,),
        )
    except Exception:
        # Fallback ohne lrclib_id (vor Migration v23)
        row = await db.fetch_one(
            """SELECT is_music, music_artist, music_title, music_album,
                      has_lyrics, lyrics_source
               FROM videos WHERE id = ?""",
            (video_id,),
        )
    if not row:
        return {}
    return {
        "is_music": bool(row["is_music"]),
        "artist": row["music_artist"] or "",
        "title": row["music_title"] or "",
        "album": row["music_album"] or "",
        "has_lyrics": bool(row["has_lyrics"]),
        "lyrics_source": row["lyrics_source"] or "",
        "lrclib_id": row["lrclib_id"] if "lrclib_id" in row.keys() else None,
    }


async def set_music_info(
    video_id: str,
    is_music: bool,
    artist: str = "",
    title: str = "",
    album: str = "",
):
    """Setzt Musik-Metadaten."""
    await db.execute(
        """UPDATE videos SET
             is_music = ?, music_artist = ?, music_title = ?, music_album = ?,
             updated_at = datetime('now')
           WHERE id = ?""",
        (int(is_music), artist, title, album, video_id),
    )


async def set_lyrics_status(video_id: str, has_lyrics: bool, source: str = "", lrclib_id: int = None):
    """Aktualisiert Lyrics-Status."""
    try:
        await db.execute(
            """UPDATE videos SET has_lyrics = ?, lyrics_source = ?, lrclib_id = ?,
                 updated_at = datetime('now')
               WHERE id = ?""",
            (int(has_lyrics), source, lrclib_id, video_id),
        )
    except Exception:
        # Fallback ohne lrclib_id
        await db.execute(
            """UPDATE videos SET has_lyrics = ?, lyrics_source = ?,
                 updated_at = datetime('now')
               WHERE id = ?""",
            (int(has_lyrics), source, video_id),
        )


async def fetch_and_save(video_id: str, provider: str = "auto") -> dict:
    """Kompletter Flow: Provider-Kaskade → speichern.

    provider: 'auto' (ytmusic→lrclib), 'ytmusic', 'lrclib'
    Returns: { status: 'ok'|'not_music'|'not_found'|'error', ... }
    """
    info = await get_music_info(video_id)
    if not info:
        return {"status": "error", "message": "Video nicht gefunden"}

    if not info.get("is_music"):
        return {"status": "not_music", "message": "Video ist nicht als Musik markiert"}

    artist = info.get("artist", "")
    title = info.get("title", "")
    album = info.get("album", "")

    if not artist or not title:
        return {"status": "error", "message": "Artist oder Titel fehlen"}

    # Duration holen
    dur = await db.fetch_val(
        "SELECT duration FROM videos WHERE id = ?", (video_id,)
    )

    result = None

    # ─── Provider-Kaskade ───
    if provider in ("auto", "ytmusic"):
        # 1) YouTube Music per Video-ID (direkt, beste Qualität)
        result = await search_ytmusic(video_id)
        # 2) YouTube Music per Name-Suche (falls Video-ID nicht matched)
        if not result:
            result = await search_ytmusic_by_name(artist, title)
        if result:
            logger.info(f"YTMusic Treffer: {artist} - {title}")

    if not result and provider in ("auto", "lrclib"):
        # 3) LRCLIB
        result = await search_lyrics(artist, title, album, dur or 0)
        if result:
            logger.info(f"LRCLIB Treffer: {artist} - {title}")

    if not result:
        return {"status": "not_found", "message": f"Keine Lyrics für '{artist} - {title}'"}

    # Speichern
    save_lyrics(video_id, result["plain"], result.get("synced"))
    await set_lyrics_status(video_id, True, result["source"], result.get("lrclib_id"))

    # Artist/Title ggf. korrigieren (LRCLIB kann bessere Schreibweise haben)
    if result.get("artist") and result.get("title"):
        await set_music_info(
            video_id, True,
            result["artist"], result["title"],
            result.get("album", album),
        )

    has_synced = bool(result.get("synced"))
    logger.info(f"Lyrics gespeichert: {artist} - {title} (synced={has_synced}, source={result['source']})")

    return {
        "status": "ok",
        "artist": result.get("artist", artist),
        "title": result.get("title", title),
        "album": result.get("album", ""),
        "has_synced": has_synced,
        "source": result["source"],
    }
