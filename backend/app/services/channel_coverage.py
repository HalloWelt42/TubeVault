"""
TubeVault – Wie vollständig ein Kanal geladen ist (Medaillen der Kanalübersicht)

Gezählt werden nur die normalen Videos eines Kanals, Live und Shorts nie
(Nutzerentscheidung 15.10.2026). Ausgenommen ist nur, was sich dauerhaft
nicht laden lässt (nur für Mitglieder, privat, entfernt, Urheberrecht,
Altersfreigabe) oder was der Nutzer selbst gelöscht bzw. ausgeschlossen hat.
Was die Quelle nur vorübergehend verweigert hat (gedrosselt, "später noch
einmal"), zählt weiter mit. Davon zählt, was in Bibliothek oder Archiv liegt.

  Gold    lückenlos
  Silber  es fehlen nur wenige Prozent (ab 95 %)
  Bronze  fast voll, aber mit mehr Lücken als Silber (ab 80 %)

Bewertet wird nur ein vollständig gescannter Kanal - vorher kennt TubeVault
nur die neuesten Feed-Einträge, und eine Medaille wäre geraten.
"""
from typing import Optional

from pydantic import BaseModel

from app.database import db

GOLD = "gold"
SILVER = "silver"
BRONZE = "bronze"
NEVER_SCANNED = "never-scanned"

SILVER_SHARE = 0.95
BRONZE_SHARE = 0.80
MIN_WANTED = 3            # darunter ist eine Bewertung nicht aussagekräftig

# Gründe der Sperrliste, die dauerhaft gelten (Rest: vorübergehend, zählt mit)
_PERMANENT_PREFIXES = ("manuell gelöscht", "Manuell ausgeschlossen", "members-only", "Members-Only",
                       "private", "removed", "copyright", "age-gate")


def permanently_unloadable_sql(column: str) -> str:
    """SQL-Bedingung: das Video mit dieser Kennung lässt sich dauerhaft nicht laden."""
    prefixes = " OR ".join(f"pi.reason LIKE '{p}%'" for p in _PERMANENT_PREFIXES)
    return (f"EXISTS (SELECT 1 FROM ignored_videos pi WHERE pi.video_id = {column} AND ({prefixes}"
            f" OR (pi.reason LIKE 'unavailable%' AND pi.reason NOT LIKE '%try again later%'"
            f" AND pi.reason NOT LIKE '%format is not available%')))")


def wanted_sql(alias: str = "r") -> str:
    """SQL-Bedingung (ohne führendes AND) für die zählenden Feed-Einträge:
    normale Videos, die sich laden lassen."""
    return (f"COALESCE({alias}.video_type, 'video') = 'video' "
            f"AND NOT {permanently_unloadable_sql(f'{alias}.video_id')}")


def have_sql(alias: str = "r") -> str:
    """SQL-Ausdruck: der Eintrag liegt fertig geladen in Bibliothek oder Archiv."""
    return f"EXISTS (SELECT 1 FROM videos hv WHERE hv.id = {alias}.video_id AND hv.status = 'ready')"


def medal(wanted: int, have: int, scanned: bool = True) -> Optional[str]:
    """gold: lückenlos, silver: ab 95 %, bronze: ab 80 %; ungescannt: never-scanned."""
    if not scanned:
        return NEVER_SCANNED
    if wanted < MIN_WANTED:
        return None
    if have >= wanted:
        return GOLD
    share = have / wanted
    if share >= SILVER_SHARE:
        return SILVER
    if share >= BRONZE_SHARE:
        return BRONZE
    return None


class Coverage(BaseModel):
    """Abdeckung eines Kanals, wie sie Kanalübersicht und Kanalseite zeigen."""
    wanted_count: int
    have_count: int
    medal: Optional[str]


async def of_channel(channel_id: str, scanned: bool) -> Coverage:
    """Abdeckung und Medaille eines einzelnen Kanals (die Liste rechnet alle
    Kanäle in einem Durchgang mit denselben Bedingungen)."""
    row = await db.fetch_one(
        f"""SELECT COUNT(*) AS wanted, COALESCE(SUM({have_sql("r")}), 0) AS have
            FROM rss_entries r WHERE r.channel_id = ? AND {wanted_sql("r")}""", (channel_id,))
    wanted, have = row["wanted"], row["have"]
    return Coverage(wanted_count=wanted, have_count=have, medal=medal(wanted, have, scanned))
