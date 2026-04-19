"""
TubeVault – yt-dlp Adapter v1.3.0
v1.3.0: exportiert aktuell gewählten Throttle-Wert (für Live-Anzeige im UI)
Stellt pytubefix-kompatible Objekte bereit, die intern yt-dlp nutzen.

Damit können alle bestehenden Call-Sites (yt.title, yt.streams, yt.chapters,
yt.captions, Channel.videos, Playlist.videos, Search.videos etc.) unverändert
bleiben, während der Daten-Backend auf yt-dlp umschaltet.

Nicht abgedeckt (bewusst nicht als Adapter):
- stream.download() — Downloads laufen besser direkt über yt-dlp (siehe
  download_service Umstellung in Schritt 5). Stream.url bleibt verfügbar
  für direkten Download-Zugriff.
"""
from __future__ import annotations

import logging
import re
from functools import cached_property
from typing import Iterator, Optional
from urllib.parse import urlparse, parse_qs

import yt_dlp

logger = logging.getLogger(__name__)

# Live-Throttle: KB/s des aktuell laufenden Downloads (0 = kein Limit).
# Wird vom ytdlp-Adapter pro Download gesetzt und vom download_service
# für den WebSocket-Broadcast (Live-Anzeige im UI) ausgelesen.
_CURRENT_THROTTLE_KBPS: int = 0

def get_current_throttle_kbps() -> int:
    return _CURRENT_THROTTLE_KBPS

def _set_current_throttle_kbps(v: int):
    global _CURRENT_THROTTLE_KBPS
    _CURRENT_THROTTLE_KBPS = int(v or 0)


# bgutil-PO-Token-Provider läuft als Docker-Service 'tubevault-pot:4416'
# Override per ENV möglich (z.B. in docker-compose)
import os as _os
_POT_BASE_URL = _os.getenv("POT_PROVIDER_URL", "http://tubevault-pot:4416")

# Optionale Cookies aus config/cookies.txt (Netscape-Format).
# Falls vorhanden, nutzt yt-dlp die eingeloggten Session-Cookies → umgeht
# auch hartnäckige Bot-Blocks (IP-basiert etc.). User legt Datei ins
# Config-Volume oder lädt per API hoch.
def _cookiefile() -> str | None:
    p = "/app/config/cookies.txt"
    return p if _os.path.isfile(p) and _os.path.getsize(p) > 0 else None


# Einmal beim Import loggen: ist POT-Provider erreichbar? sind Cookies da?
def _log_bot_setup():
    import urllib.request, urllib.error
    try:
        req = urllib.request.Request(f"{_POT_BASE_URL}/ping", method="GET")
        with urllib.request.urlopen(req, timeout=3) as r:
            import json as _j
            data = _j.loads(r.read().decode("utf-8", errors="replace"))
            logger.info(f"[BOT-SETUP] POT-Provider erreichbar: v{data.get('version')} "
                        f"(uptime={int(data.get('server_uptime', 0))}s)")
    except Exception as e:
        logger.warning(f"[BOT-SETUP] POT-Provider NICHT erreichbar ({_POT_BASE_URL}): {e}")
    cf = _cookiefile()
    if cf:
        sz = _os.path.getsize(cf)
        logger.info(f"[BOT-SETUP] cookies.txt aktiv: {cf} ({sz} Bytes)")
    else:
        logger.info("[BOT-SETUP] cookies.txt nicht vorhanden – Anon-Mode")

_log_bot_setup()

_YDL_BASE_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noprogress": True,
    "socket_timeout": 20,
    # Bot-Erkennung:
    # - PO-Token Provider (bgutil-http) liefert gültige Tokens für web/mweb/ios.
    # - remote_components ejs:github: laedt das Signature/N-Challenge-Solver
    #   Script von GitHub – freischalten von 1080p+ / AV1 / Opus Formaten.
    # - Clients: default, tv als Fallback (tv braucht kein PO-Token).
    "extractor_args": {
        "youtube": {
            "player_client": ["default", "tv"],
        },
        "youtubepot-bgutilhttp": {
            "base_url": [_POT_BASE_URL],
        },
    },
    "remote_components": ["ejs:github"],
}


