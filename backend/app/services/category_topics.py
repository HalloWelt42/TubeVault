"""
TubeVault - Kategorien: Themen erkennen

Die lokale KI schlägt Kategorien vor; nichts geschieht ohne Klick.
  1. Videos ohne Kategorie nach ihren Vektoren in Gruppen teilen (k-means
     auf der Einheitskugel, fester Startwert: gleiche Daten, gleiche Gruppen).
  2. Das Sprachmodell benennt jede Gruppe und beschreibt ihren Inhalt als
     Text für die Regel "Inhaltlich wie" (Oberthema: Stichwörter).
  3. Jede Beschreibung wird wie eine echte Regel ausgewertet: so viele
     Videos kämen hinein, vor allem aus diesen Kanälen. Was nichts oder
     fast nichts träfe, fällt weg.
Die Vorschläge bleiben gespeichert, bis sie übernommen oder verworfen
werden oder ein neuer Lauf sie ersetzt.
"""
import asyncio
import json
import logging
import math
import re
from typing import Optional

from app.database import db
from app.models.categories import CategoryCreate, RuleIn, TopicAccept, TopicState, TopicSuggestion
from app.services import ai_chat, categories, category_rules, semantic_index
from app.utils.file_utils import now_sqlite

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS category_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    query TEXT NOT NULL,
    precision TEXT NOT NULL,
    match_count INTEGER NOT NULL DEFAULT 0,
    channels TEXT NOT NULL DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now'))
);
"""

MIN_VIDEOS = 20             # darunter lohnt das Gruppieren nicht
MAX_GROUPS = 10
MIN_MATCHES = 3             # ein Vorschlag muss wenigstens so viele Videos treffen
TITLES_PER_GROUP = 15
CHANNELS_SHOWN = 3
NAME_MAX = 60
QUERY_MAX = 200

PHASE_GROUPING = "Videos werden nach Inhalt gruppiert"
PHASE_NAMING = "Die KI benennt die Themen"
PHASE_COUNTING = "Passende Videos werden gezählt"

_SYSTEM = """Du ordnest eine private Videosammlung nach Themen. Du bekommst nummerierte Gruppen inhaltlich ähnlicher Videos, je Gruppe die häufigsten Kanäle und typische Titel.

Für jede Gruppe gibst du an:
- erkennbar: true, wenn die Titel ein gemeinsames Thema haben; false bei einem bunten Gemisch ohne Thema.
- name: kurzer deutscher Name einer Kategorie, ein bis drei Wörter, etwa "Mathematik" oder "Astronomie und Raumfahrt". Kein Kanalname.
- beschreibung: Text, mit dem eine Bedeutungssuche passende Videos findet: das Oberthema, ein Doppelpunkt, dann vier bis sechs typische Stichwörter mit Komma getrennt, etwa "Kochen und Backen: Rezepte, Brot, Pizza, Kuchen". Kein Kanalname.

Schreibe Deutsch mit echten Umlauten (ä, ö, ü, ß). Gib jede Gruppennummer genau einmal zurück. Haben zwei Gruppen dasselbe Thema, bekommen sie denselben Namen."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "gruppen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nummer": {"type": "integer"},
                    "erkennbar": {"type": "boolean"},
                    "name": {"type": "string"},
                    "beschreibung": {"type": "string"},
                },
                "required": ["nummer", "erkennbar", "name", "beschreibung"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["gruppen"],
    "additionalProperties": False,
}

_state: dict = {"running": False, "phase": None, "done": 0, "total": 0, "error": None, "finished_at": None}
_task: Optional[asyncio.Task] = None


async def install_schema(connection) -> None:
    await connection.executescript(SCHEMA_SQL)
    await connection.commit()


# ─── Gruppieren ───────────────────────────────────────────────────────

def group_count(videos: int) -> int:
    """Wie viele Gruppen: wächst mit der Wurzel der Menge, 3 bis 12."""
    return min(12, max(3, round(math.sqrt(videos / 12))))


