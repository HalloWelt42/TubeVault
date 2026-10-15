"""
TubeVault – Fernsteuerung und Übergabe zwischen Geräten

Jedes Fenster, in dem TubeVault offen ist, verbindet sich per WebSocket und
ist damit ein Gerät (Wunsch 15.10.2026: vom Handy steuern, die Wiedergabe
zwischen Handy und Rechner wechseln). Der Server ist nur Vermittler:

  zustand     ein Gerät meldet, was es gerade spielt; alle anderen sehen es
  befehl      ein Gerät steuert ein anderes (Pause, Weiter, Stelle ...)
  uebergabe   ein Gerät gibt seine Wiedergabe samt Stelle und Warteschlange
              an ein anderes ab und hält selbst an

Nichts davon wird gespeichert: Wer die Verbindung schließt, ist weg. Ein
Fenster hat eine eigene Kennung (id), Fenster desselben Browsers teilen die
Gerätekennung (geraet) und den Namen.
"""
import logging
import time
from typing import Any, Literal, Optional, Protocol, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

logger = logging.getLogger(__name__)

MAX_NAME = 40
MAX_QUEUE = 5000

Kind = Literal["rechner", "handy", "tablet"]
Media = Literal["musik", "hoerbuch", "video"]
Action = Literal[
    "umschalten", "abspielen", "pause", "weiter", "zurueck", "stelle", "sprung",
    "lautstaerke", "zufall", "wiederholen", "liebling", "tonspur", "uebergeben",
]


class TrackChoice(BaseModel):
    id: int                                  # Kennung der Tonspur (audio_tracks)
    label: str


class PlayerState(BaseModel):
    """Was ein Gerät gerade spielt, so knapp, wie die Fernbedienung es braucht."""
    model_config = ConfigDict(extra="ignore")

    art: Optional[Media] = None
    kennung: Optional[str] = None            # Titel- oder Videokennung
    titel: str = ""
    untertitel: str = ""                     # Interpret oder Kanal
    quelle: str = ""                         # z.B. "ABBA Gold" oder "Teil 7 von 32"
    stelle: float = 0
    dauer: float = 0
    laeuft: bool = False
    lautstaerke: Optional[float] = None      # None: Gerät lässt sich nicht leiser stellen
    zufall: Optional[bool] = None
    wiederholen: Optional[str] = None
    liebling: Optional[bool] = None
    tonspuren: list[TrackChoice] = Field(default_factory=list)
    tonspur: Optional[int] = None            # None: Original
    kann: list[str] = Field(default_factory=list)   # z.B. weiter, zurueck, sprung


class Device(BaseModel):
    id: str
    geraet: str
    name: str
    art: Kind
    seit: float
    aktiv: float                             # zuletzt im Vordergrund
    zustand: Optional[PlayerState] = None


class QueueTrack(BaseModel):
    """Ein Titel der Warteschlange; alles Weitere reist unverändert mit."""
    model_config = ConfigDict(extra="allow")
    id: str
    title: str = ""
    duration: Optional[float] = None


class MusicPackage(BaseModel):
    queue: list[QueueTrack] = Field(max_length=MAX_QUEUE)
    index: int = 0
    title: str = ""
    source: Optional[str] = None
    time: float = 0
    shuffle: bool = False
    repeat: str = "off"


class VideoPackage(BaseModel):
    id: str
    stelle: float = 0
    liste: Optional[str] = None              # Quelle der Video-Warteschlange
    idx: int = 0
    tonspur: Optional[str] = None            # Sprache der gewählten Tonspur


class Package(BaseModel):
    art: Media
    musik: Optional[MusicPackage] = None
    video: Optional[VideoPackage] = None


# ─── Eingehende Nachrichten ───────────────────────────────────────────

class StateMessage(BaseModel):
    typ: Literal["zustand"]
    zustand: Optional[PlayerState] = None    # None: spielt nichts mehr


class CommandMessage(BaseModel):
    typ: Literal["befehl"]
    an: str
    aktion: Action
    wert: Any = None


class HandoffMessage(BaseModel):
    typ: Literal["uebergabe"]
    an: str
    paket: Package


class RenameMessage(BaseModel):
    typ: Literal["name"]
    name: str