def _ydl_extract(url: str, extra_opts: Optional[dict] = None) -> dict:
    """Zentraler yt-dlp Extract-Call."""
    opts = {**_YDL_BASE_OPTS}
    cf = _cookiefile()
    if cf:
        opts["cookiefile"] = cf
    if extra_opts:
        opts.update(extra_opts)
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _vtt_to_srt(vtt_text: str) -> str:
    """Minimal-Konverter WebVTT → SRT."""
    lines = vtt_text.splitlines()
    # WEBVTT-Header + Metadaten-Blöcke entfernen
    out_blocks: list[list[str]] = []
    current: list[str] = []
    seen_header = False
    for line in lines:
        if not seen_header:
            if line.strip().startswith("WEBVTT"):
                seen_header = True
            continue
        if "-->" in line:
            # Zeitformat VTT → SRT (Punkt → Komma)
            line = line.replace(".", ",")
            # Cue-Settings (nach zweitem Timestamp) abschneiden
            m = re.match(r"^(\d\d:\d\d:\d\d,\d\d\d)\s*-->\s*(\d\d:\d\d:\d\d,\d\d\d)", line)
            if m:
                current = [f"{m.group(1)} --> {m.group(2)}"]
                continue
            m2 = re.match(r"^(\d\d:\d\d,\d\d\d)\s*-->\s*(\d\d:\d\d,\d\d\d)", line)
            if m2:
                current = [f"00:{m2.group(1)} --> 00:{m2.group(2)}"]
                continue
            current = [line]
        elif line.strip() == "":
            if current:
                out_blocks.append(current)
                current = []
        else:
            if current:
                current.append(line)
    if current:
        out_blocks.append(current)

    srt = []
    for idx, block in enumerate(out_blocks, start=1):
        if not block:
            continue
        srt.append(str(idx))
        srt.extend(block)
        srt.append("")
    return "\n".join(srt).strip() + "\n"


# ═══════════════════════════════════════════════════════════════════
#  STREAM + STREAM-QUERY
# ═══════════════════════════════════════════════════════════════════

