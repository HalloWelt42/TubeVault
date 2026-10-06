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


def test_bot_sperre_weicht_auf_die_andere_familie_aus(monkeypatch):
    """Sperrt die Quelle eine Adresse als Bot, laufen die Abrufe über die
    andere Familie, bis die Sperrzeit abgelaufen ist - dann wieder über die
    eingestellte. (Befund 06.10.2026: IPv6 gesperrt, IPv4 kam durch.)"""
    now = [1000.0]
    monkeypatch.setattr(source_net.time, "time", lambda: now[0])
    monkeypatch.setattr(source_net, "_blocked_until", {})
    monkeypatch.setenv("TUBEVAULT_SOURCE_IP", "6")
    monkeypatch.setenv("TUBEVAULT_SOURCE_BLOCK_HOURS", "2")

    source_net.report_bot_block()
    assert source_net.bind_address() == "0.0.0.0"
    assert ytdlp_adapter._build_ydl_opts(label="x")["source_address"] == "0.0.0.0"

    now[0] += 3600                                   # auch IPv4 wird gesperrt
    source_net.report_bot_block()
    assert source_net.family() == "6"                # dessen Sperre läuft zuerst ab

    now[0] += 2 * 3600 + 1                           # beide Sperren vorbei
    assert source_net.family() == "6"

    monkeypatch.setenv("TUBEVAULT_SOURCE_IP", "")    # Betriebssystem entscheidet
    source_net.report_bot_block()
    assert source_net.bind_address() is None
