"""
TubeVault – Ungescannte Kanäle von selbst vollständig erfassen

Ein abonnierter Kanal, der noch nie vollständig gelesen wurde
(subscriptions.last_scanned leer), hat keine Medaille und keinen Überblick
über seine Lücken. Diese Arbeit liest solche Kanäle nach und nach selbst
(Wunsch 15.10.2026): höchstens einen alle zwei Stunden, bis keiner mehr übrig
ist - schonend für die Quelle.

Angehalten ist der Standard (Einstellung scan.auto_enabled); fortgesetzt wird
in der Liste der Hintergrundarbeiten. Die eine Wahrheit über den Takt ist
subscriptions.auto_scan_at: wann ein Kanal zuletzt von hier angestoßen wurde.
Ein Kanal, dessen Scan scheitert, kommt erst wieder dran, wenn alle anderen
einmal versucht wurden.
"""
import asyncio
import logging
from typing import Optional

from app.database import db
from app.services import setting_values

logger = logging.getLogger(__name__)

SWITCH = "scan.auto_enabled"
INTERVAL_S = 2 * 3600       # höchstens ein Kanal je zwei Stunden
CHECK_EVERY_S = 60          # so oft schaut die Schleife, ob es Zeit ist
START_DELAY_S = 180         # nach dem Start erst das System hochkommen lassen

_UNSCANNED = "last_scanned IS NULL AND COALESCE(enabled, 1) = 1"
_running: Optional[str] = None      # Name des Kanals, der gerade gelesen wird


async def install_schema(connection) -> None:
    try:
        await connection.execute("ALTER TABLE subscriptions ADD COLUMN auto_scan_at TEXT")
    except Exception:
        pass  # Spalte existiert bereits
    await connection.commit()


async def pending() -> int:
    return await db.fetch_val(f"SELECT COUNT(*) FROM subscriptions WHERE {_UNSCANNED}") or 0


async def total() -> int:
    return await db.fetch_val("SELECT COUNT(*) FROM subscriptions WHERE COALESCE(enabled, 1) = 1") or 0


async def next_channel() -> Optional[dict]:
    """Der nächste ungescannte Kanal: nie versuchte zuerst, dann der am längsten nicht versuchte."""
    row = await db.fetch_one(
        f"""SELECT channel_id, channel_name FROM subscriptions WHERE {_UNSCANNED}
            ORDER BY auto_scan_at IS NOT NULL, auto_scan_at, id LIMIT 1""")
    return dict(row) if row else None


async def seconds_until_due() -> int:
    """0: jetzt darf der nächste Kanal gelesen werden; sonst die Wartezeit in Sekunden."""
    elapsed = await db.fetch_val(
        "SELECT CAST(strftime('%s', 'now') - strftime('%s', MAX(auto_scan_at)) AS INTEGER) FROM subscriptions")
    if elapsed is None:
        return 0
    return max(0, INTERVAL_S - int(elapsed))


def running() -> Optional[str]:
    return _running


async def run_due() -> Optional[str]:
    """Einen Kanal lesen, wenn es eingeschaltet und an der Zeit ist; liefert dessen Namen."""
    global _running
    from app.services.job_service import job_service
    from app.services.rss_service import rss_service

    if _running or not await setting_values.is_on(SWITCH):
        return None
    if await seconds_until_due() > 0 or job_service.is_exclusive_running():
        return None
    channel = await next_channel()
    if not channel:
        return None
    name = channel["channel_name"] or channel["channel_id"]
    await db.execute("UPDATE subscriptions SET auto_scan_at = datetime('now') WHERE channel_id = ?",
                     (channel["channel_id"],))
    job = await job_service.create(
        job_type="channel_scan", title=f"Kanal-Scan: {name}",
        description=f"Ungescannten Kanal vollständig erfassen: {name}",
        metadata={"channel_id": channel["channel_id"], "trigger": "auto"})
    _running = name
    try:
        await rss_service.fetch_all_channel_videos(channel["channel_id"], job_id=job["id"])
    except Exception as e:
        logger.warning(f"[KANALSCAN] {name}: {e}")
        current = await job_service.get(job["id"])
        if current and current["status"] in ("queued", "active"):
            await job_service.fail(job["id"], str(e)[:300])
    finally:
        _running = None
    return name


async def loop() -> None:
    await asyncio.sleep(START_DELAY_S)
    logger.info("[KANALSCAN] Bereit: liest ungescannte Kanäle, höchstens einen alle 2 Stunden (wenn eingeschaltet)")
    while True:
        try:
            name = await run_due()
            if name:
                logger.info(f"[KANALSCAN] {name} gelesen, noch {await pending()} ungescannt")
        except Exception as e:
            logger.error(f"[KANALSCAN] Fehler: {e}", exc_info=True)
        await asyncio.sleep(CHECK_EVERY_S)
