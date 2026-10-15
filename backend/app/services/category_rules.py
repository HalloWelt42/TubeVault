"""
TubeVault - Kategorien: Regeln und Zugehörigkeit

Die eine Stelle, die entscheidet, welche Videos in einer Kategorie sind.

Zugehörigkeit (video_categories):
  origin 'hand'   von Hand hineingelegt - bleibt, was die Regeln auch sagen
  origin 'rule'   eine Regel passt (rule_id: die erste passende in der Reihenfolge)
Von Hand Herausgenommenes steht in category_exclusions; keine Regel bringt
es zurück. Erst erneutes Hineinlegen von Hand hebt das auf.

Regeln (category_rules), nur fertig geladene Videos zählen:
  channel    Kanal ist            value = Kanal-Kennung
  tag        Schlagwort enthält   value = Wort; ohne Groß/Klein, auch als Teil eines Schlagworts
  semantic   Inhaltlich wie       value = Beschreibung, precision = Stufe der Bedeutungssuche.
             Vektor und Schwelle stehen abgeleitet in category_rule_vectors
             (beim Speichern gerechnet). So ordnen sich neue Videos ein, ohne
             die KI zu fragen, und die Schwelle wandert nicht mit der Sammlung.

Neue und geänderte Videos merkt ein Trigger in category_dirty vor - auch,
sobald ein Video seinen Vektor bekommt; der Hintergrundlauf ordnet sie ein.
Eigene Reihenfolge: kleinste position steht oben, Neues kommt oben dazu.
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Iterable, Optional

from app.database import db
from app.models.categories import ApplyResult, Membership, PreviewVideo, RuleIn, RulePreview
from app.services import semantic_index, setting_values

logger = logging.getLogger(__name__)

TAG_MAX = 60
_CHUNK = 500                # Kennungen je IN-Liste
_SAMPLES = 6
_WORKER_BATCH = 500
_WORKER_PAUSE_S = 20

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS category_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('channel', 'tag', 'semantic')),
    value TEXT NOT NULL,
    precision TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_category_rules_category ON category_rules(category_id, position);

-- abgeleitet aus Text und Stufe einer Regel "Inhaltlich wie" (wird nicht gesichert)
CREATE TABLE IF NOT EXISTS category_rule_vectors (
    rule_id INTEGER PRIMARY KEY,
    model TEXT NOT NULL,
    vector BLOB NOT NULL,
    threshold REAL NOT NULL,
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (rule_id) REFERENCES category_rules(id) ON DELETE CASCADE
);

-- von Hand herausgenommen: keine Regel bringt das Video zurück
CREATE TABLE IF NOT EXISTS category_exclusions (
    category_id INTEGER NOT NULL,
    video_id TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (category_id, video_id),
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE,
    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_category_exclusions_video ON category_exclusions(video_id);
CREATE INDEX IF NOT EXISTS idx_video_categories_order ON video_categories(category_id, position);

-- Warteliste: diese Videos neu einordnen. Die Trigger fügen nur ein, was noch
-- fehlt (kein OR IGNORE: bei einem Upsert gälte dessen Konfliktregel)
CREATE TABLE IF NOT EXISTS category_dirty (video_id TEXT PRIMARY KEY);
"""

# Trigger der Warteliste: bei jedem Start neu angelegt, damit immer die
# aktuelle Fassung gilt
TRIGGERS_SQL = """
DROP TRIGGER IF EXISTS trg_category_dirty_insert;
DROP TRIGGER IF EXISTS trg_category_dirty_update;
DROP TRIGGER IF EXISTS trg_category_dirty_vector;
DROP TRIGGER IF EXISTS trg_category_dirty_vector_update;
DROP TRIGGER IF EXISTS trg_category_dirty_delete;
CREATE TRIGGER trg_category_dirty_insert AFTER INSERT ON videos
WHEN new.status = 'ready'
BEGIN
    INSERT INTO category_dirty (video_id) SELECT new.id
    WHERE NOT EXISTS (SELECT 1 FROM category_dirty WHERE video_id = new.id);
END;
CREATE TRIGGER trg_category_dirty_update
AFTER UPDATE OF status, channel_id, tags ON videos
BEGIN
    INSERT INTO category_dirty (video_id) SELECT new.id
    WHERE NOT EXISTS (SELECT 1 FROM category_dirty WHERE video_id = new.id);
END;
CREATE TRIGGER trg_category_dirty_vector AFTER INSERT ON video_embeddings
BEGIN
    INSERT INTO category_dirty (video_id) SELECT new.video_id
    WHERE NOT EXISTS (SELECT 1 FROM category_dirty WHERE video_id = new.video_id);
END;
CREATE TRIGGER trg_category_dirty_vector_update AFTER UPDATE OF vector ON video_embeddings
BEGIN
    INSERT INTO category_dirty (video_id) SELECT new.video_id
    WHERE NOT EXISTS (SELECT 1 FROM category_dirty WHERE video_id = new.video_id);
END;
CREATE TRIGGER trg_category_dirty_delete AFTER DELETE ON videos
BEGIN
    DELETE FROM category_dirty WHERE video_id = old.id;
END;
"""