class ForegroundMessage(BaseModel):
    typ: Literal["aktiv"]


Incoming = Union[StateMessage, CommandMessage, HandoffMessage, RenameMessage, ForegroundMessage]
_incoming = TypeAdapter(Incoming)


class Socket(Protocol):
    async def send_json(self, data: Any) -> None: ...


def clean_name(name: str, fallback: str = "Gerät") -> str:
    name = " ".join((name or "").split())[:MAX_NAME]
    return name or fallback


class Hub:
    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}
        self._sockets: dict[str, Socket] = {}

    def devices(self) -> list[Device]:
        return sorted(self._devices.values(), key=lambda d: d.seit)

    async def join(self, socket: Socket, device_id: str, geraet: str, name: str, art: Kind) -> Device:
        now = time.time()
        device = Device(id=device_id, geraet=geraet, name=clean_name(name), art=art, seit=now, aktiv=now)
        self._devices[device_id] = device      # Neu laden ersetzt die alte Verbindung
        self._sockets[device_id] = socket
        await self._send(device_id, {"typ": "willkommen", "du": device.model_dump(), "geraete": self._listing()})
        await self._broadcast_devices(skip=device_id)
        return device

    async def leave(self, device_id: str, socket: Socket) -> None:
        if self._sockets.get(device_id) is not socket:
            return                              # längst durch eine neuere Verbindung ersetzt
        self._devices.pop(device_id, None)
        self._sockets.pop(device_id, None)
        await self._broadcast_devices()

    async def handle(self, device_id: str, raw: Any) -> None:
        sender = self._devices.get(device_id)
        if not sender:
            return
        try:
            message = _incoming.validate_python(raw)
        except ValidationError as e:
            await self._send(device_id, {"typ": "fehler", "text": "Nachricht nicht verstanden"})
            first = e.errors()[0] if e.errors() else {}
            typ = raw.get("typ") if isinstance(raw, dict) else type(raw).__name__
            logger.warning(f"[Fernsteuerung] {sender.name}: {typ} nicht verstanden "
                           f"({'.'.join(map(str, first.get('loc', ())))}: {first.get('msg', '')})")
            return

        if isinstance(message, StateMessage):
            sender.zustand = message.zustand
            await self._broadcast({"typ": "zustand", "id": device_id,
                                   "zustand": message.zustand.model_dump() if message.zustand else None}, skip=device_id)
        elif isinstance(message, CommandMessage):
            await self._forward(sender, message.an, {"typ": "befehl", "aktion": message.aktion, "wert": message.wert})
        elif isinstance(message, HandoffMessage):
            await self._forward(sender, message.an, {"typ": "uebergabe", "paket": message.paket.model_dump()})
        elif isinstance(message, RenameMessage):
            name = clean_name(message.name, sender.name)
            for device in self._devices.values():      # der Name gilt für alle Fenster des Browsers
                if device.geraet == sender.geraet:
                    device.name = name
            await self._broadcast_devices()
        elif isinstance(message, ForegroundMessage):
            sender.aktiv = time.time()
            await self._broadcast_devices()

    async def _forward(self, sender: Device, target: str, message: dict) -> None:
        if target == sender.id or target not in self._devices:
            await self._send(sender.id, {"typ": "fehler", "text": "Das Gerät ist nicht mehr da"})
            return
        await self._send(target, {**message, "von": sender.id, "von_name": sender.name})

    def _listing(self) -> list[dict]:
        return [d.model_dump() for d in self.devices()]

    async def _broadcast_devices(self, skip: Optional[str] = None) -> None:
        await self._broadcast({"typ": "geraete", "geraete": self._listing()}, skip=skip)

    async def _broadcast(self, message: dict, skip: Optional[str] = None) -> None:
        for device_id in list(self._sockets):
            if device_id != skip:
                await self._send(device_id, message)

    async def _send(self, device_id: str, message: dict) -> bool:
        socket = self._sockets.get(device_id)
        if not socket:
            return False
        try:
            await socket.send_json(message)
            return True
        except Exception:
            # Verbindung abgerissen: das Aufräumen übernimmt leave() beim Schließen
            return False


hub = Hub()
