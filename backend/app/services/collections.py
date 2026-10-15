"""
TubeVault – Sammlungen

Favoritenlisten und Playlists sind für Anzeige und Wiedergabe dasselbe: eine
geordnete Reihe geladener Videos mit ihrem Stand (neu, angefangen, gesehen).
Diese Stelle liefert sie einheitlich - für die Seiten Favoriten und Playlists,
für die Warteschlange der Wiedergabe und für "Als Ton hören".

Quellen:
  favorites:<Liste>   eine Favoritenliste
  playlist:<Kennung>  eine Playlist
Ändern (Reihenfolge, Hinzufügen, Entfernen) bleibt bei favorites bzw. playlists.
"""
from typing import Optional

from pydantic import BaseModel

from app.database import db
from app.services import watch_state


class Item(BaseModel):
    id: str
    title: str
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    duration: Optional[int] = None
    video_type: Optional[str] = None
    position: int = 0                 # gemerkte Stelle in Sekunden
    progress: float = 0.0             # gesehener Anteil 0..1
    state: watch_state.State = "new"
    added_at: Optional[str] = None    # nur Favoriten merken sich, wann
    last_played: Optional[str] = None
    play_count: int = 0


class Collection(BaseModel):
    source: str
    kind: str                         # favorites | playlist
    title: str
    items: list[Item]
    duration: int                     # Gesamtdauer in Sekunden
    counts: dict[str, int]            # je Stand: new, started, finished


_FIELDS = """v.id, v.title, v.channel_id, v.channel_name, v.duration, v.video_type,
             COALESCE(v.last_position, 0) AS position, v.last_played, COALESCE(v.play_count, 0) AS play_count"""


async def _rows(kind: str, value: str):
    if kind == "favorites":
        return "Favoriten" if value == "Standard" else value, await db.fetch_all(
            f"""SELECT {_FIELDS}, f.added_at FROM favorites f JOIN videos v ON v.id = f.video_id
                WHERE f.list_name = ? AND v.status = 'ready' ORDER BY f.position, f.id""", (value,))
    if kind == "playlist":
        name = await db.fetch_val("SELECT name FROM playlists WHERE id = ?", (value,))
        if name is None:
            raise LookupError("Playlist unbekannt")
        return name, await db.fetch_all(
            f"""SELECT {_FIELDS}, NULL AS added_at FROM playlist_videos p JOIN videos v ON v.id = p.video_id
                WHERE p.playlist_id = ? AND v.status = 'ready' ORDER BY p.position, p.rowid""", (value,))
    raise ValueError("Unbekannte Sammlung")


async def load(source: str) -> Collection:
    kind, _, value = source.partition(":")
    title, rows = await _rows(kind, value)
    items = [Item(**dict(r), progress=watch_state.progress(r["position"], r["duration"]),
                  state=watch_state.state_of(r["position"], r["duration"])) for r in rows]
    counts = {state: sum(1 for i in items if i.state == state) for state in watch_state.STATES}
    return Collection(source=source, kind=kind, title=title, items=items,
                      duration=sum(i.duration or 0 for i in items), counts=counts)


async def video_ids(source: str) -> list[str]:
    return [item.id for item in (await load(source)).items]
