"""
TubeVault - Kategorien: Verwaltung und Übersicht

Anlegen, Ändern, Löschen und die Übersicht der Seite Kategorien (Kennzahlen,
Kacheln, Kanäle mit den meisten Videos ohne Kategorie). Welche Videos in
einer Kategorie sind, entscheidet allein category_rules.
"""
from typing import Optional

from app.database import db
from app.models.categories import (
    CATEGORY_COLORS, AiState, CategoryBrief, CategoryCard, CategoryCreate, CategoryOverview, CategoryUpdate,
    ChannelChoice, ChannelCount, PrecisionChoice, Rule,
)
from app.services import category_rules, semantic_index, watch_state

UNSORTED_CHANNELS = 6
CHANNEL_CHOICES = 12
COVERS = 3


class CategoryExists(Exception):
    """Eine Kategorie mit diesem Namen gibt es schon."""


# ─── Lesen ────────────────────────────────────────────────────────────

async def briefs() -> list[CategoryBrief]:
    """Alle Kategorien kurz (Auswahl in Wiedergabe und Filtern), nach Name."""
    rows = await db.fetch_all(
        """SELECT c.id, c.name, c.description, c.color,
                  (SELECT COUNT(*) FROM video_categories vc JOIN videos v ON v.id = vc.video_id
                   WHERE vc.category_id = c.id AND v.status = 'ready') AS video_count
           FROM categories c ORDER BY c.name COLLATE NOCASE""")
    return [CategoryBrief(**dict(row)) for row in rows]


async def rules_of(category_ids: Optional[list[int]] = None) -> dict[int, list[Rule]]:
    """Regeln je Kategorie samt Anzeigenamen, in ihrer Reihenfolge."""
    rows = await db.fetch_all(
        "SELECT id, category_id, kind, value, precision FROM category_rules ORDER BY category_id, position, id")
    rows = [row for row in rows if category_ids is None or row["category_id"] in category_ids]
    names = await category_rules.channel_names(row["value"] for row in rows if row["kind"] == "channel")
    result: dict[int, list[Rule]] = {}
    for row in rows:
        result.setdefault(row["category_id"], []).append(Rule(
            id=row["id"], kind=row["kind"], value=row["value"], precision=row["precision"],
            label=category_rules.rule_label(row["kind"], row["value"], names)))
    return result


async def cards() -> list[CategoryCard]:
    rows = await db.fetch_all(
        f"""SELECT c.id, c.name, c.description, c.color, c.created_at,
                   COUNT(v.id) AS video_count, COALESCE(SUM(v.duration), 0) AS duration,
                   COALESCE(SUM(CASE WHEN v.id IS NOT NULL AND {watch_state.state_sql('v')} = 'finished'
                                THEN 1 ELSE 0 END), 0) AS finished_count,
                   MAX(CASE WHEN v.id IS NOT NULL THEN vc.added_at END) AS last_filled_at
            FROM categories c
            LEFT JOIN video_categories vc ON vc.category_id = c.id
            LEFT JOIN videos v ON v.id = vc.video_id AND v.status = 'ready'
            GROUP BY c.id""")
    covers: dict[int, list[str]] = {}
    for row in await db.fetch_all(
            f"""SELECT category_id, video_id FROM (
                    SELECT vc.category_id, vc.video_id,
                           ROW_NUMBER() OVER (PARTITION BY vc.category_id ORDER BY vc.position, vc.rowid) AS n
                    FROM video_categories vc JOIN videos v ON v.id = vc.video_id AND v.status = 'ready')
                WHERE n <= {COVERS} ORDER BY category_id, n"""):
        covers.setdefault(row["category_id"], []).append(row["video_id"])
    rules = await rules_of()
    return [CategoryCard(**{**dict(row), "color": row["color"] or CATEGORY_COLORS[0]},
                         cover_ids=covers.get(row["id"], []), rules=rules.get(row["id"], []))
            for row in rows]


async def unsorted_channels(limit: int = UNSORTED_CHANNELS) -> list[ChannelCount]:
    """Kanäle mit den meisten fertigen Videos ohne Kategorie."""
    rows = await db.fetch_all(
        """SELECT v.channel_id, MAX(v.channel_name) AS name, COUNT(*) AS count FROM videos v
           WHERE v.status = 'ready' AND v.channel_id IS NOT NULL AND v.channel_id != ''
             AND NOT EXISTS (SELECT 1 FROM video_categories vc WHERE vc.video_id = v.id)
           GROUP BY v.channel_id ORDER BY count DESC, name LIMIT ?""", (limit,))
    names = await category_rules.channel_names(row["channel_id"] for row in rows)
    return [ChannelCount(channel_id=row["channel_id"], name=names.get(row["channel_id"]) or row["name"] or row["channel_id"],
                         count=row["count"]) for row in rows]


