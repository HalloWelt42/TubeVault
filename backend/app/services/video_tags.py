"""
TubeVault – Schlagwörter der Videos (eigener Index)

Der Schlagwort-Index (tag_index) für videos.tags: je Video und Schlagwort eine
Zeile in video_tags mit Suchschlüssel tag_suche (entschieden 19.10.2026).
Warum, nach welcher Regel und wie er sich aktuell hält, steht in tag_index.

Pflege: Trigger auf videos merken jedes neue Video mit Schlagwörtern und jede
Änderung an videos.tags vor (Download, Metadaten, Bearbeiten, Import,
Wiederaufbau, Bereinigung); ein gelöschtes Video nimmt seine Zeilen mit
(Fremdschlüssel, dazu metadata_service._VIDEO_ROWS). Den Bestand nach der
Einführung (Migration v59) nimmt background_catch_up in Portionen auf; die
Statusleiste zeigt den Fortschritt (background_work).

Nutzer: Listenfilter der Bibliothek und des Archivs (condition), Zählung der
Schlagwortleiste (counts, dieselben Filter wie die Liste), Kategorie-Regeln
"Schlagwort enthält" (contains_condition, ruhend solange ensure nicht
aktuell meldet). Der Volltext der Suche liest die Schlagwörter weiter aus
dem JSON (search_index entschlüsselt es dabei).
"""
from app.services.tag_index import TagIndex, keyed, parse, search_key  # noqa: F401  (Regel für Aufrufer)

INDEX = TagIndex(table="video_tags", id_column="video_id", id_type="TEXT", owner="videos", column="tags")

install_schema = INDEX.install_schema
index_videos = INDEX.index
pending = INDEX.pending
flush = INDEX.flush
refresh_before_query = INDEX.refresh_before_query
ensure = INDEX.ensure
background_catch_up = INDEX.background_catch_up
contains_condition = INDEX.contains_condition


def condition(tags: list[str], alias: str = "v") -> tuple[str, list]:
    """Listenfilter: Videos mit einem dieser Schlagwörter (genau, Schreibweise egal)."""
    return INDEX.condition(tags, alias)


async def counts(where: str, params: list) -> list[dict]:
    """Schlagwörter der Videos v, die where erfüllen, mit Anzahl ({tag, key,
    count}): so viele, wie der Listenfilter mit diesem Schlagwort findet."""
    return await INDEX.counts("videos v", "v", where, params)
