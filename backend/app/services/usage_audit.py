"""
TubeVault – Usage-Audit v1.0.0

Statischer Code-Scan der zeigt, welche Stellen im Backend noch DIREKT
auf videos.description (oder andere auszulagernde Felder) lesend zugreifen.

Das ist der "bin ich bereit die DB-Spalte zu leeren?"-Check.
So lange hier noch Zugriffe gelistet sind, sollte die Spalte nicht geleert werden.

Läuft beim Import des Modul NICHT automatisch – nur on-demand via Admin-Endpoint.
Verwendet grep-ähnliche Regex-Suche über das app/-Verzeichnis.
"""
import re
from dataclasses import dataclass
from pathlib import Path


# Regex-Patterns für DB-Lesezugriffe auf videos.description
_PATTERNS = {
    "description": [
        # SELECT … description … FROM videos
        re.compile(r"SELECT[^;]*\bdescription\b[^;]*FROM videos", re.IGNORECASE | re.DOTALL),
        # row["description"]
        re.compile(r"""row\[["']description["']\]"""),
        # v.description als Zugriff
        re.compile(r"""\bv\.description\b"""),
        # description-Referenz in dicts
        re.compile(r""""description"\s*:\s*(?:row|v|video|data|r)\.get"""),
    ],
}


@dataclass
class AuditHit:
    file: str
    line: int
    code: str
    pattern: str


def scan_for_field(field: str, root: Path | None = None) -> list[AuditHit]:
    """Scannt app/ nach Zugriffen auf videos.<field>.
    Ergebnisse sind Hit-Liste mit Datei, Zeile, Code-Snippet.
    Test-Dateien werden ausgenommen."""
    if root is None:
        root = Path(__file__).resolve().parent.parent  # backend/app
    patterns = _PATTERNS.get(field, [])
    if not patterns:
        return []

    hits: list[AuditHit] = []
    for py in root.rglob("*.py"):
        # Tests ausklammern
        if "tests" in py.parts or "__pycache__" in py.parts:
            continue
        # Export-Module selbst ausklammern (nutzen das Feld legitim)
        if py.name in ("text_export.py", "text_backup.py", "usage_audit.py"):
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in patterns:
            for m in pat.finditer(text):
                # Zeilennummer finden
                line_no = text.count("\n", 0, m.start()) + 1
                # Zeilen-Snippet holen
                lines = text.splitlines()
                snippet = lines[line_no - 1].strip() if line_no <= len(lines) else ""
                hits.append(AuditHit(
                    file=str(py.relative_to(root)),
                    line=line_no,
                    code=snippet[:200],
                    pattern=pat.pattern[:60],
                ))
    return hits


def audit_description() -> dict:
    """Komplette Audit für videos.description-Lesezugriffe."""
    hits = scan_for_field("description")
    by_file = {}
    for h in hits:
        by_file.setdefault(h.file, []).append({
            "line": h.line, "code": h.code, "pattern": h.pattern,
        })
    return {
        "field": "description",
        "total_hits": len(hits),
        "files_with_hits": len(by_file),
        "ready_to_empty": len(hits) == 0,
        "by_file": by_file,
    }
