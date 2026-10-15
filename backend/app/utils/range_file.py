"""
TubeVault – Datei mit Range-Anfragen ausliefern

Video- und Tonspieler springen per "Range: bytes=..." in eine Datei. Diese
eine Stelle liefert Teilstücke (206) oder die ganze Datei; Videos und
Musikdateien nutzen sie gemeinsam.
"""
import mimetypes
import os

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

CHUNK_SIZE = 1024 * 1024  # 1MB


def _read(path: str, start: int, length: int):
    with open(path, "rb") as f:
        f.seek(start)
        remaining = length
        while remaining > 0:
            chunk = f.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def range_response(path: str, request: Request, media_type: str | None = None,
                   fallback_type: str = "application/octet-stream") -> StreamingResponse:
    size = os.path.getsize(path)
    media_type = media_type or mimetypes.guess_type(path)[0] or fallback_type
    header = request.headers.get("range")
    if not header:
        return StreamingResponse(_read(path, 0, size), media_type=media_type,
                                 headers={"Content-Length": str(size), "Accept-Ranges": "bytes"})
    first, _, last = header.replace("bytes=", "").partition("-")
    start = int(first) if first else 0
    end = min(int(last) if last else size - 1, size - 1)
    if start >= size:
        raise HTTPException(status_code=416, detail="Range Not Satisfiable")
    length = end - start + 1
    return StreamingResponse(_read(path, start, length), status_code=206, media_type=media_type, headers={
        "Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(length),
        "Accept-Ranges": "bytes", "Cache-Control": "no-cache"})