# Spalten der Zugehörigkeit, die zum alten Bestand dazukamen (v52)
_MEMBERSHIP_COLUMNS = (
    ("origin", "TEXT NOT NULL DEFAULT 'hand'"),
    ("rule_id", "INTEGER"),
    ("position", "INTEGER NOT NULL DEFAULT 0"),
    ("added_at", "TEXT"),
)

# Bestand: alle bisherigen Zuordnungen gelten als von Hand; eigene
# Reihenfolge nach Erscheinen, neueste oben
_POSITION_BACKFILL = """
WITH ordered AS (
    SELECT vc.rowid AS rid,
           ROW_NUMBER() OVER (PARTITION BY vc.category_id
                              ORDER BY COALESCE(v.upload_date, '') DESC, vc.rowid) - 1 AS pos
    FROM video_categories vc LEFT JOIN videos v ON v.id = vc.video_id)
UPDATE video_categories SET position = (SELECT pos FROM ordered WHERE ordered.rid = video_categories.rowid)
"""

# Schreibende Wege (Speichern, von Hand, Hintergrundlauf) nacheinander
_lock = asyncio.Lock()


class RulesUnavailable(Exception):
    """Eine Regel "Inhaltlich wie" lässt sich gerade nicht rechnen (KI fehlt)."""


async def install_schema(connection) -> list[str]:
    """Tabellen, Trigger und die neuen Spalten der Zugehörigkeit anlegen.
    Gibt die neu ergänzten Spalten zurück (leer: nichts zu tun)."""
    cursor = await connection.execute("PRAGMA table_info(video_categories)")
    present = {row[1] for row in await cursor.fetchall()}
    added = []
    for column, definition in _MEMBERSHIP_COLUMNS:
        if column not in present:
            await connection.execute(f"ALTER TABLE video_categories ADD COLUMN {column} {definition}")
            added.append(column)
    if "position" in added:
        await connection.execute(_POSITION_BACKFILL)
    await connection.executescript(SCHEMA_SQL)
    await connection.executescript(TRIGGERS_SQL)
    await connection.commit()
    return added


# ─── Hilfen ───────────────────────────────────────────────────────────

def _chunks(items: list, size: int = _CHUNK):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _marks(items) -> str:
    return ",".join("?" * len(items))


async def _rows_for(sql: str, params: tuple, ids: Optional[list[str]], column: str = "id"):
    """Abfrage, wahlweise auf bestimmte Videos beschränkt (in Stücken)."""
    if ids is None:
        return await db.fetch_all(sql, params)
    rows = []
    for chunk in _chunks(ids):
        rows += await db.fetch_all(f"{sql} AND {column} IN ({_marks(chunk)})", (*params, *chunk))
    return rows


def tag_matches(raw_tags, needle: str) -> bool:
    """Enthält eines der Schlagwörter das Wort? (ohne Groß/Klein)"""
    try:
        tags = json.loads(raw_tags) if isinstance(raw_tags, str) else (raw_tags or [])
    except (ValueError, TypeError):
        return False
    folded = needle.casefold()
    return isinstance(tags, list) and any(folded in str(tag).casefold() for tag in tags)


def _like_prefilter(needle: str) -> Optional[str]:
    """LIKE-Muster zum Vorsortieren - nur bei einfachen Wörtern, denn
    Schlagwörter stehen teils mit \\u-Umschreibung im JSON."""
    folded = needle.casefold()
    return f"%{folded}%" if re.fullmatch(r"[a-z0-9 \-]+", folded) else None