class StreamAdapter:
    """pytubefix.Stream-kompatibel."""

    __slots__ = ("_fmt", "_on_progress", "_watch_url", "_video_duration")

    def __init__(self, fmt: dict, on_progress_callback=None, watch_url: str = "", video_duration: int = 0):
        self._fmt = fmt
        self._video_duration = video_duration
        self._on_progress = on_progress_callback
        self._watch_url = watch_url

    @property
    def itag(self) -> str:
        return str(self._fmt.get("format_id", ""))

    @property
    def mime_type(self) -> str:
        ext = self._fmt.get("ext", "")
        vc = self._fmt.get("vcodec", "none")
        ac = self._fmt.get("acodec", "none")
        if vc != "none":
            return f"video/{ext}"
        if ac != "none":
            return f"audio/{ext}"
        return f"application/{ext}"

    @property
    def subtype(self) -> str:
        return self._fmt.get("ext", "")

    @property
    def type(self) -> str:
        if self._fmt.get("vcodec", "none") != "none":
            return "video"
        if self._fmt.get("acodec", "none") != "none":
            return "audio"
        return "other"

    @property
    def is_progressive(self) -> bool:
        return self._fmt.get("vcodec", "none") != "none" and self._fmt.get("acodec", "none") != "none"

    @property
    def is_adaptive(self) -> bool:
        return not self.is_progressive and (
            self._fmt.get("vcodec", "none") != "none" or self._fmt.get("acodec", "none") != "none"
        )

    @property
    def includes_audio_track(self) -> bool:
        return self._fmt.get("acodec", "none") != "none"

    @property
    def includes_video_track(self) -> bool:
        return self._fmt.get("vcodec", "none") != "none"

    @property
    def resolution(self) -> Optional[str]:
        # pytubefix-kompatibel: "720p" statt "1280x720"
        h = self._fmt.get("height")
        if h:
            return f"{h}p"
        return None

    @property
    def abr(self) -> Optional[str]:
        a = self._fmt.get("abr")
        if a:
            return f"{int(a)}kbps"
        return None

    @property
    def filesize(self) -> int:
        return self._fmt.get("filesize") or self._fmt.get("filesize_approx") or 0

    @property
    def url(self) -> str:
        return self._fmt.get("url", "")

    @property
    def fps(self) -> Optional[int]:
        return self._fmt.get("fps")

    @property
    def codecs(self) -> list[str]:
        """Liste der Codecs analog pytubefix (z.B. ['avc1.640028', 'mp4a.40.2'])."""
        out = []
        vc = self._fmt.get("vcodec")
        if vc and vc != "none":
            out.append(vc)
        ac = self._fmt.get("acodec")
        if ac and ac != "none":
            out.append(ac)
        return out

    def download(
        self,
        output_path: Optional[str] = None,
        filename: Optional[str] = None,
        filename_prefix: Optional[str] = None,
        skip_existing: bool = False,
        timeout: Optional[int] = None,
        max_retries: int = 0,
    ) -> str:
        """Download via yt-dlp (nicht httpx!) — YouTube-Throttling wird intern behandelt.
        Ruft on_progress_callback(stream, chunk, remaining) analog pytubefix.
        """
        import os as _os
        from pathlib import Path as _Path
        import yt_dlp as _ydl

        out_dir = _Path(output_path) if output_path else _Path(".")
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = filename or f"stream_{self.itag}.{self.subtype or 'bin'}"
        if filename_prefix:
            fname = f"{filename_prefix}{fname}"

        # yt-dlp hängt den echten Container-Ext aus dem Format an — wir strippen unseren eigenen,
        # damit keine Doppelungen wie "audio_tmp.m4a.m4a" entstehen.
        fname_base, _fname_ext = _os.path.splitext(fname)
        out_tmpl = str(out_dir / f"{fname_base}.%(ext)s")

        if skip_existing:
            # Trivial-Check: gibt es schon was passendes?
            existing = list(out_dir.glob(f"{fname_base}.*"))
            if existing and existing[0].stat().st_size > 0:
                return str(existing[0])

        cb = self._on_progress
        this = self
        final_path = {"path": None}

        def _hook(d):
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                if total and total != this._fmt.get("filesize"):
                    this._fmt["filesize"] = total
                if cb and total:
                    try:
                        cb(this, b"", max(0, total - done))
                    except Exception:
                        pass
            elif status == "finished":
                final_path["path"] = d.get("filename") or d.get("info_dict", {}).get("filepath")
                if cb:
                    total = d.get("total_bytes") or this.filesize
                    if total:
                        this._fmt["filesize"] = total
                    try:
                        cb(this, b"", 0)
                    except Exception:
                        pass

        url = self._watch_url or self._fmt.get("webpage_url")
        if not url:
            raise RuntimeError("StreamAdapter.download: kein Watch-URL bekannt")

        opts = {
            "format": str(self.itag),
            "outtmpl": out_tmpl,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "progress_hooks": [_hook],
            "retries": max(max_retries, 3),
            "fragment_retries": 10,
            "socket_timeout": timeout or 30,
            "overwrites": True,
            # Kein Post-Processing — wir übernehmen Merge im download_service selbst.
            "postprocessors": [],
            # Bot-Erkennung: default-Clients + tv Fallback + PO-Token + EJS-Solver
            "extractor_args": {
                "youtube": {
                    "player_client": ["default", "tv"],
                },
                "youtubepot-bgutilhttp": {
                    "base_url": [_POT_BASE_URL],
                },
            },
            "remote_components": ["ejs:github"],
        }
        # Optional: cookies.txt aus config-Volume (Option 3 Bot-Umgehung)
        _cf = _cookiefile()
        if _cf:
            opts["cookiefile"] = _cf
        # Throttle-Berechnung via throttle_calc.compute() (pure Funktion, getestet).
        # Liest die 2 Settings direkt aus SQLite (sync, pro Download ok).
        try:
            import sqlite3 as _sq
            from app.config import DB_PATH as _DB
            from app.services.throttle_calc import compute as _throttle_compute
            _c = _sq.connect(str(_DB))
            _rt = _c.execute(
                "SELECT value FROM settings WHERE key='download.throttle_realtime'"
            ).fetchone()
            _kb = _c.execute(
                "SELECT value FROM settings WHERE key='download.throttle_kbps'"
            ).fetchone()
            _c.close()
            realtime = bool(_rt and str(_rt[0]).lower() == 'true')
            fixed_kbps = int(_kb[0]) if _kb and str(_kb[0]).isdigit() else 0

            decision = _throttle_compute(
                realtime=realtime,
                fixed_kbps=fixed_kbps,
                duration_s=self._video_duration or self._fmt.get("duration"),
                filesize_bytes=(self._fmt.get("filesize")
                                or self._fmt.get("filesize_approx")),
                tbr_kbps=self._fmt.get("tbr"),
            )
            if decision.active:
                opts["ratelimit"] = decision.bytes_per_sec
            _set_current_throttle_kbps(decision.kbps)
            logger.info(f"[throttle] applied: {decision.kbps} KB/s ({decision.reason})")
        except Exception as _e:
            logger.warning(f"[throttle] setup failed: {_e}")
        with _ydl.YoutubeDL(opts) as ydl:
            ydl.download([url])

        # Pfad bestimmen: was der Hook gemeldet hat, oder fallback Suchen
        if final_path["path"] and _os.path.exists(final_path["path"]):
            return final_path["path"]
        # Fallback: glob auf unseren Basenamen
        for cand in out_dir.glob(f"{fname_base}.*"):
            if cand.is_file() and cand.stat().st_size > 0:
                return str(cand)
        raise RuntimeError(
            f"StreamAdapter.download: Zieldatei nicht gefunden (outtmpl={out_tmpl})"
        )

    def __repr__(self) -> str:
        return (
            f"<Stream itag={self.itag} type={self.type} "
            f"res={self.resolution} abr={self.abr} progressive={self.is_progressive}>"
        )


