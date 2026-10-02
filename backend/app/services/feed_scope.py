"""
TubeVault – Was im Feed als neu gilt

Die EINE Definition für "neu im Feed": der Eintrag ist weder gemerkt,
ausgeblendet noch archiviert UND das Video ist noch nicht geladen. Ein
geladenes Video ist erledigt - es steht in Bibliothek oder Archiv und zählt
im Feed nicht mehr mit. Feed-Liste, Filter, Zähler der Seitenleiste und
"neue Videos" je Kanal benutzen alle diese Bedingung.
"""


def new_entry(alias: str = "r") -> str:
    """SQL-Bedingung (ohne führendes AND) für einen neuen Feed-Eintrag."""
    return (f"COALESCE({alias}.feed_status, 'active') = 'active' "
            f"AND NOT EXISTS (SELECT 1 FROM videos fv WHERE fv.id = {alias}.video_id AND fv.status = 'ready')")