async def default_precision() -> str:
    choice = await setting_values.get("ai.precision")
    return choice if choice in semantic_index.PRECISIONS else semantic_index.DEFAULT_PRECISION


async def channel_names(channel_ids: Iterable[str]) -> dict[str, str]:
    """Anzeigenamen von Kanälen: aus dem Abo, sonst aus den Videos."""
    ids = list(dict.fromkeys(channel_ids))
    names: dict[str, str] = {}
    for chunk in _chunks(ids):
        for row in await db.fetch_all(
                f"SELECT channel_id, channel_name FROM subscriptions WHERE channel_id IN ({_marks(chunk)})", chunk):
            if row["channel_name"]:
                names[row["channel_id"]] = row["channel_name"]
        missing = [c for c in chunk if c not in names]
        if missing:
            for row in await db.fetch_all(
                    f"""SELECT channel_id, MAX(channel_name) AS name FROM videos
                        WHERE channel_id IN ({_marks(missing)}) AND channel_name IS NOT NULL GROUP BY channel_id""",
                    missing):
                names[row["channel_id"]] = row["name"]
    return names


def rule_label(kind: str, value: str, names: dict[str, str]) -> str:
    return names.get(value, value) if kind == "channel" else value


# ─── Regeln prüfen und auflösen ───────────────────────────────────────

async def normalize(rules: list[RuleIn]) -> list[RuleIn]:
    """Regeln prüfen und vereinheitlichen; doppelte fallen weg.
    ValueError mit deutscher Meldung bei ungültigen Angaben."""
    result: list[RuleIn] = []
    seen = set()
    for rule in rules:
        if rule.kind == "semantic":
            precision = rule.precision if rule.precision in semantic_index.PRECISIONS else await default_precision()
            rule = RuleIn(kind="semantic", value=rule.value, precision=precision)
        else:
            rule = RuleIn(kind=rule.kind, value=rule.value)
        if rule.kind == "tag" and len(rule.value) > TAG_MAX:
            raise ValueError(f"Ein Schlagwort hat höchstens {TAG_MAX} Zeichen")
        if rule.kind == "channel" and not await db.fetch_val(
                """SELECT 1 FROM videos WHERE channel_id = ?
                   UNION SELECT 1 FROM subscriptions WHERE channel_id = ? LIMIT 1""", (rule.value, rule.value)):
            raise ValueError("Diesen Kanal gibt es in der Bibliothek nicht")
        key = (rule.kind, rule.value.casefold() if rule.kind != "channel" else rule.value, rule.precision)
        if key not in seen:
            seen.add(key)
            result.append(rule)
    return result


@dataclass
class _Rule:
    """Eine Regel, bereit zum Auswerten."""
    kind: str
    value: str
    precision: Optional[str] = None
    rule_id: Optional[int] = None
    vector: object = None           # numpy-Vektor (nur semantic)
    threshold: Optional[float] = None
    model: Optional[str] = None

    @property
    def key(self) -> tuple:
        return self.kind, self.value, self.precision


def _unpack(blob: bytes):
    import numpy as np
    return np.frombuffer(blob, dtype=np.float32)


async def _saved_rules(category_id: int) -> list[_Rule]:
    rows = await db.fetch_all(
        """SELECT r.id, r.kind, r.value, r.precision, v.model, v.vector, v.threshold
           FROM category_rules r LEFT JOIN category_rule_vectors v ON v.rule_id = r.id
           WHERE r.category_id = ? ORDER BY r.position, r.id""", (category_id,))
    return [_Rule(kind=r["kind"], value=r["value"], precision=r["precision"], rule_id=r["id"],
                  vector=_unpack(r["vector"]) if r["vector"] else None,
                  threshold=r["threshold"], model=r["model"]) for r in rows]


@dataclass
class _Resolved:
    rules: list[_Rule]
    missing: bool = False       # eine neue "Inhaltlich wie" ließ sich nicht rechnen (Speichern geht nicht)
    idle: bool = False          # eine gespeicherte trifft gerade nichts (KI aus oder anderes Modell)


