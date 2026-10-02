#!/usr/bin/env python3
"""
TubeVault – Testdaten für die lokale Entwicklung.

Legt unter data/dev/ eine eigene Datenbank mit erfundenen Videos, Kanälen und
Feed-Einträgen an. Die echte Installation wird nie berührt: Das Skript
schreibt ausschließlich in data/dev/ und holt nichts aus dem Netz.

Die Testdaten bilden gezielt die Fälle ab, an denen Listen, Suche und Filter
früher scheiterten:
  - grosses Archiv, kleine Bibliothek (Suche muss beides finden)
  - viele Videos mit demselben Upload-Tag (Sortier-Gleichstand beim Nachladen)
  - Videos ohne Kanalnamen, deren Kanal im Abo bekannt ist
  - Tags, die nur im Archiv vorkommen

Aufruf (aus dem Projektordner):
    backend/.venv/bin/python scripts/dev_seed.py          # anlegen
    backend/.venv/bin/python scripts/dev_seed.py --reset  # neu aufsetzen

Danach Backend und Oberfläche gegen die Testdaten starten:
    TUBEVAULT_DATA_DIR=data/dev TUBEVAULT_CONFIG_DIR=data/dev/config \\
        backend/.venv/bin/uvicorn app.main:app --app-dir backend --port 8033
    TUBEVAULT_API=http://localhost:8033 npm --prefix frontend run dev -- --port 5183
"""
import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV_DIR = ROOT / "data" / "dev"

os.environ["TUBEVAULT_DATA_DIR"] = str(DEV_DIR)
os.environ["TUBEVAULT_CONFIG_DIR"] = str(DEV_DIR / "config")
sys.path.insert(0, str(ROOT / "backend"))

CHANNELS = [
    ("UCdev0000000000000000001", "Werkbank Nord"),
    ("UCdev0000000000000000002", "Küchenlabor"),
    ("UCdev0000000000000000003", "Gleisplan"),
    ("UCdev0000000000000000004", "Sternstunde"),
]
TOPICS = ["Löten", "Hefeteig", "Weichenbau", "Mondfinsternis", "Fräsen", "Sauerteig",
          "Signaltechnik", "Sternbilder", "Oszilloskop", "Brühe"]
ARCHIVED_COUNT = 160
LIBRARY_COUNT = 40
NAMELESS_EVERY = 9   # jedes 9. Video ohne Kanalnamen (Abo kennt ihn)


def make_clip(target: Path) -> None:
    """Ein winziges, abspielbares Testvideo erzeugen (ohne ffmpeg: Platzhalter)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg"):
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc=duration=4:size=320x180:rate=12",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
             str(target)],
            check=True,
        )
    else:
        target.write_bytes(b"\x00" * 2048)


async def seed() -> None:
    from app.config import VIDEOS_DIR, ensure_directories
    from app.database import db

    ensure_directories()
    (DEV_DIR / "config").mkdir(parents=True, exist_ok=True)
    await db.connect()

    clip = DEV_DIR / "clip.mp4"
    if not clip.exists():
        make_clip(clip)

    # Hintergrunddienste stillegen: Testbetrieb holt nichts aus dem Netz
    for key, value in (("rss.enabled", "false"), ("queue.paused", "true")):
        await db.execute(
            "INSERT INTO settings (key, value, category) VALUES (?, ?, 'general') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    await db.execute(
        "INSERT INTO settings (key, value, category) VALUES ('system.expected_min_videos', '1', 'general') "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value")

    for channel_id, name in CHANNELS:
        await db.execute(
            "INSERT OR IGNORE INTO subscriptions (channel_id, channel_name, enabled) VALUES (?, ?, 0)",
            (channel_id, name))

    total = ARCHIVED_COUNT + LIBRARY_COUNT
    for n in range(total):
        video_id = f"dev{n:08d}"
        channel_id, channel_name = CHANNELS[n % len(CHANNELS)]
        topic = TOPICS[n % len(TOPICS)]
        archived = 1 if n < ARCHIVED_COUNT else 0
        # Gleichstand erzwingen: je 25 Videos teilen sich einen Upload-Tag
        upload_date = f"2026-{1 + (n // 25) % 9:02d}-15 00:00:00"
        tags = [topic.lower(), "archivtag" if archived else "bibliothekstag"]
        file_path = VIDEOS_DIR / video_id / "video.mp4"
        if not file_path.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(clip, file_path)
        await db.execute(
            """INSERT OR REPLACE INTO videos
               (id, title, channel_name, channel_id, description, duration, upload_date,
                download_date, tags, status, file_path, file_size, source, video_type,
                is_archived, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, 'ready', ?, ?, 'youtube', ?, ?,
                       datetime('now'), datetime('now'))""",
            (video_id, f"{topic} Folge {n + 1}",
             None if n % NAMELESS_EVERY == 0 else channel_name, channel_id,
             f"Testbeschreibung zu {topic}, Folge {n + 1}. Stichwort Prüfstand.",
             240 + n, upload_date, json.dumps(tags, ensure_ascii=False),
             str(file_path), file_path.stat().st_size,
             "short" if n % 11 == 0 else "video", archived))
        await db.execute(
            """INSERT OR IGNORE INTO rss_entries (video_id, channel_id, title, published, duration)
               VALUES (?, ?, ?, ?, ?)""",
            (video_id, channel_id, f"{topic} Folge {n + 1}", upload_date, 240 + n))

    await db.fts_rebuild_from_resolver()
    await db.disconnect()
    print(f"Testdaten bereit: {total} Videos ({ARCHIVED_COUNT} im Archiv) unter {DEV_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--reset", action="store_true", help="data/dev vorher löschen")
    args = parser.parse_args()
    if args.reset and DEV_DIR.exists():
        shutil.rmtree(DEV_DIR)
    asyncio.run(seed())


if __name__ == "__main__":
    main()