class StreamQueryAdapter:
    """pytubefix.StreamQuery-kompatibel."""

    def __init__(self, streams: list[StreamAdapter]):
        self._streams = streams

    def __iter__(self) -> Iterator[StreamAdapter]:
        return iter(self._streams)

    def __len__(self) -> int:
        return len(self._streams)

    def __getitem__(self, i):
        return self._streams[i]

    def filter(
        self,
        *,
        progressive: Optional[bool] = None,
        adaptive: Optional[bool] = None,
        only_audio: Optional[bool] = None,
        only_video: Optional[bool] = None,
        type: Optional[str] = None,
        resolution: Optional[str] = None,
        subtype: Optional[str] = None,
        mime_type: Optional[str] = None,
        abr: Optional[str] = None,
        fps: Optional[int] = None,
    ) -> "StreamQueryAdapter":
        def keep(s: StreamAdapter) -> bool:
            if progressive is True and not s.is_progressive:
                return False
            if progressive is False and s.is_progressive:
                return False
            if adaptive is True and not s.is_adaptive:
                return False
            if adaptive is False and s.is_adaptive:
                return False
            if only_audio is True and (s.includes_video_track or not s.includes_audio_track):
                return False
            if only_video is True and (s.includes_audio_track or not s.includes_video_track):
                return False
            if type and s.type != type:
                return False
            if resolution and s.resolution != resolution:
                return False
            if subtype and s.subtype != subtype:
                return False
            if mime_type and s.mime_type != mime_type:
                return False
            if abr and s.abr != abr:
                return False
            if fps and s.fps != fps:
                return False
            return True

        return StreamQueryAdapter([s for s in self._streams if keep(s)])

    def order_by(self, attr: str) -> "StreamQueryAdapter":
        def key(s: StreamAdapter):
            if attr == "resolution":
                v = s.resolution
                if v and v.endswith("p"):
                    try:
                        return int(v[:-1])
                    except ValueError:
                        return 0
                return 0
            if attr == "abr":
                v = s.abr
                if v and v.endswith("kbps"):
                    try:
                        return int(v[:-4])
                    except ValueError:
                        return 0
                return 0
            if attr == "fps":
                return s.fps or 0
            if attr == "filesize":
                return s.filesize
            return getattr(s, attr, 0) or 0

        return StreamQueryAdapter(sorted(self._streams, key=key))

    def desc(self) -> "StreamQueryAdapter":
        return StreamQueryAdapter(list(reversed(self._streams)))

    def asc(self) -> "StreamQueryAdapter":
        return self

    def first(self) -> Optional[StreamAdapter]:
        return self._streams[0] if self._streams else None

    def last(self) -> Optional[StreamAdapter]:
        return self._streams[-1] if self._streams else None

    def get_by_itag(self, itag) -> Optional[StreamAdapter]:
        itag = str(itag)
        for s in self._streams:
            if s.itag == itag:
                return s
        return None

    def get_audio_only(self, subtype: Optional[str] = None) -> Optional[StreamAdapter]:
        q = self.filter(only_audio=True)
        if subtype:
            q = q.filter(subtype=subtype)
        best = q.order_by("abr").desc().first()
        return best

    def get_highest_resolution(self) -> Optional[StreamAdapter]:
        # Bevorzugt progressiv (kein Merge nötig); sonst höchste adaptive Video-Res
        prog = self.filter(progressive=True).order_by("resolution").desc().first()
        if prog:
            return prog
        return self.filter(only_video=True).order_by("resolution").desc().first()

    def get_lowest_resolution(self) -> Optional[StreamAdapter]:
        return self.filter(progressive=True).order_by("resolution").asc().first()


