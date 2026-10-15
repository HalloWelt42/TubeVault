"""
TubeVault – Fernsteuerung: Verbindung der Geräte (services/remote_hub)
"""
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.services.remote_hub import Device, Kind, hub

router = APIRouter(prefix="/api/remote", tags=["Fernsteuerung"])


@router.get("/devices", response_model=list[Device])
async def devices():
    """Alle Geräte, auf denen TubeVault gerade offen ist, mit ihrem Wiedergabestand."""
    return hub.devices()


@router.websocket("/ws")
async def remote_socket(websocket: WebSocket,
                        id: str = Query(..., min_length=8, max_length=64),
                        geraet: str = Query(..., min_length=8, max_length=64),
                        name: str = Query("Gerät", max_length=80),
                        art: Kind = Query("rechner")):
    await websocket.accept()
    await hub.join(websocket, id, geraet, name, art)
    try:
        while True:
            text = await websocket.receive_text()
            if text == "ping":
                await websocket.send_text("pong")
                continue
            try:
                await hub.handle(id, json.loads(text))
            except json.JSONDecodeError:
                continue
    except WebSocketDisconnect:
        pass
    finally:
        await hub.leave(id, websocket)
