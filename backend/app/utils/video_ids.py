"""
TubeVault – Kennungen von Videos

Die eine Stelle für die Frage "ist das ein Video der Quelle?". Videos der
Quelle haben eine Kennung aus genau 11 Zeichen; eigene Videos tragen
own_<12 Zeichen>, ältere Importe local_<12 Zeichen>. Nur Videos der Quelle
haben Kapitel, Werbemarken, Bewertungen und Bilder bei der Quelle.
"""
import re

_SOURCE_ID = re.compile(r"[A-Za-z0-9_-]{11}")


def is_source_video(video_id: str | None) -> bool:
    return bool(video_id) and _SOURCE_ID.fullmatch(video_id) is not None
