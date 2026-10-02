"""
TubeVault – Kanal-Zuordnung v1.0.0

Die EINE Regel für Kanalname und Kanal-ID an Videos:

    Ist der Kanal eines Videos bekannt, steht sein Name am Video.

Hintergrund: videos.channel_name wird von einem Dutzend Schreibwegen gesetzt
(Download, Import, Playlist-Stub, Scan, Wiederaufbau ...). Liefert die Quelle
einmal keinen Namen, blieb das Feld leer - obwohl das Abo den Namen kennt.
Statt jeden Schreibweg einzeln abzusichern, erzwingt die Datenbank die Regel
per Trigger. Damit gilt sie auch für Schreibwege, die später dazukommen.

Regeln im Einzelnen
-------------------
1. Video ohne Kanal-ID, aber mit eindeutigem Feed-Eintrag → Kanal-ID aus dem Feed.
2. Video mit Kanal-ID, aber ohne Namen → Name aus dem Abo, sonst vom jüngsten
   anderen Video desselben Kanals.
3. Ein bekannter Name wird nie durch einen leeren ersetzt.
4. Ändert sich der Name im Abo (Kanal umbenannt), ziehen die Videos nach, die
   den alten Namen oder keinen tragen. Von Hand gesetzte Namen bleiben.

"Gültiger Name" heisst: nicht leer und nicht bloss die Kanal-ID.
"""
import logging

logger = logging.getLogger(__name__)

_NAME_FROM_SUBSCRIPTION = """
    SELECT s.channel_name FROM subscriptions s
    WHERE s.channel_id = {cid}
      AND TRIM(COALESCE(s.channel_name, '')) <> ''
      AND s.channel_name <> s.channel_id
"""
_NAME_FROM_SIBLING = """
    SELECT v2.channel_name FROM videos v2
    WHERE v2.channel_id = {cid} AND v2.id <> {vid}
      AND TRIM(COALESCE(v2.channel_name, '')) <> ''
    ORDER BY v2.created_at DESC LIMIT 1
"""


def _known_name(cid: str, vid: str) -> str:
    """SQL-Ausdruck: bester bekannter Name zu einer Kanal-ID (oder NULL)."""
    return (f"COALESCE(({_NAME_FROM_SUBSCRIPTION.format(cid=cid)}), "
            f"({_NAME_FROM_SIBLING.format(cid=cid, vid=vid)}))")


_FILL_ID = """
    UPDATE videos
       SET channel_id = (SELECT MIN(r.channel_id) FROM rss_entries r WHERE r.video_id = {vid})
     WHERE id = {vid}
       AND COALESCE(channel_id, '') = ''
       AND (SELECT COUNT(DISTINCT r.channel_id) FROM rss_entries r WHERE r.video_id = {vid}) = 1;
"""
_FILL_NAME = """
    UPDATE videos
       SET channel_name = {known}
     WHERE id = {vid}
       AND TRIM(COALESCE(channel_name, '')) = ''
       AND COALESCE(channel_id, '') <> ''
       AND {known} IS NOT NULL;
"""

TRIGGERS_SQL = f"""
CREATE TRIGGER IF NOT EXISTS trg_video_channel_insert AFTER INSERT ON videos
WHEN COALESCE(new.channel_id, '') = '' OR TRIM(COALESCE(new.channel_name, '')) = ''
BEGIN
    {_FILL_ID.format(vid='new.id')}
    {_FILL_NAME.format(vid='new.id', known=_known_name('videos.channel_id', 'new.id'))}
END;

CREATE TRIGGER IF NOT EXISTS trg_video_channel_update
AFTER UPDATE OF channel_id, channel_name ON videos
WHEN COALESCE(new.channel_id, '') = '' OR TRIM(COALESCE(new.channel_name, '')) = ''
BEGIN
    -- Regel 3: bekannter Name geht nicht verloren
    UPDATE videos SET channel_name = old.channel_name
     WHERE id = new.id
       AND TRIM(COALESCE(new.channel_name, '')) = ''
       AND TRIM(COALESCE(old.channel_name, '')) <> ''
       AND COALESCE(new.channel_id, '') = COALESCE(old.channel_id, '');
    UPDATE videos SET channel_id = old.channel_id
     WHERE id = new.id
       AND COALESCE(new.channel_id, '') = ''
       AND COALESCE(old.channel_id, '') <> '';
    {_FILL_ID.format(vid='new.id')}
    {_FILL_NAME.format(vid='new.id', known=_known_name('videos.channel_id', 'new.id'))}
END;

CREATE TRIGGER IF NOT EXISTS trg_subscription_name_insert AFTER INSERT ON subscriptions
WHEN TRIM(COALESCE(new.channel_name, '')) <> '' AND new.channel_name <> new.channel_id
BEGIN
    UPDATE videos SET channel_name = new.channel_name
     WHERE channel_id = new.channel_id AND TRIM(COALESCE(channel_name, '')) = '';
END;

CREATE TRIGGER IF NOT EXISTS trg_subscription_name_update
AFTER UPDATE OF channel_name ON subscriptions
WHEN TRIM(COALESCE(new.channel_name, '')) <> '' AND new.channel_name <> new.channel_id
     AND COALESCE(old.channel_name, '') <> new.channel_name
BEGIN
    UPDATE videos SET channel_name = new.channel_name
     WHERE channel_id = new.channel_id
       AND (TRIM(COALESCE(channel_name, '')) = '' OR channel_name = old.channel_name);
END;
"""

# Bestand reparieren: füllt ausschliesslich Leeres, überschreibt nichts.
REPAIR_SQL = [
    """UPDATE videos
          SET channel_id = (SELECT MIN(r.channel_id) FROM rss_entries r WHERE r.video_id = videos.id)
        WHERE COALESCE(channel_id, '') = ''
          AND (SELECT COUNT(DISTINCT r.channel_id) FROM rss_entries r WHERE r.video_id = videos.id) = 1""",
    f"""UPDATE videos
           SET channel_name = ({_NAME_FROM_SUBSCRIPTION.format(cid='videos.channel_id')})
         WHERE TRIM(COALESCE(channel_name, '')) = ''
           AND COALESCE(channel_id, '') <> ''
           AND ({_NAME_FROM_SUBSCRIPTION.format(cid='videos.channel_id')}) IS NOT NULL""",
    f"""UPDATE videos
           SET channel_name = ({_NAME_FROM_SIBLING.format(cid='videos.channel_id', vid='videos.id')})
         WHERE TRIM(COALESCE(channel_name, '')) = ''
           AND COALESCE(channel_id, '') <> ''
           AND ({_NAME_FROM_SIBLING.format(cid='videos.channel_id', vid='videos.id')}) IS NOT NULL""",
]


async def install(connection, *, repair: bool) -> int:
    """Trigger anlegen; repair=True füllt zusätzlich den Bestand. Gibt die Zahl
    der reparierten Zeilen zurück."""
    await connection.executescript(TRIGGERS_SQL)
    repaired = 0
    if repair:
        for statement in REPAIR_SQL:
            cursor = await connection.execute(statement)
            repaired += cursor.rowcount
    return repaired