async def ai_state() -> AiState:
    from app.services import ai_chat
    semantic = bool(await semantic_index.config()) and await semantic_index.available()
    return AiState(semantic=semantic, topics=semantic and bool(await ai_chat.pick_model()),
                   precisions=[PrecisionChoice(key=key, label=level.label)
                               for key, level in semantic_index.PRECISIONS.items()],
                   default_precision=await category_rules.default_precision())


async def overview() -> CategoryOverview:
    total = await db.fetch_val("SELECT COUNT(*) FROM videos WHERE status = 'ready'") or 0
    assigned = await db.fetch_val(
        """SELECT COUNT(DISTINCT vc.video_id) FROM video_categories vc
           JOIN videos v ON v.id = vc.video_id AND v.status = 'ready'""") or 0
    return CategoryOverview(categories=await cards(), total=total, assigned=assigned, unassigned=total - assigned,
                            unsorted_channels=await unsorted_channels(), colors=CATEGORY_COLORS,
                            ai=await ai_state())


async def channel_choices(query: str = "", limit: int = CHANNEL_CHOICES) -> list[ChannelChoice]:
    """Kanäle für die Regel "Kanal ist": Name enthält die Eingabe, die mit
    den meisten fertigen Videos zuerst."""
    rows = await db.fetch_all(
        """SELECT channel_id, MAX(channel_name) AS name, COUNT(*) AS count FROM videos
           WHERE status = 'ready' AND channel_id IS NOT NULL AND channel_id != ''
           GROUP BY channel_id ORDER BY count DESC""")
    names = await category_rules.channel_names(row["channel_id"] for row in rows)
    folded = query.strip().casefold()
    result = []
    for row in rows:
        name = names.get(row["channel_id"]) or row["name"] or row["channel_id"]
        if not folded or folded in name.casefold():
            result.append(ChannelChoice(channel_id=row["channel_id"], name=name, count=row["count"]))
            if len(result) >= limit:
                break
    return result


# ─── Ändern ───────────────────────────────────────────────────────────

async def _check_name(name: str, own_id: Optional[int] = None) -> None:
    folded = name.casefold()
    for row in await db.fetch_all("SELECT id, name FROM categories"):
        if row["id"] != own_id and (row["name"] or "").casefold() == folded:
            raise CategoryExists(f"Die Kategorie \"{row['name']}\" gibt es schon")


async def next_color() -> str:
    """Die erste noch nicht vergebene Farbe, sonst reihum."""
    used = [row["color"] for row in await db.fetch_all("SELECT color FROM categories")]
    for color in CATEGORY_COLORS:
        if color not in used:
            return color
    return CATEGORY_COLORS[len(used) % len(CATEGORY_COLORS)]


async def create(data: CategoryCreate) -> int:
    """Kategorie anlegen, mit Regeln gleich gefüllt. Regeln werden vorher
    geprüft - scheitern sie, entsteht nichts."""
    await _check_name(data.name)
    prepared = await category_rules.prepare(None, data.rules) if data.rules else []
    color = data.color if data.color in CATEGORY_COLORS else await next_color()
    cursor = await db.execute("INSERT INTO categories (name, description, color) VALUES (?, ?, ?)",
                              (data.name, data.description or None, color))
    category_id = cursor.lastrowid
    if prepared:
        await category_rules.commit(category_id, prepared)
    return category_id


async def exists(category_id: int) -> bool:
    return bool(await db.fetch_val("SELECT 1 FROM categories WHERE id = ?", (category_id,)))


async def update(category_id: int, data: CategoryUpdate) -> None:
    fields = data.model_dump(exclude_unset=True)
    if "name" in fields:
        if not fields["name"]:
            raise ValueError("Der Name darf nicht leer sein")
        await _check_name(fields["name"], category_id)
    if "color" in fields and fields["color"] not in CATEGORY_COLORS:
        raise ValueError("Diese Farbe steht nicht zur Auswahl")
    if "description" in fields:
        fields["description"] = fields["description"] or None
    if fields:
        assignments = ", ".join(f"{key} = ?" for key in fields)
        await db.execute(f"UPDATE categories SET {assignments} WHERE id = ?", (*fields.values(), category_id))


async def delete(category_id: int) -> None:
    """Kategorie samt Regeln und Zuordnungen löschen; die Videos bleiben."""
    for table in ("category_exclusions", "video_categories"):
        await db.conn.execute(f"DELETE FROM {table} WHERE category_id = ?", (category_id,))
    await db.conn.execute(
        "DELETE FROM category_rule_vectors WHERE rule_id IN (SELECT id FROM category_rules WHERE category_id = ?)",
        (category_id,))
    await db.conn.execute("DELETE FROM category_rules WHERE category_id = ?", (category_id,))
    await db.conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    await db.conn.commit()


async def video_categories(video_id: str) -> list[CategoryBrief]:
    rows = await db.fetch_all(
        """SELECT c.id, c.name, c.description, c.color, 0 AS video_count FROM categories c
           JOIN video_categories vc ON vc.category_id = c.id WHERE vc.video_id = ? ORDER BY c.name COLLATE NOCASE""",
        (video_id,))
    return [CategoryBrief(**dict(row)) for row in rows]
