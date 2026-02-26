"""
TubeVault -  API Endpoints Router v1.5.90
CRUD + Test für registrierte API-Endpunkte.
© HalloWelt42 -  Private Nutzung
"""

import logging
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/endpoints", tags=["API Endpoints"])


class EndpointCreate(BaseModel):
    name: str
    label: str
    url: str
    category: str = "external"
    enabled: bool = True
    test_path: Optional[str] = None
    description: Optional[str] = None
    sort_order: int = 0


class EndpointUpdate(BaseModel):
    label: Optional[str] = None
    url: Optional[str] = None
    category: Optional[str] = None
    enabled: Optional[bool] = None
    test_path: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


@router.get("")
async def list_endpoints():
    """Alle registrierten API-Endpunkte auflisten."""
    rows = await db.fetch_all(
        "SELECT * FROM api_endpoints ORDER BY sort_order, category, name"
    )
    return [dict(r) for r in rows]


@router.post("")
async def create_endpoint(ep: EndpointCreate):
    """Neuen API-Endpunkt registrieren."""
    try:
        await db.execute(
            """INSERT INTO api_endpoints (name, label, url, category, enabled, test_path, description, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (ep.name, ep.label, ep.url, ep.category, ep.enabled, ep.test_path, ep.description, ep.sort_order)
        )
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(400, f"Endpunkt '{ep.name}' existiert bereits")
        raise HTTPException(500, str(e))
    return {"status": "ok", "name": ep.name}


@router.put("/{ep_id}")
async def update_endpoint(ep_id: int, ep: EndpointUpdate):
    """Endpunkt aktualisieren."""
    updates = {k: v for k, v in ep.model_dump().items() if v is not None}
    if not updates:
        return {"status": "ok"}
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [ep_id]
    await db.execute(f"UPDATE api_endpoints SET {set_clause} WHERE id = ?", values)
    return {"status": "ok"}


@router.delete("/{ep_id}")
async def delete_endpoint(ep_id: int):
    """Endpunkt entfernen."""
    await db.execute("DELETE FROM api_endpoints WHERE id = ?", (ep_id,))
    return {"status": "ok"}


@router.post("/{ep_id}/test")
async def test_endpoint(ep_id: int):
    """Endpunkt-Erreichbarkeit testen."""
    row = await db.fetch_one("SELECT * FROM api_endpoints WHERE id = ?", (ep_id,))
    if not row:
        raise HTTPException(404, "Endpunkt nicht gefunden")

    url = row["url"].rstrip("/")
    test_path = row["test_path"] or ""
    full_url = url + test_path

    now = datetime.utcnow().isoformat()
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(full_url)
            status = f"{resp.status_code} {resp.reason_phrase}"
            ok = 200 <= resp.status_code < 400

            # Antwortgröße + Content-Type
            ct = resp.headers.get("content-type", "")
            size = len(resp.content)

            await db.execute(
                "UPDATE api_endpoints SET last_tested = ?, last_status = ? WHERE id = ?",
                (now, status, ep_id)
            )
            return {
                "status": "ok" if ok else "error",
                "http_status": resp.status_code,
                "status_text": status,
                "content_type": ct,
                "response_size": size,
                "url": full_url,
                "tested_at": now,
            }
    except httpx.TimeoutException:
        await db.execute(
            "UPDATE api_endpoints SET last_tested = ?, last_status = ? WHERE id = ?",
            (now, "TIMEOUT", ep_id)
        )
        return {"status": "error", "http_status": 0, "status_text": "Timeout (10s)", "url": full_url, "tested_at": now}
    except Exception as e:
        err = str(e)[:200]
        await db.execute(
            "UPDATE api_endpoints SET last_tested = ?, last_status = ? WHERE id = ?",
            (now, f"ERROR: {err}", ep_id)
        )
        return {"status": "error", "http_status": 0, "status_text": err, "url": full_url, "tested_at": now}