# ═══════════════════════════════════════════════════════════════════
#  CHAPTER + CAPTION
# ═══════════════════════════════════════════════════════════════════

class ChapterAdapter:
    """pytubefix.Chapter-kompatibel."""

    __slots__ = ("title", "start_seconds", "duration")

    def __init__(self, title: str, start_seconds: int, duration: int):
        self.title = title
        self.start_seconds = start_seconds
        self.duration = duration

    @property
    def end_seconds(self) -> int:
        return self.start_seconds + self.duration


class CaptionAdapter:
    """pytubefix.Caption-kompatibel."""

    def __init__(self, code: str, name: str, url: str, ext: str):
        self.code = code
        self.name = name
        self._url = url
        self._ext = ext

    def generate_srt_captions(self) -> str:
        import httpx
        r = httpx.get(self._url, timeout=20)
        r.raise_for_status()
        text = r.text
        if self._ext in ("vtt", "webvtt"):
            return _vtt_to_srt(text)
        if self._ext == "srt":
            return text
        # Fallback: wenn es wie VTT aussieht, konvertieren; sonst wie es ist
        if text.lstrip().startswith("WEBVTT"):
            return _vtt_to_srt(text)
        return text


# ═══════════════════════════════════════════════════════════════════
#  YOUTUBE (Video)
# ═══════════════════════════════════════════════════════════════════

class YoutubeAdapter:
    """pytubefix.YouTube-kompatibel."""

    def __init__(self, url: str, on_progress_callback=None, **_kwargs):
        self.watch_url = url
        self.video_id = _extract_video_id(url) or ""
        self.on_progress_callback = on_progress_callback
        self._info: Optional[dict] = None

    def _ensure(self) -> dict:
        if self._info is None:
            self._info = _ydl_extract(self.watch_url)
        return self._info

    # Metadaten
    @property
    def title(self) -> str:
        return self._ensure().get("title") or ""

    @property
    def author(self) -> str:
        return self._ensure().get("uploader") or self._ensure().get("channel") or ""

    @property
    def channel_id(self) -> str:
        return self._ensure().get("channel_id") or ""

    @property
    def channel_url(self) -> str:
        return self._ensure().get("channel_url") or ""

    @property
    def description(self) -> str:
        return self._ensure().get("description") or ""

    @property
    def length(self) -> int:
        return int(self._ensure().get("duration") or 0)

    @property
    def views(self) -> int:
        return int(self._ensure().get("view_count") or 0)

    @property
    def keywords(self) -> list[str]:
        return list(self._ensure().get("tags") or [])

    @property
    def thumbnail_url(self) -> str:
        return self._ensure().get("thumbnail") or ""

    @property
    def publish_date(self):
        import datetime as _dt
        raw = self._ensure().get("upload_date")
        if not raw:
            return None
        try:
            return _dt.datetime.strptime(raw, "%Y%m%d")
        except ValueError:
            return None

    # vid_info-Shim für Altcode, der videoDetails/playabilityStatus liest
    @property
    def vid_info(self) -> dict:
        info = self._ensure()
        is_live = bool(info.get("is_live"))
        was_live = bool(info.get("was_live"))
        return {
            "videoDetails": {
                "videoId": self.video_id,
                "title": info.get("title") or "",
                "author": info.get("uploader") or "",
                "channelId": info.get("channel_id") or "",
                "lengthSeconds": str(info.get("duration") or 0),
                "viewCount": str(info.get("view_count") or 0),
                "shortDescription": info.get("description") or "",
                "keywords": list(info.get("tags") or []),
                "isLive": is_live,
                "isLiveContent": is_live or was_live,
                "isPostLiveDvr": False,
            },
            "playabilityStatus": {
                "status": "OK",
                "playableInEmbed": True,
            },
            # extra für Debug
            "_ytdlp_raw": info,
        }

    # Streams
    @property
    def streams(self) -> StreamQueryAdapter:
        info = self._ensure()
        fmts = info.get("formats") or []
        # Nur Formate mit URL (manche sind nur Platzhalter)
        fmts = [f for f in fmts if f.get("url")]
        # Storyboards/Bilder raus (sb*)
        fmts = [f for f in fmts if f.get("ext") not in ("mhtml",)]
        video_duration = int(info.get("duration") or 0)
        return StreamQueryAdapter([
            StreamAdapter(
                f,
                on_progress_callback=self.on_progress_callback,
                watch_url=self.watch_url,
                video_duration=video_duration,
            )
            for f in fmts
        ])

    # Chapters
    @property
    def chapters(self) -> list[ChapterAdapter]:
        info = self._ensure()
        out: list[ChapterAdapter] = []
        for c in info.get("chapters") or []:
            start = int(c.get("start_time") or 0)
            end = int(c.get("end_time") or start)
            out.append(ChapterAdapter(
                title=c.get("title") or "",
                start_seconds=start,
                duration=max(0, end - start),
            ))
        return out

    # Captions
    @property
    def captions(self) -> list[CaptionAdapter]:
        info = self._ensure()
        out: list[CaptionAdapter] = []
        for lang, variants in (info.get("subtitles") or {}).items():
            fmt = _pick_sub_format(variants)
            if fmt:
                out.append(CaptionAdapter(
                    code=lang,
                    name=fmt.get("name") or lang,
                    url=fmt.get("url"),
                    ext=fmt.get("ext", ""),
                ))
        for lang, variants in (info.get("automatic_captions") or {}).items():
            if lang in (info.get("subtitles") or {}):
                continue  # manuelle haben Vorrang
            fmt = _pick_sub_format(variants)
            if fmt:
                out.append(CaptionAdapter(
                    code=f"a.{lang}",
                    name=fmt.get("name") or f"{lang} (auto)",
                    url=fmt.get("url"),
                    ext=fmt.get("ext", ""),
                ))
        return out