async def _resolve(category_id: Optional[int], rules: list[RuleIn]) -> _Resolved:
    """Regeln samt Vektor und Schwelle. Unveränderte gespeicherte Regeln
    behalten ihre Werte (so zeigt die Vorschau, was das Speichern ergibt;
    ohne KI bleiben sie erhalten). Neue "Inhaltlich wie" werden gerechnet."""
    saved = {rule.key: rule for rule in await _saved_rules(category_id)} if category_id else {}
    cfg = await semantic_index.config()
    model = cfg[1] if cfg else None
    result = _Resolved(rules=[])
    library = None
    for rule in rules:
        item = _Rule(kind=rule.kind, value=rule.value, precision=rule.precision)
        known = saved.get(item.key)
        if known:
            item.rule_id = known.rule_id
        result.rules.append(item)
        if rule.kind != "semantic":
            continue
        if known and known.vector is not None and known.model == model:
            item.vector, item.threshold, item.model = known.vector, known.threshold, known.model
            continue
        vector = await semantic_index.text_vector(rule.value)
        library = library or await semantic_index.all_vectors()
        if vector is not None and library is not None and vector.shape[0] == library[1].shape[1]:
            level = semantic_index.PRECISIONS[rule.precision]
            item.vector, item.model = vector, model
            item.threshold = semantic_index.rule_floor(library[1] @ vector, level, len(library[0]))
        elif known and known.vector is not None:
            # gespeichert, aber gerade nicht neu zu rechnen: bleibt, trifft vorerst nichts
            item.vector, item.threshold, item.model = known.vector, known.threshold, known.model
            result.idle = True
        else:
            result.missing = True
    return result


# ─── Auswerten ────────────────────────────────────────────────────────

async def _only_ready(ids: list[str]) -> set[str]:
    rows = await _rows_for("SELECT id FROM videos WHERE status = 'ready'", (), ids)
    return {row["id"] for row in rows}


async def _semantic_hits(rule: _Rule, subset: Optional[list[str]]) -> set[str]:
    import numpy as np
    cfg = await semantic_index.config()
    if rule.vector is None or not cfg or rule.model != cfg[1]:
        return set()
    if subset is None:
        library = await semantic_index.all_vectors()
        if library is None or library[1].shape[1] != rule.vector.shape[0]:
            return set()
        ids, matrix = library
        found = [ids[i] for i in np.nonzero(matrix @ rule.vector >= rule.threshold)[0]]
        return await _only_ready(found)
    rows = await _rows_for(
        """SELECT e.video_id, e.vector FROM video_embeddings e JOIN videos v ON v.id = e.video_id
           WHERE e.model = ? AND v.status = 'ready'""", (rule.model,), subset, column="e.video_id")
    return {row["video_id"] for row in rows
            if (vector := _unpack(row["vector"])).shape == rule.vector.shape
            and float(vector @ rule.vector) >= rule.threshold}


async def _match(rule: _Rule, subset: Optional[list[str]]) -> set[str]:
    """Fertige Videos, auf die eine Regel passt (wahlweise nur unter subset)."""
    if rule.kind == "channel":
        rows = await _rows_for("SELECT id FROM videos WHERE status = 'ready' AND channel_id = ?", (rule.value,), subset)
        return {row["id"] for row in rows}
    if rule.kind == "tag":
        sql, params = "SELECT id, tags FROM videos WHERE status = 'ready' AND tags IS NOT NULL AND tags != '[]'", ()
        pattern = _like_prefilter(rule.value)
        if pattern:
            sql, params = f"{sql} AND tags LIKE ?", (pattern,)
        rows = await _rows_for(sql, params, subset)
        return {row["id"] for row in rows if tag_matches(row["tags"], rule.value)}
    if rule.kind == "semantic":
        return await _semantic_hits(rule, subset)
    return set()


async def _evaluate(rules: list[_Rule], subset: Optional[list[str]] = None) -> tuple[dict[str, int], list[set[str]]]:
    """Video -> Stelle der ersten passenden Regel, dazu die Treffer je Regel."""
    hits = [await _match(rule, subset) for rule in rules]
    first: dict[str, int] = {}
    for index, found in enumerate(hits):
        for video_id in found:
            first.setdefault(video_id, index)
    return first, hits


# ─── Zugehörigkeit abgleichen ─────────────────────────────────────────

async def _idle_rule_ids(rules: list[_Rule]) -> set[int]:
    """Gespeicherte "Inhaltlich wie", die gerade nichts treffen können (kein
    Vektor des aktuellen Modells, KI aus). Wer über sie hineinkam, bleibt."""
    cfg = await semantic_index.config()
    model = cfg[1] if cfg else None
    return {rule.rule_id for rule in rules
            if rule.kind == "semantic" and rule.rule_id and (rule.vector is None or rule.model != model)}


