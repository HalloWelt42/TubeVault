"""
TubeVault – Kanal-Verweis auflösen

Der Nutzer gibt beim Hinzufügen eines Kanals irgendetwas ein: die Kanal-ID,
eine Kanal-Adresse, ein Handle (@name) oder die Adresse eines Videos. Hier
wird daraus genau eine Kanal-ID - oder eine verständliche Absage. Was nicht
auflösbar ist, wird nie zu einem Abo.
"""
import asyncio
import re

_CHANNEL_ID = re.compile(r"UC[0-9A-Za-z_-]{22}")
_VIDEO_MARKERS = ("youtu.be/", "youtube.com/watch", "youtube.com/shorts/", "youtube.com/live/")
_HANDLE = re.compile(r"@[\w.\-]{3,}")


class UnresolvableChannel(ValueError):
    """Aus der Eingabe lässt sich kein Kanal bestimmen."""


def is_channel_id(text: str) -> bool:
    return bool(_CHANNEL_ID.fullmatch(text or ""))


def _with_scheme(text: str) -> str:
    return text if text.startswith(("http://", "https://")) else f"https://{text}"


def _lookup(text: str) -> str:
    """Synchron (im Thread): die Quelle nach der Kanal-ID fragen."""
    from app.utils.pytube_client import make_channel, make_youtube
    if any(marker in text for marker in _VIDEO_MARKERS):
        return make_youtube(_with_scheme(text)).channel_id or ""
    if "youtube.com/" in text:
        return make_channel(_with_scheme(text)).channel_id or ""
    handle = _HANDLE.fullmatch(text)
    if handle:
        return make_channel(f"https://www.youtube.com/{text}").channel_id or ""
    return ""


async def resolve(text: str) -> str:
    """Eingabe in eine Kanal-ID übersetzen. Wirft UnresolvableChannel."""
    text = (text or "").strip()
    if not text:
        raise UnresolvableChannel("Bitte eine Kanal-ID, eine Kanal-Adresse oder ein Handle eingeben")
    if is_channel_id(text):
        return text
    in_url = re.search(r"youtube\.com/channel/(UC[0-9A-Za-z_-]{22})", text)
    if in_url:
        return in_url.group(1)
    try:
        channel_id = await asyncio.to_thread(_lookup, text)
    except Exception as e:
        raise UnresolvableChannel(f"Kanal nicht auflösbar: {str(e)[:200]}") from e
    if not is_channel_id(channel_id):
        raise UnresolvableChannel(
            f"'{text[:80]}' ist weder Kanal-ID, Kanal-Adresse, Handle noch Video-Adresse")
    return channel_id