def _pick_sub_format(variants: list[dict]) -> Optional[dict]:
    """Bevorzugte Subtitle-Format-Auswahl: vtt > srt > json3 > srv3 > rest."""
    pref = ["vtt", "srt", "json3", "srv3", "srv2", "srv1"]
    by_ext = {v.get("ext"): v for v in variants if v.get("url")}
    for p in pref:
        if p in by_ext:
            return by_ext[p]
    return next(iter(by_ext.values()), None)


def _extract_video_id(url: str) -> Optional[str]:
    try:
        u = urlparse(url)
        if u.netloc in ("youtu.be",):
            return u.path.lstrip("/").split("/")[0] or None
        if "youtube.com" in u.netloc:
            if u.path == "/watch":
                q = parse_qs(u.query)
                return (q.get("v") or [None])[0]
            if u.path.startswith("/shorts/"):
                return u.path.split("/")[2]
            if u.path.startswith("/embed/") or u.path.startswith("/v/"):
                return u.path.split("/")[2]
    except Exception:
        return None
    # Fallback: direkte ID
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url or ""):
        return url
    return None


# ═══════════════════════════════════════════════════════════════════
#  CHANNEL / PLAYLIST-VIDEO-ITEMS
# ═══════════════════════════════════════════════════════════════════

class ChannelVideoItem:
    """Leichtgewichtiger Video-Eintrag aus einer Channel/Playlist-Liste (flat)."""

    __slots__ = ("video_id", "title", "author", "channel_id", "length",
                 "views", "thumbnail_url", "publish_date", "watch_url")

    def __init__(self, entry: dict, fallback_channel: Optional[dict] = None):
        self.video_id = entry.get("id") or ""
        self.title = entry.get("title") or ""
        self.author = entry.get("uploader") or (fallback_channel or {}).get("channel") or ""
        self.channel_id = entry.get("channel_id") or (fallback_channel or {}).get("channel_id") or ""
        self.length = int(entry.get("duration") or 0)
        self.views = int(entry.get("view_count") or 0)
        thumbs = entry.get("thumbnails") or []
        self.thumbnail_url = (thumbs[-1].get("url") if thumbs else None) or (
            f"https://i.ytimg.com/vi/{self.video_id}/hqdefault.jpg" if self.video_id else ""
        )
        self.publish_date = entry.get("upload_date")
        self.watch_url = entry.get("url") or entry.get("webpage_url") or (
            f"https://www.youtube.com/watch?v={self.video_id}" if self.video_id else ""
        )