def cluster(matrix, groups: int, iterations: int = 25, seed: int = 7):
    """k-means auf normierten Vektoren (Ähnlichkeit = Skalarprodukt).
    Gibt (Gruppe je Zeile, Mittelpunkte) zurück."""
    import numpy as np
    rng = np.random.default_rng(seed)
    count = matrix.shape[0]
    groups = max(1, min(groups, count))
    # Start nach k-means++: weit voneinander entfernte Punkte
    centers = [matrix[rng.integers(count)]]
    distance = np.maximum(0.0, 1.0 - matrix @ centers[0])
    for _ in range(1, groups):
        total = float(distance.sum())
        pick = rng.choice(count, p=distance / total) if total > 0 else rng.integers(count)
        centers.append(matrix[pick])
        distance = np.minimum(distance, np.maximum(0.0, 1.0 - matrix @ matrix[pick]))
    centers = np.stack(centers)
    labels = np.zeros(count, dtype=int)
    for _ in range(iterations):
        labels = np.argmax(matrix @ centers.T, axis=1)
        moved = centers.copy()
        for index in range(groups):
            members = matrix[labels == index]
            if len(members):
                mean = members.sum(axis=0)
                norm = float(np.linalg.norm(mean))
                if norm:
                    moved[index] = mean / norm
        if np.allclose(moved, centers, atol=1e-5):
            break
        centers = moved
    return labels, centers


# ─── Ablauf ───────────────────────────────────────────────────────────

def _set(**changes) -> None:
    _state.update(changes)


async def _unsorted_vectors():
    library = await semantic_index.all_vectors()
    if library is None:
        return None
    ids, matrix = library
    unsorted = {row["id"] for row in await db.fetch_all(
        """SELECT v.id FROM videos v WHERE v.status = 'ready'
           AND NOT EXISTS (SELECT 1 FROM video_categories vc WHERE vc.video_id = v.id)""")}
    rows = [index for index, vid in enumerate(ids) if vid in unsorted]
    return [ids[i] for i in rows], matrix[rows]


async def _describe_groups(ids: list[str], matrix, labels, centers) -> list[dict]:
    """Je ausreichend große Gruppe: Größe, typische Titel, häufigste Kanäle."""
    import numpy as np
    smallest = max(5, int(len(ids) * 0.01))
    sizes = [(int((labels == index).sum()), index) for index in range(len(centers))]
    result = []
    for size, index in sorted(sizes, reverse=True)[:MAX_GROUPS]:
        if size < smallest:
            continue
        members = np.nonzero(labels == index)[0]
        nearest = members[np.argsort(-(matrix[members] @ centers[index]))[:TITLES_PER_GROUP]]
        chosen = [ids[i] for i in nearest]
        marks = ",".join("?" * len(chosen))
        titles = {row["id"]: row["title"] for row in await db.fetch_all(
            f"SELECT id, title FROM videos WHERE id IN ({marks})", chosen)}
        member_ids = [ids[i] for i in members]
        result.append({"size": size, "titles": [titles[v] for v in chosen if v in titles],
                       "channels": await _top_channels(member_ids)})
    return result


