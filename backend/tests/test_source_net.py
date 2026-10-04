"""Netzweg zur Quelle: eine Stelle legt IPv4/IPv6 für alle Abrufe fest."""
from app.utils import source_net, ytdlp_adapter


def test_netzweg_nach_einstellung(monkeypatch):
    monkeypatch.setenv("TUBEVAULT_SOURCE_IP", "6")
    assert source_net.bind_address() == "::"
    assert ytdlp_adapter._build_ydl_opts(label="x")["source_address"] == "::"
    assert source_net.client()._transport._pool._local_address == "::"

    monkeypatch.setenv("TUBEVAULT_SOURCE_IP", "4")
    assert ytdlp_adapter._build_ydl_opts(label="x")["source_address"] == "0.0.0.0"

    monkeypatch.setenv("TUBEVAULT_SOURCE_IP", "")
    assert source_net.bind_address() is None
    assert "source_address" not in ytdlp_adapter._build_ydl_opts(label="x")
