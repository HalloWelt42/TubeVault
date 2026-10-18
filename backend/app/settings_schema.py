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
  - section = Block der Einstellungsseite (channels, downloads, view, extensions, system);
    None = wird an anderer Stelle
    bedient (z.B. Drosselung auf der Jobs-Seite), aber hier geprüft.
"""
from typing import Literal, Optional

from pydantic import BaseModel

from app.services import language

# Qualitäten, die Download und Auswahllisten kennen (höchste zuerst)
VIDEO_QUALITIES = ["best", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p", "144p"]

SettingKind = Literal["toggle", "number", "duration", "select", "text", "secret", "choices"]


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
    zero_label: Optional[str] = None   # 0 bedeutet "ohne Grenze"; so heißt es in der Oberfläche
    options_from: Optional[str] = None # choices: Adresse, die die Auswahl live liefert (GET, Liste aus value, label, hint)


SETTINGS: list[SettingDef] = [
    # ── Scanner ───────────────────────────────────────────────────────
    SettingDef(key="rss.enabled", default="true", kind="toggle", category="rss", section="channels",
               label="Kanäle prüfen",
               description="Abonnierte Kanäle automatisch auf neue Videos prüfen."),
    SettingDef(key="rss.interval", default="43200", kind="duration", category="rss", section="channels",
               min=3600, max=86400, label="Grundtakt",
               description="So oft wird ein Kanal geprüft, der kürzlich ein Video gezeigt hat. Je länger "
                           "sein neuestes Video zurückliegt, desto seltener (ein Viertel dessen Alters); "
                           "ein neues Video setzt sofort auf den Grundtakt zurück."),
    SettingDef(key="rss.max_interval", default="2592000", kind="duration", category="rss",
               section="channels", min=86400, max=2592000, label="Längster Prüfabstand",
               description="So lange bleibt ein Kanal, der seit Langem nichts zeigt, höchstens "
                           "ungeprüft."),
    SettingDef(key="rss.max_age_days", default="90", kind="number", category="rss", section="channels",
               min=0, max=3650, unit="Tage", zero_label="alle", label="Höchstes Video-Alter",
               description="Neu im Feed erscheinen nur Videos bis zu diesem Alter."),
    # ── Feed ──────────────────────────────────────────────────────────
    SettingDef(key="shorts.exclude", default="false", kind="toggle", category="feed", section="channels",
               label="Shorts ausschließen",
               description="Shorts erscheinen nirgends (Feed, Bibliothek, Archiv, Suche) und werden "
                           "nicht automatisch geladen. Was ein Short ist, bestätigt die Quelle - "
                           "die Dauer allein entscheidet nicht."),
    # ── Auto-Download ─────────────────────────────────────────────────
    SettingDef(key="rss.auto_dl_daily_limit", default="20", kind="number", category="rss",
               section="downloads", min=0, max=1000, unit="je Tag", zero_label="unbegrenzt",
               label="Automatische Downloads",
               description="Höchstzahl automatischer Downloads je Tag (Auto-Download und Drip)."),
    # ── Downloads ─────────────────────────────────────────────────────
    SettingDef(key="download.quality", default="720p", kind="select", category="download",
               section="downloads", options=VIDEO_QUALITIES, label="Standard-Qualität",
               description="Gilt für alle Downloads, wenn weder der Auftrag noch der Kanal eine "
                           "Qualität vorgibt."),
    SettingDef(key="download.auto_subtitle", default="false", kind="toggle", category="download",
               section="downloads", label="Untertitel mitladen",
               description="Beim Download und beim Öffnen eines Videos, in den genannten Sprachen."),
    SettingDef(key="download.subtitle_lang", default="de,en", kind="text", category="download",
               section="downloads", label="Untertitel-Sprachen",
               description="Kommagetrennt, z.B. de,en. Die erste vorhandene wird genommen."),
    SettingDef(key="download.throttle_kbps", default="0", kind="number", category="download",
               min=0, max=100000, unit="KB/s", label="Drosselung",
               description="0 = ohne Grenze. Wirkt nicht, solange die dynamische Drosselung an ist. "
                           "Eingestellt auf der Downloads-Seite."),
    SettingDef(key="download.throttle_realtime", default="false", kind="toggle", category="download",
               label="Drosselung in Echtzeit"),
    SettingDef(key="download.cooldown_base_s", default="30", kind="number", category="download",
               min=5, max=3600, unit="s", label="Pause zwischen Downloads"),
    # ── Allgemein ─────────────────────────────────────────────────────
    SettingDef(key="general.videos_per_page", default="24", kind="number", category="general",
               section="view", min=12, max=96, label="Videos je Ladeschritt",
               description="So viele Videos lädt eine Liste je Schritt nach."),
    SettingDef(key="language.main", default="de", kind="select", category="general", section="view",
               options=[lang.code for lang in language.LANGUAGES],
               option_labels={lang.code: lang.name for lang in language.LANGUAGES},
               label="Hauptsprache",
               description="Sprach-Labels erscheinen nur bei Videos und Kanälen in anderen Sprachen - so steht "
                           "nicht auf fast jeder Kachel dieselbe Flagge."),
    # ── Erweiterungen ─────────────────────────────────────────────────
    SettingDef(key="dub.enabled", default="false", kind="toggle", category="dub",
               section="extensions", label="Nachvertonung",
               description="Einzelne Videos in der Wiedergabe zum Nachvertonen vormerken (Stimme und "
                           "Sprache wählst du dort). Die Arbeit erledigt der Nachvertoner auf einem "
                           "leistungsfähigen Rechner; die fertige Tonspur ist in der Wiedergabe umschaltbar."),
    # Vorauswahl beim Vormerken, gewählt auf der Seite Nachvertonung (Stern, Untertitel)
    SettingDef(key="dub.default_voice", default="", kind="text", category="dub",
               label="Vorauswahl-Stimme",
               description="Stimme, die beim Vormerken vorgewählt ist. Leer: die erste gemeldete Stimme, "
                           "deren Name mit Zeit beginnt."),
    SettingDef(key="dub.default_subtitles", default="any", kind="select", category="dub",
               options=["manual", "any"], option_labels={"manual": "vom Autor", "any": "auch automatische"},
               label="Untertitel als Transkript",
               description="Vorauswahl beim Vormerken: welche Untertitel der Quelle das Transkribieren "
                           "ersparen dürfen. Je Video änderbar."),
    SettingDef(key="ai.enabled", default="false", kind="toggle", category="ai",
               section="extensions", label="Bedeutungssuche mit lokaler KI",
               description="Die Suche findet zusätzlich inhaltlich Verwandtes, auch ohne Wortgleichheit. "
                           "Die Vektoren rechnet ein lokaler KI-Dienst; ist er nicht erreichbar, arbeitet "
                           "die Suche als reine Wortsuche weiter."),
    SettingDef(key="ai.url", default="", kind="text", category="ai", section="extensions",
               label="Adresse des KI-Dienstes",
               description="OpenAI-kompatible Schnittstelle, z.B. http://192.168.178.20:1234/v1"),
    # Weg zum KI-Dienst (Wunsch 16.10.2026): direkt oder über die Leitstelle, jederzeit umschaltbar.
    # Nur die KI-Aufrufe gehen diesen Weg; Videoquelle, Bewertungen, Liedtexte, Werbeabschnitte und
    # alle anderen Anbindungen bleiben direkt.
    SettingDef(key="ai.route", default="direct", kind="select", category="ai", section="extensions",
               options=["direct", "leitstelle"], option_labels={"direct": "Direkt", "leitstelle": "Über die Leitstelle"},
               label="Weg zum KI-Dienst",
               description="Direkt: TubeVault spricht den KI-Dienst unter der Adresse oben selbst an. Über die "
                           "Leitstelle: die KI-Anfragen gehen an die Leitstelle, die Speicher, Vorrang und "
                           "Warteschlange für alle Programme regelt. Nur die KI nimmt diesen Weg; Videoquelle, "
                           "Bewertungen, Liedtexte und alle anderen Anbindungen bleiben direkt."),
    SettingDef(key="ai.leitstelle_url", default="", kind="text", category="ai", section="extensions",
               label="Adresse der Leitstelle",
               description="Fassade der Leitstelle, z.B. http://192.168.178.49:8530/v1. Gilt, wenn der Weg "
                           "zum KI-Dienst auf Leitstelle steht."),
    SettingDef(key="ai.leitstelle_key", default="", kind="secret", category="ai", section="extensions",
               label="Schlüssel der Leitstelle",
               description="Schlüssel der Anwendung TubeVault aus der Leitstelle (dort unter Anwendungen). "
                           "Wird bei jeder KI-Anfrage über die Leitstelle mitgeschickt."),
    # Erlaubnisliste externer Modelle (Nutzer 18.10.2026: die Apps entscheiden selbst per Einstellung, nur wo die
    # Qualität reicht; freiwillig, entlastet die lokale KI). Gespeichert als Namen durch Komma getrennt.
    SettingDef(key="ai.leitstelle_extern", default="", kind="choices", category="ai", section="extensions",
               options_from="/api/settings/options/ai.leitstelle_extern",
               label="Ausweichen nach extern",
               description="Externe Modelle (etwa bei Hetzner), auf die die Leitstelle ausweichen darf, wenn die "
                           "eigenen Rechner lange belegt sind; dabei verlassen Texte das Heimnetz. Nur wählen, wo "
                           "die Qualität reicht. Leer: alles bleibt im Heimnetz. Gilt über die Leitstelle."),
    SettingDef(key="ai.precision", default="ausgewogen", kind="select", category="ai", section="extensions",
               options=["weit", "ausgewogen", "genau", "sehr_genau"],
               option_labels={"weit": "Weit", "ausgewogen": "Ausgewogen", "genau": "Genau",
                              "sehr_genau": "Sehr genau"},
               label="Genauigkeit der Bedeutungssuche",
               description="Standard für jede Suche: Weit findet auch lose Verwandtes (mehr Treffer), "
                           "Sehr genau nur eng Passendes. Auf der Suchseite je Suche umstellbar."),
    SettingDef(key="ai.passages_enabled", default="true", kind="toggle", category="ai", section="extensions",
               label="Gesagtes für die Bedeutungssuche einbetten",
               description="Rechnet für jeden Abschnitt aus Transkripten und Untertiteln einen Vektor auf dem "
                           "KI-Dienst, damit die Bedeutungssuche auch im Gesagten findet. Viele Abschnitte "
                           "belegen den KI-Dienst stundenlang; Anhalten wirkt nach dem laufenden Stapel."),
    # ── Hintergrundarbeiten (geschaltet in deren Liste, nicht auf der Einstellungsseite) ──
    SettingDef(key="types.check_enabled", default="true", kind="toggle", category="types",
               label="Video-Typen bei der Quelle prüfen",
               description="Fragt im Hintergrund nach, was Short und was Video ist (eine Anfrage "
                           "etwa alle 2 Sekunden). Anhalten schont die Quelle."),
    SettingDef(key="transcripts.ai_enabled", default="true", kind="toggle", category="transcripts",
               label="KI-Transkripte erstellen",
               description="Der Rechner mit der Spracherkennung holt sich laufend das nächste Video. "
                           "Angehalten wird nach dem Video, das gerade bearbeitet wird."),
    SettingDef(key="transcripts.import_enabled", default="true", kind="toggle", category="transcripts",
               label="Mitgeladene Untertitel einlesen",
               description="Macht das Gesagte von Videos durchsuchbar, zu denen beim Laden Untertitel "
                           "mitkamen. Liest nur lokale Dateien, fragt nicht bei der Quelle."),
    SettingDef(key="system.update_check", default="true", kind="toggle", category="system", section="system",
               label="Nach neuen Versionen sehen",
               description="Liest alle 6 Stunden die Versionsnummer des öffentlichen Projekts, eine kleine Datei "
                           "ohne Konto. Ist eine neuere Version erschienen, steht oben rechts ein Hinweis."),
    SettingDef(key="scan.auto_enabled", default="false", kind="toggle", category="scan",
               label="Ungescannte Kanäle erfassen",
               description="Liest Kanäle, die noch nie vollständig gelesen wurden, von selbst: höchstens "
                           "einen alle 2 Stunden, bis alle erfasst sind. Standard: angehalten."),
    SettingDef(key="dub.processing_enabled", default="false", kind="toggle", category="dub",
               label="Vertonen",
               description="Nur solange das an ist, bekommt der Nachvertoner neue Aufträge. Angehalten wird "
                           "nach dem Auftrag, der gerade läuft. Standard: angehalten."),
    SettingDef(key="music.source", default="alle", kind="select", category="music",
               options=["alle", "sammlung", "videos"],
               option_labels={"alle": "Alles", "sammlung": "Eigene Sammlung", "videos": "Musikvideos"},
               label="Quelle der Musik",
               description="Was Musikseite und Musikspieler zeigen und spielen: die eigene Sammlung "
                           "(FLAC und andere Dateien), die Musikvideos oder beides. Gibt es einen Song "
                           "doppelt, gilt bei 'Alles' die Datei."),
    SettingDef(key="history.paused", default="false", kind="toggle", category="history",
               label="Verlauf pausiert",
               description="Solange an, schreibt TubeVault keinen Verlauf mit. Gemerkte Stellen "
                           "zum Weiterschauen werden weiter gespeichert."),
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


def default(key: str) -> str:
    """Standardwert einer Einstellung - die eine Quelle für Ersatzwerte im Code."""
    return next(s.default for s in SETTINGS if s.key == key)


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
        # Ganzzahlige Einstellungen (Schrittweite ganz oder ohne) werden gerundet
        # gespeichert: gelesen wird mit int(), und "1800.5" ließe sonst den
        # Scanner bei jedem Durchlauf abstürzen
        whole = definition.step is None or float(definition.step).is_integer()
        if whole or number == int(number):
            return str(int(round(number)))
        return str(number)

    if definition.kind == "select":
        if value not in (definition.options or []):
            raise ValueError(f"{definition.label}: '{value}' steht nicht zur Auswahl")
        return value

    if definition.kind == "choices":
        # Namen durch Komma; Schreibweise der Namen prüft der anbietende Dienst (hier die Leitstelle)
        names = [n.strip() for n in value.split(",") if n.strip()]
        if any(len(n) > 200 or any(c in n for c in "\r\n") for n in names):
            raise ValueError(f"{definition.label}: ungültiger Name")
        return ",".join(dict.fromkeys(names))

    # text
    if key in ("ai.url", "ai.leitstelle_url"):
        if value and not value.startswith(("http://", "https://")):
            raise ValueError(f"{definition.label}: Adresse muss mit http:// oder https:// beginnen")
        return value.rstrip("/")
    if definition.kind == "secret":
        if any(c.isspace() for c in value):
            raise ValueError(f"{definition.label}: ohne Leerzeichen")
        return value
    if key == "download.subtitle_lang":
        langs = [part.strip().lower() for part in value.split(",") if part.strip()]
        if not langs or not all(part.replace("-", "").isalnum() and len(part) <= 10 for part in langs):
            raise ValueError(f"{definition.label}: Sprachkürzel kommagetrennt angeben, z.B. de,en")
        return ",".join(langs)
    return value
