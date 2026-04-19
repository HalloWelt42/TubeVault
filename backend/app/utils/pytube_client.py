"""
TubeVault – Zentraler YouTube-Backend-Client v2.0.0

Einheitlicher YouTube/Channel/Playlist/Search-Entrypoint mit umschaltbarem
Backend: yt-dlp (Default) oder pytubefix (Legacy-Fallback).

Backend wird per Env YT_BACKEND=ytdlp|pytubefix gewählt (Default: ytdlp).
Pytubefix-Client (falls Legacy) per PYTUBE_CLIENT (Default: MWEB).

Alle Call-Sites nutzen nur die vier Factory-Funktionen unten — dadurch
kann man Backends jederzeit ohne Code-Änderung umschalten.
"""
import logging
import os

logger = logging.getLogger(__name__)

YT_BACKEND = os.getenv("YT_BACKEND", "ytdlp").lower()
PYTUBE_CLIENT = os.getenv("PYTUBE_CLIENT", "MWEB")

logger.info(f"pytube_client: backend={YT_BACKEND}")


def _ytdlp():
    from app.utils.ytdlp_adapter import (
        YoutubeAdapter, ChannelAdapter, PlaylistAdapter, SearchAdapter,
    )
    return YoutubeAdapter, ChannelAdapter, PlaylistAdapter, SearchAdapter


def _pytubefix():
    from pytubefix import YouTube, Channel, Playlist, Search
    return YouTube, Channel, Playlist, Search


def make_youtube(url: str, **kwargs):
    if YT_BACKEND == "pytubefix":
        YouTube, _, _, _ = _pytubefix()
        kwargs.setdefault("client", PYTUBE_CLIENT)
        return YouTube(url, **kwargs)
    YoutubeAdapter, _, _, _ = _ytdlp()
    return YoutubeAdapter(url, **kwargs)


def make_channel(url: str, **kwargs):
    if YT_BACKEND == "pytubefix":
        _, Channel, _, _ = _pytubefix()
        kwargs.setdefault("client", PYTUBE_CLIENT)
        return Channel(url, **kwargs)
    _, ChannelAdapter, _, _ = _ytdlp()
    return ChannelAdapter(url, **kwargs)


def make_playlist(url: str, **kwargs):
    if YT_BACKEND == "pytubefix":
        _, _, Playlist, _ = _pytubefix()
        kwargs.setdefault("client", PYTUBE_CLIENT)
        return Playlist(url, **kwargs)
    _, _, PlaylistAdapter, _ = _ytdlp()
    return PlaylistAdapter(url, **kwargs)


def make_search(query: str, **kwargs):
    if YT_BACKEND == "pytubefix":
        _, _, _, Search = _pytubefix()
        kwargs.setdefault("client", PYTUBE_CLIENT)
        return Search(query, **kwargs)
    _, _, _, SearchAdapter = _ytdlp()
    return SearchAdapter(query, **kwargs)
