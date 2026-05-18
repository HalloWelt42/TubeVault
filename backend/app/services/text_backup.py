"""
TubeVault – Notfall-Backup für Text-Spalten v1.0.0

Bevor irgendeine DB-Spalte geleert wird, schreibt dieses Modul den Inhalt
ZUSÄTZLICH als Backup-Dateien weg. Nicht das Export-System, sondern eine
paranoide "worst case, alles kaputt" Versicherung.

Schreibt zwei Formate parallel (Redundanz):
1. JSON-Lines: eine Zeile pro Video (einfach zu parsen)
2. Raw-SQL:    INSERT-Statements (direkt einspielbar)

Ablage: exports_root/text-backups/descriptions-<timestamp>.{jsonl,sql}
"""
import gzip
import json
import logging
from datetime import datetime
from pathlib import Path

from app.database import db
from app.services.storage import storage

logger = logging.getLogger(__name__)


async def backup_description_column() -> dict:
    """Dumpt die kompletten videos.description in 2 Formaten
    in den exports_root/text-backups/-Ordner.
    Returns: {jsonl_path, sql_path, rows, bytes_jsonl, bytes_sql}
    """
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = storage.exports_root / "text-backups"
    out_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = out_dir / f"descriptions-{ts}.jsonl.gz"
    sql_path = out_dir / f"descriptions-{ts}.sql.gz"

    rows_all = await db.fetch_all(
        "SELECT id, description FROM videos "
        "WHERE description IS NOT NULL AND description != ''"
    )

    count = 0
    with gzip.open(jsonl_path, "wt", encoding="utf-8") as fj, \
         gzip.open(sql_path, "wt", encoding="utf-8") as fs:
        fs.write("-- TubeVault descriptions backup\n")
        fs.write(f"-- Generated: {ts}\n")
        fs.write(f"-- Rows: {len(rows_all)}\n\n")
        for row in rows_all:
            vid = row["id"]
            desc = row["description"] or ""
            # JSON-Lines: ein Objekt pro Zeile
            fj.write(json.dumps({"id": vid, "description": desc}, ensure_ascii=False) + "\n")
            # SQL: escaped UPDATE-Statement
            esc_desc = desc.replace("'", "''")
            esc_vid = vid.replace("'", "''")
            fs.write(f"UPDATE videos SET description='{esc_desc}' WHERE id='{esc_vid}';\n")
            count += 1

    jsonl_size = jsonl_path.stat().st_size
    sql_size = sql_path.stat().st_size
    logger.warning(
        f"[text_backup] descriptions gesichert: {count} Zeilen → "
        f"{jsonl_path.name} ({jsonl_size} B) + {sql_path.name} ({sql_size} B)"
    )
    return {
        "timestamp": ts,
        "rows": count,
        "jsonl_path": str(jsonl_path),
        "jsonl_size_bytes": jsonl_size,
        "sql_path": str(sql_path),
        "sql_size_bytes": sql_size,
    }


async def list_backups() -> list[dict]:
    """Alle vorhandenen Backups zurückgeben (für UI)."""
    out_dir = storage.exports_root / "text-backups"
    if not out_dir.exists():
        return []
    result = []
    for p in sorted(out_dir.iterdir(), reverse=True):
        if p.is_file():
            result.append({
                "filename": p.name,
                "size_bytes": p.stat().st_size,
                "mtime": int(p.stat().st_mtime),
            })
    return result
