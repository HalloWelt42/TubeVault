"""
TubeVault - Lokale KI: Sprachmodell für Textaufgaben

Derselbe KI-Dienst wie die Bedeutungssuche (Einstellung ai.url, OpenAI-
kompatibel) beantwortet auch Textaufgaben, z.B. Themen benennen. Welches
Sprachmodell, legt TubeVault nicht fest. Direkt: genommen wird ein Modell, das
der Dienst gerade geladen hat - so lädt nie ein zweites großes Modell nach;
kennt der Dienst keinen Ladezustand, gilt das erste Sprachmodell seiner Liste.
Über die Leitstelle wählt sie (Kette der Anwendung TubeVault); externe Modelle
nur über die Erlaubnisliste ai.leitstelle_extern, nie durch eigene Wahl.

Antworten kommen als JSON nach Schema; Prosa wird vor dem Speichern auf
gerade Zeichen gebracht (Modelle halten sich nicht verlässlich daran).
"""
import json
import logging
import re
import time
from typing import Optional

import httpx

from app.services import semantic_index, setting_values

logger = logging.getLogger(__name__)

_MODEL_TTL_S = 60
_LIST_TIMEOUT_S = 5
_ANSWER_TIMEOUT_S = 300
_model: tuple[float, Optional[str]] = (0.0, None)
LEITSTELLE_WAEHLT = "leitstelle"     # Modellname, mit dem die Leitstelle selbst nach der Kette wählt


class ChatUnavailable(Exception):
    """Kein Sprachmodell erreichbar oder die Antwort taugt nicht."""


def _is_text_model(entry: dict) -> bool:
    kind = (entry.get("type") or "").lower()
    return kind in ("llm", "vlm") or (not kind and "embed" not in (entry.get("id") or "").lower())


async def _list_models(url: str) -> Optional[str]:
    if await semantic_index.via_leitstelle():
        # Die Leitstelle entscheidet; hier nur, ob sie TubeVault ein Sprachmodell im Heimnetz anbietet
        async with httpx.AsyncClient(timeout=_LIST_TIMEOUT_S, headers=await semantic_index.headers("Modelle lesen")) as client:
            response = await client.get(f"{url}/models")
            response.raise_for_status()
        eigene = [e for e in response.json().get("data", [])
                  if not (e.get("x-leitstelle") or {}).get("extern") and "text" in ((e.get("x-leitstelle") or {}).get("faehigkeiten") or [])]
        return LEITSTELLE_WAEHLT if eigene else None
    root = re.sub(r"/v1$", "", url)
    async with httpx.AsyncClient(timeout=_LIST_TIMEOUT_S, headers=await semantic_index.headers("Modelle lesen")) as client:
        # Dienste mit Ladezustand (/api/v0/models): ein geladenes Sprachmodell
        try:
            response = await client.get(f"{root}/api/v0/models")
            if response.status_code == 200:
                entries = [e for e in response.json().get("data", []) if _is_text_model(e)]
                loaded = [e["id"] for e in entries if e.get("state") == "loaded"]
                return loaded[0] if loaded else None
        except (httpx.HTTPError, ValueError):
            pass
        response = await client.get(f"{url}/models")
        response.raise_for_status()
        entries = [e for e in response.json().get("data", []) if _is_text_model(e)]
        return entries[0]["id"] if entries else None


async def extern_choices() -> dict:
    """Auswahl für die Erlaubnisliste: die externen Sprachmodelle, die die Leitstelle TubeVault anbietet."""
    if not await semantic_index.via_leitstelle():
        return {"options": [], "state": "Gilt nur über die Leitstelle (Weg zum KI-Dienst)"}
    url = (await setting_values.get("ai.leitstelle_url")).strip().rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=_LIST_TIMEOUT_S, headers=await semantic_index.headers("Modelle lesen")) as client:
            response = await client.get(f"{url}/models")
            response.raise_for_status()
    except httpx.HTTPError as e:
        return {"options": [], "state": f"Leitstelle antwortet nicht ({e.__class__.__name__})"}
    options = []
    for e in response.json().get("data", []):
        x = e.get("x-leitstelle") or {}
        if not x.get("extern") or "text" not in (x.get("faehigkeiten") or []):
            continue
        brief = x.get("steckbrief") or {}
        hint = brief.get("zweck") or "extern"
        if brief.get("anfragen_je_minute"):
            hint += f", höchstens {brief['anfragen_je_minute']} je Minute"
        options.append({"value": e["id"], "label": x.get("name") or e["id"], "hint": hint})
    state = f"gefunden: {len(options)} externe Modelle" if options else \
        "Die Leitstelle erlaubt TubeVault keine externen Modelle (Leitstelle, Anwendungen, Zone extern)"
    return {"options": options, "state": state}


async def pick_model() -> Optional[str]:
    """Das Sprachmodell für Textaufgaben, oder None (kurz zwischengespeichert)."""
    global _model
    checked, model = _model
    if time.time() - checked < _MODEL_TTL_S:
        return model
    cfg = await semantic_index.config()
    model = None
    if cfg:
        try:
            model = await _list_models(cfg[0])
        except Exception as e:
            logger.debug(f"[KI] Modelle nicht abrufbar: {e.__class__.__name__}")
    _model = (time.time(), model)
    return model


def forget_model() -> None:
    global _model
    _model = (0.0, None)


# Typografische Zeichen (als Codepunkte) und ihr gerader Ersatz
_DASHES = (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)
_DOUBLE_QUOTES = (0x201C, 0x201D, 0x201E, 0x201F, 0x00AB, 0x00BB)
_SINGLE_QUOTES = (0x2018, 0x2019, 0x201A, 0x201B, 0x2039, 0x203A)
_SPACES = (0x00A0, 0x202F, 0x2009)
_ELLIPSIS = chr(0x2026)
_PLAIN = str.maketrans({**{chr(c): "-" for c in _DASHES}, **{chr(c): '"' for c in _DOUBLE_QUOTES},
                        **{chr(c): "'" for c in _SINGLE_QUOTES}, **{chr(c): " " for c in _SPACES}})


def plain(text: str) -> str:
    """KI-Prosa auf gerade Zeichen: Striche, Anführungszeichen, Leerzeichen."""
    text = (text or "").translate(_PLAIN).replace(_ELLIPSIS, "...")
    text = re.sub(r"\s+-{2,}\s+", " - ", text)
    return " ".join(text.split())


async def complete_json(system: str, user: str, name: str, schema: dict,
                        timeout: float = _ANSWER_TIMEOUT_S) -> dict:
    """Eine Aufgabe an das geladene Sprachmodell, Antwort als JSON nach Schema."""
    cfg = await semantic_index.config()
    model = await pick_model()
    if not cfg or not model:
        raise ChatUnavailable("Kein Sprachmodell geladen")
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{cfg[0]}/chat/completions", json=payload,
                                         headers=await semantic_index.headers(f"Textaufgabe {name}"))
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        forget_model()
        raise ChatUnavailable(f"Das Sprachmodell antwortet nicht ({e.__class__.__name__})") from e
    content = re.sub(r"<think>.*?</think>", "", content or "", flags=re.S)
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    try:
        return json.loads(content)
    except ValueError as e:
        logger.info(f"[KI] Antwort kein JSON: {content[:300]}")
        raise ChatUnavailable("Die Antwort des Sprachmodells ließ sich nicht lesen") from e