async def _top_positions(category_id: int, video_ids: list[str]) -> dict[str, int]:
    """Plätze oben in der eigenen Reihenfolge, das neueste Video zuoberst."""
    top = await db.fetch_val("SELECT MIN(position) FROM video_categories WHERE category_id = ?", (category_id,))
    dates = {}
    for chunk in _chunks(video_ids):
        for row in await db.fetch_all(
                f"SELECT id, COALESCE(upload_date, '') AS d FROM videos WHERE id IN ({_marks(chunk)})", chunk):
            dates[row["id"]] = row["d"]
    ordered = sorted(video_ids, key=lambda vid: (dates.get(vid, ""), vid))
    start = top if top is not None else 0
    return {vid: start - 1 - index for index, vid in enumerate(ordered)}


async def _sync(category_id: int, target_rules: dict[str, int], subset: Optional[list[str]],
                keep_rules: frozenset = frozenset()) -> ApplyResult:
    """Zeilen mit origin 'rule' an die Treffer angleichen (von Hand Gelegtes
    und Herausgenommenes bleibt, ebenso was über eine gerade nicht
    auswertbare Regel kam: keep_rules). subset: nur diese Videos betrachten."""
    rows = await _rows_for("SELECT video_id, origin, rule_id FROM video_categories WHERE category_id = ?",
                           (category_id,), subset, column="video_id")
    excluded = {row["video_id"] for row in await _rows_for(
        "SELECT video_id FROM category_exclusions WHERE category_id = ?", (category_id,), subset, column="video_id")}
    hand = {row["video_id"] for row in rows if row["origin"] == "hand"}
    current = {row["video_id"]: row["rule_id"] for row in rows if row["origin"] == "rule"}
    target = {vid: rid for vid, rid in target_rules.items() if vid not in hand and vid not in excluded}

    remove = [vid for vid, rid in current.items() if vid not in target and rid not in keep_rules]
    update = [(rid, category_id, vid) for vid, rid in target.items() if vid in current and current[vid] != rid]
    insert = [vid for vid in target if vid not in current]
    connection = db.conn
    if remove:
        await connection.executemany(
            "DELETE FROM video_categories WHERE category_id = ? AND video_id = ? AND origin = 'rule'",
            [(category_id, vid) for vid in remove])
    if update:
        await connection.executemany(
            "UPDATE video_categories SET rule_id = ? WHERE category_id = ? AND video_id = ?", update)
    if insert:
        positions = await _top_positions(category_id, insert)
        await connection.executemany(
            """INSERT OR IGNORE INTO video_categories (video_id, category_id, origin, rule_id, position, added_at)
               VALUES (?, ?, 'rule', ?, ?, datetime('now'))""",
            [(vid, category_id, target[vid], positions[vid]) for vid in insert])
    await connection.commit()
    return ApplyResult(added=len(insert), removed=len(remove))


async def _apply_category(category_id: int) -> ApplyResult:
    rules = await _saved_rules(category_id)
    matched, _ = await _evaluate(rules)
    return await _sync(category_id, {vid: rules[i].rule_id for vid, i in matched.items()}, None,
                       frozenset(await _idle_rule_ids(rules)))


async def apply_category(category_id: int) -> ApplyResult:
    """Alle Videos gegen die gespeicherten Regeln einer Kategorie prüfen."""
    async with _lock:
        return await _apply_category(category_id)


async def _apply_videos(video_ids: list[str]) -> int:
    ids = list(dict.fromkeys(video_ids))
    changed = 0
    for row in await db.fetch_all("SELECT DISTINCT category_id FROM category_rules"):
        rules = await _saved_rules(row["category_id"])
        matched, _ = await _evaluate(rules, ids)
        result = await _sync(row["category_id"], {vid: rules[i].rule_id for vid, i in matched.items()}, ids,
                             frozenset(await _idle_rule_ids(rules)))
        changed += result.added + result.removed
    return changed


async def apply_videos(video_ids: list[str]) -> int:
    """Einzelne Videos in alle Kategorien mit Regeln einordnen. Gibt die
    Zahl der Änderungen zurück."""
    async with _lock:
        return await _apply_videos(video_ids)


