"""
TubeVault – Einstellungs-Schema v1.0.0

Die EINE Liste aller Einstellungen, die der Nutzer verändern kann.

Vorher gab es drei Listen, die auseinanderliefen: die Standardwerte in der
Datenbank, die Regler in der Oberfläche und die Stellen im Code, die Werte
lesen. Folge: Regler ohne Wirkung, Regler auf nicht vorhandene Schlüssel
(Speichern scheiterte), ungeprüfte Werte, die später beim Lesen abstürzten.

Regeln:
  - Was hier steht, hat einen Verbraucher im Code. Kein Eintrag ohne Wirkung.
  - Standardwerte, Grenzen und Auswahllisten stehen nur hier; Datenbank
    (DEFAULT_SETTINGS), Prüfung beim Speichern und Oberfläche leiten sich ab.
  - section = Block der Einstellungsseite (channels, view, extensions);
    None = wird an anderer Stelle
    bedient (z.B. Drosselung auf der Jobs-Seite), aber hier geprüft.
"""
from typing import Literal, Optional

from pydantic import BaseModel

# Qualitäten, die Download und Auswahllisten kennen (höchste zuerst)
VIDEO_QUALITIES = ["best", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p", "144p"]

SettingKind = Literal["toggle", "number", "duration", "select", "text"]


class SettingDef(BaseModel):
    key: str
    default: str
    kind: SettingKind
    label: str
    description: str = ""
    category: str                      # Gruppe in der Datenbank
    section: Optional[str] = None      # Reiter der Einstellungsseite
    min: Optional[float] = None
    max: Optional[float] = None
    unit: Optional[str] = None
    step: Optional[float] = None      # Schrittweite des Eingabefelds (Standard 1)
    options: Optional[list[str]] = None
    option_labels: Optional[dict[str, str]] = None   # Anzeige je Auswahlwert


SETTINGS: list[SettingDef] = [
    # ── Scanner ───────────────────────────────────────────────────────
    SettingDef(key="rss.enabled", default="true", kind="toggle", category="rss", section="channels",
               label="Scanner aktiv",
               description="Prüft automatisch alle abonnierten Kanäle auf neue Videos."),
    SettingDef(key="rss.interval", default="1800", kind="duration", category="rss", section="channels",
               min=300, max=86400, label="Basis-Prüfintervall",
               description="Startintervall für neue Abos. Verdoppelt sich bei jeder Prüfung ohne neue "
                           "Videos bis zum längsten Prüfintervall. Neue Videos setzen auf diesen Wert "
                           "zurück."),
    SettingDef(key="rss.max_interval", default="86400", kind="duration", category="rss",
               section="channels", min=1800, max=604800, label="Längstes Prüfintervall",
               description="So lange bleibt ein ruhiger Kanal höchstens ungeprüft. Ein neues Video "
                           "erscheint spätestens nach dieser Zeit im Feed."),
    SettingDef(key="rss.max_age_days", default="90", kind="number", category="rss", section="channels",
               min=7, max=365, unit="Tage", label="Maximales Video-Alter",
               description="Bei der Prüfung auf neue Videos werden ältere Einträge übergangen."),
    # ── Feed ──────────────────────────────────────────────────────────
    SettingDef(key="shorts.exclude", default="false", kind="toggle", category="feed", section="channels",
               label="Shorts ausschließen",
               description="Shorts erscheinen nirgends (Feed, Bibliothek, Archiv, Suche) und werden "
                           "nicht automatisch geladen. Was ein Short ist, bestätigt die Quelle - "
                           "die Dauer allein entscheidet nicht."),
    # ── Auto-Download ─────────────────────────────────────────────────
    SettingDef(key="rss.auto_dl_daily_limit", default="20", kind="number", category="rss",
               section="channels", min=1, max=200, unit="pro Tag", label="Tageslimit",
               description="Höchstzahl automatischer Downloads pro Tag (Schutz vor Massen-Downloads)."),
    # ── Downloads ─────────────────────────────────────────────────────
    SettingDef(key="download.quality", default="720p", kind="select", category="download",
               section="channels", options=VIDEO_QUALITIES, label="Standard-Qualität",
               description="Gilt für alle Downloads, wenn weder der Auftrag noch der Kanal eine "
                           "Qualität vorgibt."),
    SettingDef(key="download.auto_subtitle", default="false", kind="toggle", category="download",
               section="channels", label="Untertitel herunterladen"),
    SettingDef(key="download.subtitle_lang", default="de,en", kind="text", category="download",
               section="channels", label="Untertitel-Sprachen",
               description="Kommagetrennt, z.B. de,en. Alle genannten Sprachen werden geladen."),
    SettingDef(key="download.throttle_kbps", default="0", kind="number", category="download",
               section="channels", min=0, max=100000, unit="KB/s", label="Bandbreiten-Limit",
               description="0 = unbegrenzt. Wirkt nicht, solange auf der Jobs-Seite die Drosselung "
                           "in Echtzeit eingeschaltet ist."),
    SettingDef(key="download.throttle_realtime", default="false", kind="toggle", category="download",
               label="Drosselung in Echtzeit"),
    SettingDef(key="download.cooldown_base_s", default="30", kind="number", category="download",
               min=5, max=3600, unit="s", label="Pause zwischen Downloads"),
    # ── Allgemein ─────────────────────────────────────────────────────
    SettingDef(key="general.videos_per_page", default="24", kind="number", category="general",
               section="view", min=12, max=96, label="Videos pro Seite",
               description="So viele Videos lädt eine Liste je Schritt nach."),
    # ── Erweiterungen ─────────────────────────────────────────────────
    SettingDef(key="dub.enabled", default="false", kind="toggle", category="dub",
               section="extensions", label="Nachvertonung",
               description="Einzelne Videos in der Wiedergabe zum Nachvertonen vormerken (Stimme und "
                           "Sprache wählst du dort). Die Arbeit erledigt der Nachvertoner auf einem "
                           "leistungsfähigen Rechner; die fertige Tonspur ist in der Wiedergabe umschaltbar."),
    SettingDef(key="ai.enabled", default="false", kind="toggle", category="ai",
               section="extensions", label="Bedeutungssuche mit lokaler KI",
               description="Die Suche findet zusätzlich inhaltlich Verwandtes, auch ohne Wortgleichheit. "
                           "Die Vektoren rechnet ein lokaler KI-Dienst; ist er nicht erreichbar, arbeitet "
                           "die Suche als reine Wortsuche weiter."),
    SettingDef(key="ai.url", default="", kind="text", category="ai", section="extensions",
               label="Adresse des KI-Dienstes",
               description="OpenAI-kompatible Schnittstelle, z.B. http://192.168.178.20:1234/v1"),
    # ── System ────────────────────────────────────────────────────────
    SettingDef(key="archive.mount_check_interval", default="30", kind="number", category="archive",
               min=5, max=3600, unit="s", label="Prüfintervall für externe Archive"),
]

BY_KEY: dict[str, SettingDef] = {d.key: d for d in SETTINGS}

# Früher angelegte Einstellungen ohne Wirkung. Werden aus der Datenbank
# entfernt, damit kein Regler etwas verspricht, das nicht passiert.
REMOVED_KEYS = [
    "feed.auto_classify",          # Erkennung lief immer, Regler wurde nie gelesen
    "feed.auto_refresh",           # zugehöriger Hintergrundlauf wurde nie gestartet
    "feed.refresh_interval_days",
    "rss.auto_download",           # nur der Schalter am Kanal entscheidet
    "download.format",             # Ergebnis ist immer mp4
    "download.concurrent",         # es läuft immer genau ein Download
    "theme.mode",                  # Erscheinungsbild liegt im Browser
    "theme.accent",
    "general.language",
    "general.default_view",
    "feed.hide_shorts",            # ersetzt durch shorts.exclude (gilt überall)
    "dub.voice",                   # Stimme und Sprache wählt man je Video
    "dub.target_language",
    "dub.subtitles",
    "rss.auto_quality",            # es gilt die Standard-Qualität bzw. die des Kanals
    "download.auto_thumbnail",     # Vorschaubild und Kapitel werden immer gespeichert
    "download.auto_chapters",
    "player.volume",               # der Player merkt sich die letzte Lautstärke
    "player.autoplay",
    "player.speed",
    "player.save_position",        # die Position wird immer gemerkt
    "ai.embedding_model",          # fest (semantic_index.EMBEDDING_MODEL)
    "ai.min_similarity",
]


def default_rows() -> list[tuple[str, str, str, str]]:
    """Zeilen für die settings-Tabelle: (key, value, description, category)."""
    return [(d.key, d.default, d.description or d.label, d.category) for d in SETTINGS]


def validate(key: str, raw) -> str:
    """Wert prüfen und in die gespeicherte Schreibweise bringen.
    Wirft ValueError mit einer Meldung für den Nutzer."""
    definition = BY_KEY.get(key)
    if definition is None:
        raise KeyError(key)
    value = str(raw).strip()

    if definition.kind == "toggle":
        if value.lower() not in ("true", "false"):
            raise ValueError(f"{definition.label}: nur an oder aus möglich")
        return value.lower()

    if definition.kind in ("number", "duration"):
        try:
            number = float(value.replace(",", "."))
        except ValueError:
            raise ValueError(f"{definition.label}: bitte eine Zahl eingeben")
        if definition.min is not None and number < definition.min:
            raise ValueError(f"{definition.label}: mindestens {definition.min:g}")
        if definition.max is not None and number > definition.max:
            raise ValueError(f"{definition.label}: höchstens {definition.max:g}")
        return str(int(number)) if number == int(number) else str(number)

    if definition.kind == "select":
        if value not in (definition.options or []):
            raise ValueError(f"{definition.label}: '{value}' steht nicht zur Auswahl")
        return value

    # text
    if key == "ai.url":
        if value and not value.startswith(("http://", "https://")):
            raise ValueError(f"{definition.label}: Adresse muss mit http:// oder https:// beginnen")
        return value.rstrip("/")
    if key == "download.subtitle_lang":
        langs = [part.strip().lower() for part in value.split(",") if part.strip()]
        if not langs or not all(part.replace("-", "").isalnum() and len(part) <= 10 for part in langs):
            raise ValueError(f"{definition.label}: Sprachkürzel kommagetrennt angeben, z.B. de,en")
        return ",".join(langs)
    return value
