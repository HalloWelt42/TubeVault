"""
TubeVault – Download-Optionen v1.0.0

Die EINE Stelle, die entscheidet, womit ein Video geladen wird.

Vorher legte jeder Einstieg (Suche, Feed, Kanalseite, Sammel-Download, Drip,
Auto-Download, Import, erneutes Laden) selbst fest, welche Qualität gilt -
mal die Einstellung, mal der Kanal, mal ein fester Wert im Frontend. Ergebnis:
"die Einstellungen werden nicht befolgt".

Vorrang (für jede Option einzeln):
    1. Auftrag    - was der Nutzer für genau diesen Download gewählt hat
    2. Kanal      - Vorgabe am Abo des Kanals, zu dem das Video gehört
    3. Standard   - Einstellungen: download.quality für von Hand gestartete,
                    rss.auto_quality für automatische Downloads

Aufträge speichern nur, was ausdrücklich gewählt wurde. Aufgelöst wird beim
Start des Downloads: eine geänderte Einstellung gilt damit auch für bereits
wartende Aufträge.
"""
from typing import Literal, Optional

from pydantic import BaseModel

from app import settings_schema
from app.database import db

Origin = Literal["manual", "auto"]

AUDIO_ONLY = "audio_only"
_OUTPUT_FORMAT = "mp4"


class EffectiveOptions(BaseModel):
    quality: str
    audio_only: bool
    merge_audio: bool
    download_thumbnail: bool
    subtitle_langs: list[str]
    itag: Optional[int] = None
    audio_itag: Optional[int] = None
    format: str = _OUTPUT_FORMAT
    origin: Origin = "manual"
    quality_source: Literal["auftrag", "kanal", "standard"]


async def _setting(key: str) -> str:
    value = await db.fetch_val("SELECT value FROM settings WHERE key = ?", (key,))
    return value if value not in (None, "") else settings_schema.BY_KEY[key].default


async def channel_prefs(video_id: str) -> dict:
    """Vorgaben des Abos, zu dessen Kanal das Video gehört (leer, wenn keins)."""
    row = await db.fetch_one(
        """SELECT s.download_quality, s.audio_only
           FROM subscriptions s
           WHERE s.channel_id = COALESCE(
               (SELECT NULLIF(channel_id, '') FROM videos WHERE id = ?),
               (SELECT channel_id FROM rss_entries WHERE video_id = ? LIMIT 1))""",
        (video_id, video_id))
    return dict(row) if row else {}


def explicit(**wishes) -> dict:
    """Nur ausdrücklich gesetzte Wünsche behalten (None = nicht gewählt)."""
    return {key: value for key, value in wishes.items() if value is not None}


async def effective(video_id: str, requested: dict | None) -> EffectiveOptions:
    """Wirksame Optionen für den Download von video_id."""
    requested = requested or {}
    origin: Origin = "auto" if requested.get("origin") == "auto" else "manual"
    channel = await channel_prefs(video_id)

    wanted_quality = requested.get("quality") or None
    wants_stream = requested.get("itag") is not None or requested.get("audio_itag") is not None

    # Nur-Audio: ausdrücklich gewählt > Kanal. Wer für diesen Download eine
    # Video-Qualität oder einen Stream wählt, will kein Nur-Audio vom Kanal.
    if wanted_quality == AUDIO_ONLY:
        audio_only, wanted_quality = True, None
    elif requested.get("audio_only") is not None:
        audio_only = bool(requested["audio_only"])
    elif wanted_quality or wants_stream:
        audio_only = False
    else:
        audio_only = bool(channel.get("audio_only"))

    if wanted_quality:
        quality, source = wanted_quality, "auftrag"
    elif channel.get("download_quality"):
        quality, source = channel["download_quality"], "kanal"
    else:
        key = "rss.auto_quality" if origin == "auto" else "download.quality"
        quality, source = await _setting(key), "standard"

    if requested.get("download_thumbnail") is not None:
        download_thumbnail = bool(requested["download_thumbnail"])
    else:
        download_thumbnail = (await _setting("download.auto_thumbnail")) == "true"

    if requested.get("subtitle_lang"):
        subtitle_langs = [requested["subtitle_lang"]]
    elif (await _setting("download.auto_subtitle")) == "true":
        raw = await _setting("download.subtitle_lang")
        subtitle_langs = [part.strip() for part in raw.split(",") if part.strip()]
    else:
        subtitle_langs = []

    return EffectiveOptions(
        quality=AUDIO_ONLY if audio_only else quality,
        audio_only=audio_only,
        merge_audio=requested.get("merge_audio", True) is not False,
        download_thumbnail=download_thumbnail,
        subtitle_langs=subtitle_langs,
        itag=requested.get("itag"),
        audio_itag=requested.get("audio_itag"),
        origin=origin,
        quality_source=source,
    )
