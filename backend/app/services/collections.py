"""
TubeVault – Sammlungen

Favoritenlisten und Playlists sind für Anzeige und Wiedergabe dasselbe: eine
geordnete Reihe geladener Videos mit ihrem Stand (neu, angefangen, gesehen).
Diese Stelle liefert sie einheitlich - für die Seiten Favoriten und Playlists,
für die Warteschlange der Wiedergabe und für "Als Ton hören".

Quellen:
  favorites:<Liste>   eine Favoritenliste
  playlist:<Kennung>  eine Playlist, auch mit noch nicht geladenen Videos
                      (vorgemerkt; loaded=False, Stand "pending", lädt der Drip)
  category:<Kennung>  eine Kategorie in eigener Reihenfolge, je Video der
                      Grund (reason: von Hand oder die Art der Regel)
Ändern (Reihenfolge, Hinzufügen, Entfernen) bleibt bei favorites, playlists
bzw. category_rules.
"""
from typing import Optional

from pydantic import BaseModel

from app.database import db
from app.models.categories import Reason
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
    added_at: Optional[str] = None    # Favoriten und Kategorien merken sich, wann
    upload_date: Optional[str] = None
    last_played: Optional[str] = None
    play_count: int = 0
    loaded: bool = True               # False: vorgemerkt, noch nicht geladen
    reason: Optional[Reason] = None   # nur Kategorien: warum das Video drin ist
    language: Optional[str] = None          # Sprache (services/language) für das Label
    language_source: Optional[str] = None


class Collection(BaseModel):
    source: str
    kind: str                         # favorites | playlist | category
    title: str
    items: list[Item]
    duration: int                     # Gesamtdauer in Sekunden
    counts: dict[str, int]            # je Stand: new, started, finished; pending = noch nicht geladen


_FIELDS = """v.id, v.title, v.channel_id, v.channel_name, v.duration, v.video_type, v.upload_date,
             COALESCE(v.last_position, 0) AS position, v.last_played, COALESCE(v.play_count, 0) AS play_count,
             v.status = 'ready' AS loaded, v.language, v.language_source"""


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
                WHERE p.playlist_id = ? ORDER BY p.position, p.rowid""", (value,))
    if kind == "category":
        name = await db.fetch_val("SELECT name FROM categories WHERE id = ?", (value,))
        if name is None:
            raise LookupError("Kategorie unbekannt")
        return name, await db.fetch_all(
            f"""SELECT {_FIELDS}, c.added_at,
                       CASE WHEN c.origin = 'hand' THEN 'hand' ELSE r.kind END AS reason
                FROM video_categories c JOIN videos v ON v.id = c.video_id
                LEFT JOIN category_rules r ON r.id = c.rule_id
                WHERE c.category_id = ? AND v.status = 'ready' ORDER BY c.position, c.rowid""", (value,))
    raise ValueError("Unbekannte Sammlung")


async def load(source: str) -> Collection:
    kind, _, value = source.partition(":")
    title, rows = await _rows(kind, value)
    items = [Item(**{**dict(r), "loaded": bool(r["loaded"])}, progress=watch_state.progress(r["position"], r["duration"]),
                  state=watch_state.state_of(r["position"], r["duration"])) for r in rows]
    counts = {state: sum(1 for i in items if i.loaded and i.state == state) for state in watch_state.STATES}
    counts["pending"] = sum(1 for i in items if not i.loaded)
    return Collection(source=source, kind=kind, title=title, items=items,
                      duration=sum(i.duration or 0 for i in items), counts=counts)


async def video_ids(source: str) -> list[str]:
    """Die geladenen Videos (abspielbar), in der Reihenfolge der Sammlung."""
    return [item.id for item in (await load(source)).items if item.loaded]
