"""
TubeVault -  Tag Sanitization v1.7.4
Bereinigt kaputte Tags aus YouTube-Metadaten.
© HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
"""

import re
import json
import logging

logger = logging.getLogger(__name__)

# Patterns die als ganzer Tag ungültig sind
INVALID_TAG_PATTERNS = [
    r'^[\(\)\[\]\{\}]+$',        # Nur Klammern: "(", ")", "((", etc.
    r'^\W+$',                     # Nur Sonderzeichen
    r'^#\w+$',                    # Hashtags wie #shorts (optional -  auskommentieren wenn gewünscht)
]

# Fragmente die typisch für schlecht gesplittete Titel sind
KNOWN_FRAGMENTS = {
    "(official", "official)", "(official)", 
    "(music", "music)", "(music)",
    "(video", "video)", "(video)",
    "(audio", "audio)", "(audio)",
    "(lyric", "lyric)", "(lyric)", "(lyrics)", "lyrics)",
    "(hd", "hd)", "(hd)",
    "(4k", "4k)", "(4k)",
    "(live", "live)", "(live)",
    "(full", "full)", "(full)",
    "(feat", "feat)", "(feat.)", "feat.)",
    "(ft", "ft)", "(ft.)", "ft.)",
    "(remix", "remix)", "(remix)",
    "(prod", "prod)", "(prod.)", "prod.)",
    "(visualizer", "visualizer)", "(visualizer)",
    "(explicit", "explicit)", "(explicit)",
    "(clean", "clean)", "(clean)",
    "(version", "version)", "(version)",
}

# Min/Max Länge
MIN_TAG_LENGTH = 2
MAX_TAG_LENGTH = 100


def sanitize_tag(tag: str) -> str | None:
    """Einzelnen Tag bereinigen. Gibt None zurück wenn ungültig."""
    if not tag or not isinstance(tag, str):
        return None
    
    tag = tag.strip()
    
    # Zu kurz / zu lang
    if len(tag) < MIN_TAG_LENGTH or len(tag) > MAX_TAG_LENGTH:
        return None
    
    # Bekannte Fragmente (case-insensitive)
    if tag.lower() in KNOWN_FRAGMENTS:
        return None
    
    # Unbalancierte Klammern am Rand → Reste abschneiden
    # z.B. "(Official Music Video)" → "Official Music Video"  
    # z.B. "Official Video)" → "Official Video"
    tag = re.sub(r'^\(+', '', tag).strip()
    tag = re.sub(r'\)+$', '', tag).strip()
    tag = re.sub(r'^\[+', '', tag).strip()
    tag = re.sub(r'\]+$', '', tag).strip()
    
    # Nach Bereinigung nochmal Länge prüfen
    if len(tag) < MIN_TAG_LENGTH:
        return None
    
    # Nur Sonderzeichen/Whitespace
    if not re.search(r'[a-zA-Z0-9\u00C0-\u024F\u0400-\u04FF\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF]', tag):
        return None
    
    return tag


def sanitize_tags(tags: list) -> list:
    """Liste von Tags bereinigen: Duplikate, Fragmente, leere Einträge entfernen."""
    if not tags or not isinstance(tags, list):
        return []
    
    seen = set()
    result = []
    
    for raw_tag in tags:
        clean = sanitize_tag(raw_tag)
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            result.append(clean)
    
    return result


def sanitize_tags_json(tags_json: str) -> str:
    """JSON-String mit Tags bereinigen, gibt bereinigten JSON-String zurück."""
    try:
        tags = json.loads(tags_json) if tags_json else []
    except (json.JSONDecodeError, TypeError):
        return "[]"
    
    return json.dumps(sanitize_tags(tags), ensure_ascii=False)