# ─── Vorschau und Speichern ───────────────────────────────────────────

async def _members(category_id: Optional[int]) -> tuple[set[str], dict[str, int], set[str]]:
    """(alle Videos, per Regel drin mit Regel, von Hand herausgenommen) einer Kategorie."""
    if not category_id:
        return set(), {}, set()
    rows = await db.fetch_all(
        """SELECT vc.video_id, vc.origin, vc.rule_id FROM video_categories vc JOIN videos v ON v.id = vc.video_id
           WHERE vc.category_id = ? AND v.status = 'ready'""", (category_id,))
    excluded = await db.fetch_all("SELECT video_id FROM category_exclusions WHERE category_id = ?", (category_id,))
    return ({row["video_id"] for row in rows},
            {row["video_id"]: row["rule_id"] for row in rows if row["origin"] == "rule"},
            {row["video_id"] for row in excluded})


async def _newest(video_ids: set[str], limit: int) -> list[PreviewVideo]:
    rows = await _rows_for("SELECT id, title, channel_name, COALESCE(upload_date, '') AS d FROM videos WHERE 1 = 1",
                           (), list(video_ids))
    rows = sorted(rows, key=lambda row: (row["d"], row["id"]), reverse=True)[:limit]
    return [PreviewVideo(id=row["id"], title=row["title"], channel_name=row["channel_name"]) for row in rows]


async def preview(category_id: Optional[int], rules: list[RuleIn]) -> RulePreview:
    """Was die Regeln ergäben, ohne etwas zu ändern."""
    resolved = await _resolve(category_id, await normalize(rules))
    matched, hits = await _evaluate(resolved.rules)
    members, rule_members, excluded = await _members(category_id)
    matching = set(matched) - excluded
    new = matching - members
    idle = await _idle_rule_ids(resolved.rules)
    leaving = {vid for vid, rid in rule_members.items() if vid not in matching and rid not in idle}
    return RulePreview(matching=len(matching), new=len(new), leaving=len(leaving),
                       per_rule=[len(found - excluded) for found in hits],
                       samples=await _newest(new or matching, _SAMPLES),
                       semantic_missing=resolved.missing or resolved.idle)


async def matches(rules: list[RuleIn]) -> Optional[set[str]]:
    """Fertige Videos, auf die Regeln einer neuen Kategorie passen würden;
    None, wenn eine "Inhaltlich wie"-Regel gerade nicht zu rechnen ist."""
    resolved = await _resolve(None, await normalize(rules))
    if resolved.missing:
        return None
    matched, _ = await _evaluate(resolved.rules)
    return set(matched)


async def _store(category_id: int, resolved: list[_Rule]) -> None:
    keep = {rule.rule_id for rule in resolved if rule.rule_id}
    connection = db.conn
    for row in await db.fetch_all("SELECT id FROM category_rules WHERE category_id = ?", (category_id,)):
        if row["id"] not in keep:
            await connection.execute("DELETE FROM category_rule_vectors WHERE rule_id = ?", (row["id"],))
            await connection.execute("DELETE FROM category_rules WHERE id = ?", (row["id"],))
    for position, rule in enumerate(resolved):
        if rule.rule_id:
            await connection.execute("UPDATE category_rules SET position = ? WHERE id = ?", (position, rule.rule_id))
        else:
            cursor = await connection.execute(
                "INSERT INTO category_rules (category_id, kind, value, precision, position) VALUES (?, ?, ?, ?, ?)",
                (category_id, rule.kind, rule.value, rule.precision, position))
            rule.rule_id = cursor.lastrowid
        if rule.kind == "semantic" and rule.vector is not None:
            import numpy as np
            await connection.execute(
                """INSERT OR REPLACE INTO category_rule_vectors (rule_id, model, vector, threshold, updated_at)
                   VALUES (?, ?, ?, ?, datetime('now'))""",
                (rule.rule_id, rule.model, np.asarray(rule.vector, dtype=np.float32).tobytes(), float(rule.threshold)))
    await connection.commit()


async def prepare(category_id: Optional[int], rules: list[RuleIn]) -> list[_Rule]:
    """Regeln prüfen und rechnen, ohne zu schreiben. RulesUnavailable, wenn
    eine neue "Inhaltlich wie"-Regel gerade nicht zu rechnen ist."""
    resolved = await _resolve(category_id, await normalize(rules))
    if resolved.missing:
        raise RulesUnavailable("Der KI-Dienst ist gerade nicht erreichbar - \"Inhaltlich wie\" lässt sich nicht rechnen")
    return resolved.rules