# ═══════════════════════════════════════════════════════════════════
#  CHANNEL
# ═══════════════════════════════════════════════════════════════════

class ChannelAdapter:
    """pytubefix.Channel-kompatibel. Lazy; Videos als Generator."""

    def __init__(self, url: str, *, max_videos: Optional[int] = None, **_kwargs):
        self.channel_url = url
        self._max_videos = max_videos
        self._meta: Optional[dict] = None

    def _ensure_meta(self) -> dict:
        if self._meta is None:
            # Light-Abruf: nur Channel-Grunddaten + flat Video-Liste
            opts = {"extract_flat": "in_playlist"}
            if self._max_videos:
                opts["playlistend"] = self._max_videos
            self._meta = _ydl_extract(
                _channel_videos_url(self.channel_url), extra_opts=opts
            )
        return self._meta

    @property
    def channel_id(self) -> str:
        return self._ensure_meta().get("channel_id") or ""

    @property
    def channel_name(self) -> str:
        return (
            self._ensure_meta().get("channel")
            or self._ensure_meta().get("uploader")
            or self._ensure_meta().get("title")
            or ""
        )

    @property
    def vanity_url(self) -> Optional[str]:
        return self._ensure_meta().get("uploader_url")

    @property
    def thumbnail_url(self) -> str:
        thumbs = self._ensure_meta().get("thumbnails") or []
        return thumbs[-1]["url"] if thumbs else ""

    @property
    def description(self) -> str:
        return self._ensure_meta().get("description") or ""

    @property
    def videos(self) -> Iterator[ChannelVideoItem]:
        meta = self._ensure_meta()
        fallback = {"channel": meta.get("channel"), "channel_id": meta.get("channel_id")}
        for e in (meta.get("entries") or []):
            if not e:
                continue
            yield ChannelVideoItem(e, fallback_channel=fallback)

    @property
    def video_urls(self) -> list[str]:
        return [v.watch_url for v in self.videos]

    @property
    def playlists(self) -> Iterator["PlaylistSummary"]:
        # Separate Abfrage auf /playlists
        url = _channel_subpage_url(self.channel_url, "playlists")
        try:
            info = _ydl_extract(url, extra_opts={"extract_flat": "in_playlist"})
        except Exception as e:
            logger.warning(f"ChannelAdapter.playlists: {e}")
            return
        for e in (info.get("entries") or []):
            if not e:
                continue
            yield PlaylistSummary(e)

    # initial_data-Shim — nur soweit Altcode drauf zugreift
    @property
    def initial_data(self) -> dict:
        return {"metadata": {"channelMetadataRenderer": {
            "title": self.channel_name,
            "description": self.description,
            "externalId": self.channel_id,
            "avatar": {"thumbnails": [{"url": self.thumbnail_url}]} if self.thumbnail_url else {},
        }}}


class PlaylistSummary:
    __slots__ = ("title", "playlist_id", "playlist_url")

    def __init__(self, entry: dict):
        self.title = entry.get("title") or ""
        self.playlist_id = entry.get("id") or ""
        self.playlist_url = entry.get("url") or (
            f"https://www.youtube.com/playlist?list={self.playlist_id}" if self.playlist_id else ""
        )


def _channel_videos_url(url: str) -> str:
    """Stellt sicher, dass wir /videos-Seite abfragen."""
    if url.rstrip("/").endswith("/videos"):
        return url
    if "/playlist" in url or "list=" in url:
        return url
    return url.rstrip("/") + "/videos"