async def _top_channels(video_ids: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    for start in range(0, len(video_ids), 500):
        chunk = video_ids[start:start + 500]
        for row in await db.fetch_all(
                f"""SELECT channel_id, COUNT(*) AS n FROM videos WHERE id IN ({",".join("?" * len(chunk))})
                    AND channel_id IS NOT NULL GROUP BY channel_id""", chunk):
            counts[row["channel_id"]] = counts.get(row["channel_id"], 0) + row["n"]
    top = sorted(counts, key=lambda c: -counts[c])[:CHANNELS_SHOWN]
    names = await category_rules.channel_names(top)
    return [names.get(c, c) for c in top]


def _prompt(groups: list[dict], existing: list[str]) -> str:
    parts = []
    if existing:
        parts.append("Diese Kategorien gibt es schon, schlage sie nicht noch einmal vor: " + ", ".join(existing))
    for number, group in enumerate(groups, start=1):
        lines = [f"Gruppe {number} ({group['size']} Videos)", "Kanäle: " + ", ".join(group["channels"]), "Titel:"]
        lines += [f"- {title}" for title in group["titles"]]
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _degenerate(text: str) -> bool:
    """Wiederholungsschleifen und Kommentare des Modells erkennen."""
    return bool(re.search(r"(\w{3,})\1{3,}", text) or re.search(r"\w{50,}", text) or "//" in text.replace("://", ""))


def read_answer(answer: dict, groups: int) -> list[tuple[str, str]]:
    """(Name, Beschreibung) je erkennbarer Gruppe, gesäubert, ohne Doppel."""
    topics: dict[str, tuple[str, str]] = {}
    for entry in answer.get("gruppen") or []:
        if not isinstance(entry, dict) or not entry.get("erkennbar"):
            continue
        number = entry.get("nummer")
        name = ai_chat.plain(str(entry.get("name") or "")).strip(" .:\"'")[:NAME_MAX]
        query = ai_chat.plain(str(entry.get("beschreibung") or ""))[:QUERY_MAX]
        if not isinstance(number, int) or not 1 <= number <= groups or not name or not query:
            continue
        if _degenerate(name) or _degenerate(query):
            continue
        topics.setdefault(name.casefold(), (name, query))
    return list(topics.values())


async def _run() -> None:
    try:
        _set(running=True, phase=PHASE_GROUPING, done=0, total=0, error=None)
        data = await _unsorted_vectors()
        if data is None:
            raise ai_chat.ChatUnavailable("Die Bedeutungssuche hat noch keine Videos erfasst")
        ids, matrix = data
        if len(ids) < MIN_VIDEOS:
            raise ai_chat.ChatUnavailable("Zu wenige Videos ohne Kategorie")
        labels, centers = await asyncio.to_thread(cluster, matrix, group_count(len(ids)))
        groups = await _describe_groups(ids, matrix, labels, centers)
        if not groups:
            raise ai_chat.ChatUnavailable("Keine deutlichen Themen gefunden")

        _set(phase=PHASE_NAMING)
        existing = [row["name"] for row in await db.fetch_all("SELECT name FROM categories ORDER BY name")]
        answer = await ai_chat.complete_json(_SYSTEM, _prompt(groups, existing), "themen", _SCHEMA)
        known = {name.casefold() for name in existing}
        topics = [(name, query) for name, query in read_answer(answer, len(groups)) if name.casefold() not in known]

        _set(phase=PHASE_COUNTING, total=len(topics))
        precision = await category_rules.default_precision()
        found = []
        for name, query in topics:
            matched = await category_rules.matches([RuleIn(kind="semantic", value=query, precision=precision)])
            if matched is None:
                raise ai_chat.ChatUnavailable("Der KI-Dienst ist nicht mehr erreichbar")
            if len(matched) >= MIN_MATCHES:
                found.append((name, query, len(matched), await _top_channels(list(matched))))
            _set(done=_state["done"] + 1)

        await db.conn.execute("DELETE FROM category_suggestions")
        await db.conn.executemany(
            "INSERT INTO category_suggestions (name, query, precision, match_count, channels) VALUES (?, ?, ?, ?, ?)",
            [(name, query, precision, count, json.dumps(channels, ensure_ascii=False))
             for name, query, count, channels in sorted(found, key=lambda f: -f[2])])
        await db.conn.commit()
        if not found:
            _set(error="Keine Themen gefunden, die genug Videos treffen")
    except ai_chat.ChatUnavailable as e:
        _set(error=str(e))
    except Exception as e:
        logger.warning(f"[THEMEN] Lauf fehlgeschlagen: {e.__class__.__name__}: {e}")
        _set(error="Themen erkennen ist fehlgeschlagen")
    finally:
        _set(running=False, phase=None, finished_at=now_sqlite())


def start() -> bool:
    """Einen Lauf starten; False, wenn schon einer läuft."""
    global _task
    if _state["running"]:
        return False
    _set(running=True, phase=PHASE_GROUPING, done=0, total=0, error=None)
    _task = asyncio.create_task(_run())
    return True


# ─── Vorschläge ───────────────────────────────────────────────────────

async def suggestions() -> list[TopicSuggestion]:
    rows = await db.fetch_all("SELECT * FROM category_suggestions ORDER BY match_count DESC, id")
    return [TopicSuggestion(id=row["id"], name=row["name"], query=row["query"], precision=row["precision"],
                            match_count=row["match_count"], channels=json.loads(row["channels"] or "[]"))
            for row in rows]


async def state() -> TopicState:
    return TopicState(**{key: _state[key] for key in ("running", "phase", "done", "total", "error", "finished_at")},
                      suggestions=await suggestions())


async def accept(suggestion_id: int, changes: TopicAccept) -> int:
    """Vorschlag übernehmen (wahlweise geändert): Kategorie samt Regel anlegen."""
    row = await db.fetch_one("SELECT * FROM category_suggestions WHERE id = ?", (suggestion_id,))
    if not row:
        raise LookupError("Den Vorschlag gibt es nicht mehr")
    rules = changes.rules if changes.rules is not None else [
        RuleIn(kind="semantic", value=row["query"], precision=row["precision"])]
    category_id = await categories.create(CategoryCreate(name=changes.name or row["name"], color=changes.color,
                                                         rules=rules))
    await db.execute("DELETE FROM category_suggestions WHERE id = ?", (suggestion_id,))
    return category_id


async def dismiss(suggestion_id: int) -> None:
    await db.execute("DELETE FROM category_suggestions WHERE id = ?", (suggestion_id,))