async def commit(category_id: int, resolved: list[_Rule]) -> ApplyResult:
    """Vorbereitete Regeln speichern und die Kategorie neu füllen."""
    async with _lock:
        await _store(category_id, resolved)
        return await _apply_category(category_id)


async def save_rules(category_id: int, rules: list[RuleIn]) -> ApplyResult:
    return await commit(category_id, await prepare(category_id, rules))


# ─── Von Hand ─────────────────────────────────────────────────────────

async def add_by_hand(category_id: int, video_ids: list[str]) -> int:
    """Videos von Hand hineinlegen (hebt ein früheres Herausnehmen auf).
    Gibt die Zahl der neu hinzugekommenen zurück."""
    ids = list(await _only_ready(list(dict.fromkeys(video_ids))))
    if not ids:
        return 0
    async with _lock:
        connection = db.conn
        for chunk in _chunks(ids):
            await connection.execute(
                f"DELETE FROM category_exclusions WHERE category_id = ? AND video_id IN ({_marks(chunk)})",
                (category_id, *chunk))
            await connection.execute(
                f"""UPDATE video_categories SET origin = 'hand', rule_id = NULL
                    WHERE category_id = ? AND origin = 'rule' AND video_id IN ({_marks(chunk)})""", (category_id, *chunk))
        present = {row["video_id"] for row in await _rows_for(
            "SELECT video_id FROM video_categories WHERE category_id = ?", (category_id,), ids, column="video_id")}
        new = [vid for vid in ids if vid not in present]
        if new:
            positions = await _top_positions(category_id, new)
            await connection.executemany(
                """INSERT OR IGNORE INTO video_categories (video_id, category_id, origin, position, added_at)
                   VALUES (?, ?, 'hand', ?, datetime('now'))""",
                [(vid, category_id, positions[vid]) for vid in new])
        await connection.commit()
        return len(new)


async def remove_by_hand(category_id: int, video_ids: list[str]) -> list[Membership]:
    """Videos herausnehmen; keine Regel bringt sie zurück. Gibt die
    entfernten Zeilen zurück (für Rückgängig)."""
    ids = list(dict.fromkeys(video_ids))
    async with _lock:
        rows = await _rows_for(
            "SELECT video_id, origin, rule_id, position, added_at FROM video_categories WHERE category_id = ?",
            (category_id,), ids, column="video_id")
        connection = db.conn
        await connection.executemany(
            "DELETE FROM video_categories WHERE category_id = ? AND video_id = ?",
            [(category_id, row["video_id"]) for row in rows])
        await connection.executemany(
            "INSERT OR IGNORE INTO category_exclusions (category_id, video_id) VALUES (?, ?)",
            [(category_id, row["video_id"]) for row in rows])
        await connection.commit()
    return [Membership(**dict(row)) for row in rows]


async def restore(category_id: int, entries: list[Membership]) -> int:
    """Herausnehmen rückgängig machen: Zeilen wie vorher, Ausschluss weg.
    Per Regel Hineingekommene prüft die Regel dabei neu."""
    ids = [entry.video_id for entry in entries]
    ready = await _only_ready(ids)
    async with _lock:
        connection = db.conn
        for chunk in _chunks(ids):
            await connection.execute(
                f"DELETE FROM category_exclusions WHERE category_id = ? AND video_id IN ({_marks(chunk)})",
                (category_id, *chunk))
        await connection.executemany(
            """INSERT OR IGNORE INTO video_categories (video_id, category_id, origin, rule_id, position, added_at)
               VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')))""",
            [(e.video_id, category_id, e.origin, e.rule_id if e.origin == "rule" else None, e.position, e.added_at)
             for e in entries if e.video_id in ready])
        await connection.commit()
        by_rule = [e.video_id for e in entries if e.origin == "rule" and e.video_id in ready]
        if by_rule:
            rules = await _saved_rules(category_id)
            matched, _ = await _evaluate(rules, by_rule)
            await _sync(category_id, {vid: rules[i].rule_id for vid, i in matched.items()}, by_rule,
                        frozenset(await _idle_rule_ids(rules)))
    return len(ready)


