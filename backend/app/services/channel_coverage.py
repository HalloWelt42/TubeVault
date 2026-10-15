"""
TubeVault – Wie vollständig ein Kanal geladen ist (Medaillen der Kanalübersicht)

Gemessen wird an den Feed-Einträgen, die der Nutzer haben will: ohne
ausgeblendete Einträge, ohne dauerhaft nicht ladbare (ignored_videos, z.B.
nur für Mitglieder oder gelöscht) und ohne Shorts, wenn sie ausgeschlossen
sind. Davon zählt, was in Bibliothek oder Archiv liegt.

Früher (bis 15.10.2026) wurden alle geladenen Videos des Kanals gegen alle
Feed-Einträge gerechnet: Videos außerhalb des Feeds glichen fehlende aus, ein
Kanal konnte Gold tragen, obwohl die Hälfte fehlte; "war mal komplett" gab
dauerhaft Bronze. Nutzerwunsch: sinnvolle Metrik.
"""
from typing import Optional

GOLD = "gold"
SILVER = "silver"
BRONZE = "bronze"

SILVER_SHARE = 0.90
BRONZE_SHARE = 0.75
MIN_WANTED = 3            # darunter ist eine Bewertung nicht aussagekräftig


def wanted_sql(alias: str = "r") -> str:
    """SQL-Bedingung (ohne führendes AND) für gewünschte Feed-Einträge.
    Shorts schließt der Aufrufer mit video_classifier.without_shorts aus."""
    return (f"COALESCE({alias}.feed_status, 'active') <> 'dismissed' "
            f"AND {alias}.video_id NOT IN (SELECT video_id FROM ignored_videos)")


def have_sql(alias: str = "r") -> str:
    """SQL-Ausdruck: der Eintrag liegt fertig geladen in Bibliothek oder Archiv."""
    return f"EXISTS (SELECT 1 FROM videos hv WHERE hv.id = {alias}.video_id AND hv.status = 'ready')"


def medal(wanted: int, have: int) -> Optional[str]:
    """gold: alles Gewünschte geladen, silver: ab 90 %, bronze: ab 75 %."""
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
