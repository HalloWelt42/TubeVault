"""
TubeVault Backend – Konfiguration v1.5.1
© HalloWelt42 – Private Nutzung
"""

import os
from pathlib import Path

# Basis-Pfade
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = Path(os.getenv("TUBEVAULT_DATA_DIR", "/app/data"))
CONFIG_DIR = Path(os.getenv("TUBEVAULT_CONFIG_DIR", "/app/config"))

# Unterverzeichnisse
VIDEOS_DIR = DATA_DIR / "videos"
AUDIO_DIR = DATA_DIR / "audio"
THUMBNAILS_DIR = DATA_DIR / "thumbnails"
METADATA_DIR = DATA_DIR / "metadata"
SUBTITLES_DIR = DATA_DIR / "subtitles"
AVATARS_DIR = DATA_DIR / "avatars"
BANNERS_DIR = DATA_DIR / "banners"
DB_DIR = DATA_DIR / "db"
EXPORTS_DIR = DATA_DIR / "exports"
TEMP_DIR = DATA_DIR / "temp"
SCAN_DIR = DATA_DIR / "scan"
RSS_THUMBS_DIR = DATA_DIR / "rss_thumbs"
TEXTS_DIR = DATA_DIR / "texts"
# Eigene Musiksammlung (FLAC usw.), im Container nur lesend eingehängt
# (docker-compose: TUBEVAULT_MUSIC_SOURCE); Cover-Ablage beschreibbar daneben
MUSIC_FILES_DIR = DATA_DIR / "musik"
MUSIC_COVERS_DIR = DATA_DIR / "musik_cover"

# Datenbank
DB_PATH = DB_DIR / "tubevault.db"

# Sicherungen der Datenbank (services/sicherung.py), auf dem Pi bei den Medien
BACKUP_DIR = EXPORTS_DIR / "backups"
# Sicherungsregel, die eine Stelle für App und scripts/backup_db.sh; überschreibbar über die Umgebung bzw. die .env
# des Klons (docker-compose.yml reicht sie durch, leer heißt Vorgabe):
# regelmäßig frühestens am sicherung_abstand_tage-ten Kalendertag nach der jüngsten Sicherung, vor dem Ausrollen nur,
# wenn die jüngste älter ist als sicherung_vor_ausrollen_ab_stunden, höchstens sicherung_behalten Stände (mindestens 1)
SICHERUNG_ABSTAND_TAGE = int(os.getenv("TUBEVAULT_SICHERUNG_ABSTAND_TAGE") or 7)
SICHERUNG_VOR_AUSROLLEN_AB_STUNDEN = int(os.getenv("TUBEVAULT_SICHERUNG_VOR_AUSROLLEN_AB_STUNDEN") or 24)
SICHERUNG_BEHALTEN = max(1, int(os.getenv("TUBEVAULT_SICHERUNG_BEHALTEN") or 3))

# Server
HOST = os.getenv("TUBEVAULT_HOST", "0.0.0.0")
PORT = int(os.getenv("TUBEVAULT_PORT", "8031"))

# Downloads
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "1"))
DEFAULT_QUALITY = os.getenv("DEFAULT_QUALITY", "720p")
DEFAULT_FORMAT = os.getenv("DEFAULT_FORMAT", "mp4")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", str(1024 * 1024)))  # 1MB

# Versioning
VERSION = "2.92.1"
APP_NAME = "TubeVault"

# CORS – immer offen, keine Einschränkungen
CORS_ORIGINS = ["*"]


def ensure_directories():
    """Alle Datenverzeichnisse erstellen falls nicht vorhanden."""
    for d in [VIDEOS_DIR, AUDIO_DIR, THUMBNAILS_DIR, METADATA_DIR,
              SUBTITLES_DIR, AVATARS_DIR, BANNERS_DIR, DB_DIR, EXPORTS_DIR, TEMP_DIR, RSS_THUMBS_DIR, TEXTS_DIR,
              SCAN_DIR]:
        d.mkdir(parents=True, exist_ok=True)