async def set_video_categories(video_id: str, category_ids: list[int]) -> None:
    """Die Kategorien eines Videos von Hand festlegen (Bearbeiten in der
    Wiedergabe): Abgewählte gelten als herausgenommen, Neue als von Hand."""
    current = {row["category_id"] for row in await db.fetch_all(
        "SELECT category_id FROM video_categories WHERE video_id = ?", (video_id,))}
    known = {row["id"] for row in await db.fetch_all("SELECT id FROM categories")}
    wanted = {int(cid) for cid in category_ids if int(cid) in known}
    for category_id in current - wanted:
        await remove_by_hand(category_id, [video_id])
    for category_id in wanted - current:
        await add_by_hand(category_id, [video_id])


async def reorder(category_id: int, video_ids: list[str]) -> None:
    """Eigene Reihenfolge festlegen (in der gegebenen Folge von oben)."""
    async with _lock:
        await db.conn.executemany(
            "UPDATE video_categories SET position = ? WHERE category_id = ? AND video_id = ?",
            [(index, category_id, vid) for index, vid in enumerate(dict.fromkeys(video_ids))])
        await db.conn.commit()


# ─── Hintergrund: neue Videos einordnen ───────────────────────────────

async def pending() -> int:
    return await db.fetch_val("SELECT COUNT(*) FROM category_dirty") or 0


async def process_dirty(limit: int = _WORKER_BATCH) -> int:
    """Einen Stapel vorgemerkter Videos einordnen. Gibt die Zahl zurück."""
    ids = [row["video_id"] for row in await db.fetch_all("SELECT video_id FROM category_dirty LIMIT ?", (limit,))]
    if not ids:
        return 0
    # erst austragen: wird ein Video währenddessen erneut vorgemerkt, bleibt die neue Marke
    for chunk in _chunks(ids):
        await db.conn.execute(f"DELETE FROM category_dirty WHERE video_id IN ({_marks(chunk)})", chunk)
    await db.conn.commit()
    try:
        if await db.fetch_val("SELECT 1 FROM category_rules LIMIT 1"):
            await apply_videos(ids)
    except Exception:
        await db.conn.executemany("INSERT OR IGNORE INTO category_dirty (video_id) VALUES (?)", [(i,) for i in ids])
        await db.conn.commit()
        raise
    return len(ids)


async def refresh_vectors() -> int:
    """Regeln "Inhaltlich wie" ohne Vektor des aktuellen Modells nachrechnen
    (nach dem Wiederherstellen der Nutzerdaten - Vektoren werden nicht
    gesichert - oder nach einem Modellwechsel) und ihre Kategorien neu füllen.
    Gibt die Zahl der nachgerechneten Regeln zurück."""
    cfg = await semantic_index.config()
    if not cfg:
        return 0
    rows = await db.fetch_all(
        """SELECT r.id, r.category_id, r.value, r.precision FROM category_rules r
           LEFT JOIN category_rule_vectors v ON v.rule_id = r.id
           WHERE r.kind = 'semantic' AND (v.rule_id IS NULL OR v.model != ?)""", (cfg[1],))
    if not rows or not await semantic_index.available():
        return 0
    library = await semantic_index.all_vectors()
    if library is None:
        return 0
    import numpy as np
    done, categories = 0, set()
    for row in rows:
        vector = await semantic_index.text_vector(row["value"])
        if vector is None or vector.shape[0] != library[1].shape[1]:
            break
        level = semantic_index.PRECISIONS.get(row["precision"]) or semantic_index.PRECISIONS[await default_precision()]
        await db.conn.execute(
            """INSERT OR REPLACE INTO category_rule_vectors (rule_id, model, vector, threshold, updated_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            (row["id"], cfg[1], np.asarray(vector, dtype=np.float32).tobytes(),
             semantic_index.rule_floor(library[1] @ vector, level, len(library[0]))))
        await db.conn.commit()
        done += 1
        categories.add(row["category_id"])
    for category_id in categories:
        await apply_category(category_id)
    return done


async def worker() -> None:
    """Hintergrundlauf: vorgemerkte Videos nach den Regeln einordnen."""
    await asyncio.sleep(30)
    while True:
        try:
            await refresh_vectors()
            while await process_dirty():
                await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"[KATEGORIEN] Einordnen unterbrochen: {e.__class__.__name__}: {e}")
        await asyncio.sleep(_WORKER_PAUSE_S)