def _channel_subpage_url(url: str, sub: str) -> str:
    base = url.rstrip("/")
    for suffix in ("/videos", "/shorts", "/streams", "/playlists", "/about"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return f"{base}/{sub}"


# ═══════════════════════════════════════════════════════════════════
#  PLAYLIST
# ═══════════════════════════════════════════════════════════════════

class PlaylistAdapter:
    """pytubefix.Playlist-kompatibel."""

    def __init__(self, url: str, *, max_videos: Optional[int] = None, **_kwargs):
        self.playlist_url = url
        self._max_videos = max_videos
        self._info: Optional[dict] = None

    def _ensure(self) -> dict:
        if self._info is None:
            opts = {"extract_flat": "in_playlist"}
            if self._max_videos:
                opts["playlistend"] = self._max_videos
            self._info = _ydl_extract(self.playlist_url, extra_opts=opts)
        return self._info

    @property
    def playlist_id(self) -> str:
        info = self._ensure()
        pid = info.get("id") or ""
        # Falls wir auf /watch mit list= sind
        if not pid:
            try:
                q = parse_qs(urlparse(self.playlist_url).query)
                pid = (q.get("list") or [""])[0]
            except Exception:
                pass
        return pid

    @property
    def title(self) -> str:
        return self._ensure().get("title") or ""

    @property
    def description(self) -> str:
        return self._ensure().get("description") or ""

    @property
    def owner(self) -> str:
        return self._ensure().get("uploader") or self._ensure().get("channel") or ""

    @property
    def owner_id(self) -> str:
        return self._ensure().get("channel_id") or self._ensure().get("uploader_id") or ""

    @property
    def length(self) -> int:
        info = self._ensure()
        return int(info.get("playlist_count") or len(info.get("entries") or []))

    @property
    def videos(self) -> Iterator[ChannelVideoItem]:
        info = self._ensure()
        fallback = {"channel": info.get("uploader"), "channel_id": info.get("channel_id")}
        for e in (info.get("entries") or []):
            if not e:
                continue
            yield ChannelVideoItem(e, fallback_channel=fallback)

    @property
    def video_urls(self) -> list[str]:
        return [v.watch_url for v in self.videos]

    # _html_data-Shim (Altcode in search.py greift auf title-Fallback zu)
    @property
    def _html_data(self) -> dict:
        return {"title": {"runs": [{"text": self.title}]}}


# ═══════════════════════════════════════════════════════════════════
#  SEARCH
# ═══════════════════════════════════════════════════════════════════

class SearchAdapter:
    """pytubefix.Search-kompatibel.

    yt-dlp 'ytsearchN:query' liefert nur Videos (keine kategorisierte Aufteilung
    in Playlists/Channels wie bei YouTube-UI). Wir extrahieren:
      - videos: direkt aus entries
      - shorts: Videos mit duration ≤ 60s
      - playlists/channels: leere Liste (yt-dlp kann das über ytsearch nicht)

    Für pytubefix-Kompatibilität gibt es die Singular-Aliase playlist/channel/
    completion_suggestions zusätzlich — damit der bestehende Router-Code
    (s.playlist[:6], s.channel[:4]) nicht in AttributeError läuft.
    """

    def __init__(self, query: str, *, max_results: int = 25, **_kwargs):
        self.query = query
        self._max = max_results
        self._info: Optional[dict] = None

    def _ensure(self) -> dict:
        if self._info is None:
            self._info = _ydl_extract(
                f"ytsearch{self._max}:{self.query}",
                extra_opts={"extract_flat": True},
            )
        return self._info

    # ── Video-Kategorien (aus ytsearch) ─────────────────────────────
    # videos enthält ALLE Treffer (auch Shorts) — damit UIs, die nur
    # 'videos' lesen, keine Shorts verlieren. shorts ist die Untermenge
    # mit duration ≤ 60s, für UIs die beides getrennt anzeigen wollen.

    @property
    def videos(self) -> list[ChannelVideoItem]:
        entries = self._ensure().get("entries") or []
        return [ChannelVideoItem(e) for e in entries if e and e.get("id")]

    @property
    def shorts(self) -> list[ChannelVideoItem]:
        return [v for v in self.videos if 0 < v.length <= 60]

    # ── Playlists / Channels: nicht verfügbar über ytsearch ─────────

    @property
    def playlists(self) -> list[PlaylistSummary]:
        # yt-dlp ytsearch liefert keine Playlist-Entries — wäre separater
        # Call nötig (YouTube-Search-URL mit sp=Filter). Bleibt leer bis
        # echter Bedarf.
        return []

    @property
    def channels(self) -> list:
        return []

    @property
    def suggestions(self) -> list[str]:
        return []

    # ── pytubefix-Kompat: Singular-Aliase ───────────────────────────
    # Alter Router-Code (search.py) nutzt s.playlist / s.channel /
    # s.completion_suggestions (pytubefix-Namen). Wir mappen auf unsere
    # Plural-Properties, damit try/except nicht mehr alle Fehler schluckt.

    @property
    def playlist(self) -> list[PlaylistSummary]:
        return self.playlists

    @property
    def channel(self) -> list:
        return self.channels

    @property
    def completion_suggestions(self) -> list[str]:
        return self.suggestions
