"""
TubeVault – Thumbnail AI Service v1.6.21
© HalloWelt42 – Private Nutzung

Analysiert Video-Thumbnails per LM Studio Vision-Modell (Mac).
Erkennt: video_type (video/short/live), Kategorie-Vorschläge, Beschreibung.
Basiert auf ImageVault ai_worker Architektur.
"""

import asyncio
import base64
import io
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from app.database import db

logger = logging.getLogger("tubevault.thumbnail_ai")

# ─── Prompt für Vision-Modell ───────────────────────────────
DEFAULT_PROMPT = """Klassifiziere dieses YouTube-Video anhand des Thumbnails. Antworte NUR mit JSON:

{"video_type": "video", "confidence": 0.95}

video_type ist "video" oder "short":
- "short": Typische Short-Indikatoren wie TikTok-Stil, einzelne Person nah, simpler Hintergrund, große Text-Overlays, Meme-Stil, Reaction-Clip, kurzer Gag
- "video": Normales YouTube-Video (Standard) — Tutorials, Gameplay, Vlogs, Musikvideos, Dokumentationen, Reviews

Im Zweifel immer "video". NUR das JSON."""


class ThumbnailAiService:
    """Thumbnail-Analyse per LM Studio Vision-Modell."""

    def __init__(self):
        self.config = {
            "lm_studio_url": "http://192.168.178.65:1234",
            "model": "",  # Leer = automatisch erstes Modell
            "enabled": False,
            "auto_analyze": False,
            "batch_size": 5,
            "interval_seconds": 15,
            "max_image_size": 512,
            "max_tokens": 2048,
            "temperature": 0.2,
        }
        self.status = {
            "connected": False,
            "model": "",
            "available_models": [],
            "processing": False,
            "current_video_id": None,
            "current_title": None,
            "queue_count": 0,
            "batch_total": 0,
            "batch_done": 0,
            "total_analyzed": 0,
            "total_errors": 0,
            "total_type_changes": 0,
            "last_error": "",
            "last_check": "",
            "tokens_per_second": 0,
        }
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._log: list[dict] = []  # Letzte 200 Einträge

    # ─── Config ──────────────────────────────────────────

    async def load_config(self):
        """Config aus DB laden."""
        row = await db.fetch_one(
            "SELECT value FROM settings WHERE key = 'thumbnail_ai_config'"
        )
        if row:
            try:
                saved = json.loads(row["value"])
                self.config.update(saved)
            except (json.JSONDecodeError, TypeError):
                pass

    async def save_config(self, updates: dict):
        """Config in DB speichern."""
        self.config.update(updates)
        value = json.dumps(self.config)
        existing = await db.fetch_one(
            "SELECT key FROM settings WHERE key = 'thumbnail_ai_config'"
        )
        if existing:
            await db.execute(
                "UPDATE settings SET value = ? WHERE key = 'thumbnail_ai_config'",
                (value,)
            )
        else:
            await db.execute(
                "INSERT INTO settings (key, value, category) VALUES ('thumbnail_ai_config', ?, 'ai')",
                (value,)
            )
        return self.config

    # ─── Prompt ──────────────────────────────────────────

    async def get_prompt(self) -> str:
        """Aktuellen Prompt laden (DB oder Default)."""
        row = await db.fetch_one(
            "SELECT value FROM settings WHERE key = 'thumbnail_ai_prompt'"
        )
        if row and row["value"]:
            return row["value"]
        return DEFAULT_PROMPT

    async def save_prompt(self, prompt: str) -> str:
        """Benutzerdefinierten Prompt speichern."""
        existing = await db.fetch_one(
            "SELECT key FROM settings WHERE key = 'thumbnail_ai_prompt'"
        )
        if existing:
            await db.execute(
                "UPDATE settings SET value = ? WHERE key = 'thumbnail_ai_prompt'",
                (prompt,)
            )
        else:
            await db.execute(
                "INSERT INTO settings (key, value, category) VALUES ('thumbnail_ai_prompt', ?, 'ai')",
                (prompt,)
            )
        self._add_log("info", f"Prompt aktualisiert ({len(prompt)} Zeichen)")
        return prompt

    async def reset_prompt(self) -> str:
        """Prompt auf Default zurücksetzen."""
        await db.execute(
            "DELETE FROM settings WHERE key = 'thumbnail_ai_prompt'"
        )
        self._add_log("info", "Prompt auf Default zurückgesetzt")
        return DEFAULT_PROMPT

    # ─── Logging ─────────────────────────────────────────

    def _add_log(self, level: str, msg: str, details: dict = None):
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "msg": msg,
            "details": details,
        }
        self._log.append(entry)
        if len(self._log) > 200:
            self._log = self._log[-200:]

        if level == "error":
            logger.error(f"[Thumbnail-AI] {msg}")
            self.status["last_error"] = msg
        else:
            logger.info(f"[Thumbnail-AI] {msg}")

    def get_log(self, limit: int = 50) -> list[dict]:
        return self._log[-limit:]

    # ─── LM Studio Verbindung ────────────────────────────

    async def check_connection(self) -> dict:
        """Prüft Verbindung zu LM Studio und gibt Modell-Info zurück."""
        url = self.config["lm_studio_url"].rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{url}/v1/models")
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("data", [])
                    model_ids = [m.get("id", "?") for m in models]
                    self.status["available_models"] = model_ids
                    if models:
                        # Konfiguriertes Modell nutzen, falls vorhanden
                        chosen = self.config.get("model", "")
                        if chosen and chosen in model_ids:
                            active = chosen
                        else:
                            active = model_ids[0]
                        self.status["connected"] = True
                        self.status["model"] = active
                        self.status["last_check"] = datetime.now(timezone.utc).isoformat()
                        return {"connected": True, "model": active, "models": model_ids}

            self.status["connected"] = False
            self.status["model"] = ""
            self.status["available_models"] = []
            return {"connected": False, "error": "Kein Modell geladen"}
        except Exception as e:
            self.status["connected"] = False
            self.status["model"] = ""
            self.status["available_models"] = []
            return {"connected": False, "error": str(e)}

    # ─── Thumbnail laden + Base64 ────────────────────────

    async def _get_thumbnail_base64(self, video_id: str) -> Optional[str]:
        """Thumbnail laden, auf max_image_size skalieren, als Base64 zurückgeben."""
        from app.config import THUMBNAILS_DIR, RSS_THUMBS_DIR
        from PIL import Image
        from io import BytesIO

        raw_data = None

        # 1) DB: gespeicherter thumbnail_path
        row = await db.fetch_one(
            "SELECT thumbnail_path FROM videos WHERE id = ?", (video_id,)
        )
        if row and row["thumbnail_path"]:
            p = row["thumbnail_path"]
            if os.path.exists(p):
                try:
                    with open(p, "rb") as f:
                        raw_data = f.read()
                except Exception:
                    pass

        # 2) Lokaler Thumbnail-Ordner
        if not raw_data:
            for d in [str(THUMBNAILS_DIR), str(RSS_THUMBS_DIR)]:
                for ext in (".jpg", ".webp", ".png"):
                    path = os.path.join(d, f"{video_id}{ext}")
                    if os.path.exists(path):
                        try:
                            with open(path, "rb") as f:
                                raw_data = f.read()
                            break
                        except Exception:
                            pass
                if raw_data:
                    break

        # 3) Remote YouTube Thumbnail
        if not raw_data:
            urls = [
                f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
            ]
            async with httpx.AsyncClient(timeout=10) as client:
                for url in urls:
                    try:
                        resp = await client.get(url)
                        if resp.status_code == 200 and len(resp.content) > 1000:
                            raw_data = resp.content
                            break
                    except Exception:
                        pass

        if not raw_data:
            return None

        # Resize auf max_image_size (Breite)
        max_w = self.config.get("max_image_size", 512)
        try:
            img = Image.open(BytesIO(raw_data))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            if img.width > max_w:
                ratio = max_w / img.width
                new_h = int(img.height * ratio)
                img = img.resize((max_w, new_h), Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=80)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            # Fallback: Originalbild ohne Resize
            return base64.b64encode(raw_data).decode()

    # ─── Einzelne Analyse ────────────────────────────────

    async def analyze_video(self, video_id: str) -> dict:
        """Ein Video-Thumbnail analysieren. Gibt Ergebnis zurück."""
        title = await self._get_video_title(video_id)
        self.status["processing"] = True
        self.status["current_video_id"] = video_id
        self.status["current_title"] = title

        try:
            # Thumbnail laden
            thumb_b64 = await self._get_thumbnail_base64(video_id)
            if not thumb_b64:
                self._add_log("error", f"✗ Kein Thumbnail: {title}")
                self.status["total_errors"] += 1
                await self._mark_failed(video_id, "Kein Thumbnail")
                self.status["batch_done"] += 1
                return {"error": f"Kein Thumbnail für {video_id}"}

            # LM Studio Anfrage
            url = self.config["lm_studio_url"].rstrip("/")
            model = self.status.get("model") or self.config.get("model") or "default"
            prompt = await self.get_prompt()

            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{thumb_b64}"
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                "max_tokens": self.config["max_tokens"],
                "temperature": self.config["temperature"],
                "stream": False,
            }

            t0 = time.monotonic()
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(f"{url}/v1/chat/completions", json=payload)

            elapsed = time.monotonic() - t0

            if resp.status_code != 200:
                error_text = resp.text[:200]
                self._add_log("error", f"✗ HTTP {resp.status_code}: {title}", {"error": error_text})
                self.status["total_errors"] += 1
                await self._mark_failed(video_id, f"HTTP {resp.status_code}")
                self.status["batch_done"] += 1
                return {"error": f"HTTP {resp.status_code}: {error_text}"}

            data = resp.json()
            usage = data.get("usage", {})
            completion_tokens = usage.get("completion_tokens", 0)
            tok_s = round(completion_tokens / elapsed, 1) if elapsed > 0 else 0
            self.status["tokens_per_second"] = tok_s

            # Response-Text extrahieren
            text = ""
            for choice in data.get("choices", []):
                msg = choice.get("message", {})
                text += msg.get("content", "")

            if not text.strip():
                self._add_log("error", f"✗ Leere Antwort: {title}")
                self.status["total_errors"] += 1
                await self._mark_failed(video_id, "Leere Antwort")
                self.status["batch_done"] += 1
                return {"error": "Leere Antwort von LM Studio"}

            # JSON parsen
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                import re
                match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
                if match:
                    try:
                        result = json.loads(match.group())
                    except json.JSONDecodeError:
                        self._add_log("error", f"✗ JSON-Fehler: {title}", {"raw": text[:200]})
                        self.status["total_errors"] += 1
                        await self._mark_failed(video_id, "JSON-Parse")
                        self.status["batch_done"] += 1
                        return {"error": "JSON-Parse fehlgeschlagen", "raw": text[:500]}
                else:
                    self._add_log("error", f"✗ Kein JSON: {title}", {"raw": text[:200]})
                    self.status["total_errors"] += 1
                    await self._mark_failed(video_id, "Kein JSON")
                    self.status["batch_done"] += 1
                    return {"error": "Kein JSON in Antwort", "raw": text[:500]}

            # In DB speichern (inkl. Typ-Korrektur + Log mit Titel)
            await self._save_analysis(video_id, result)
            self.status["total_analyzed"] += 1
            self.status["batch_done"] += 1

            return {"ok": True, "video_id": video_id, "title": title, "result": result, "elapsed": round(elapsed, 1), "tok_s": tok_s}

        except httpx.ConnectError as e:
            self._add_log("error", f"✗ Verbindung fehlgeschlagen: {e}")
            self.status["total_errors"] += 1
            self.status["connected"] = False
            return {"error": f"Verbindung fehlgeschlagen: {e}"}
        except httpx.TimeoutException:
            self._add_log("error", f"✗ Timeout (>180s): {title}")
            self.status["total_errors"] += 1
            return {"error": "Timeout >180s"}
        except Exception as e:
            self._add_log("error", f"✗ {type(e).__name__}: {title}", {"error": str(e)})
            self.status["total_errors"] += 1
            return {"error": str(e)}
        finally:
            if not self._running:
                self.status["processing"] = False
            self.status["current_video_id"] = None
            self.status["current_title"] = None

    async def _get_video_title(self, video_id: str) -> str:
        """Titel eines Videos aus DB laden (kurz)."""
        row = await db.fetch_one("SELECT title FROM videos WHERE id = ?", (video_id,))
        if row and row["title"]:
            t = row["title"]
            return t[:50] + "…" if len(t) > 50 else t
        row = await db.fetch_one("SELECT title FROM rss_entries WHERE video_id = ?", (video_id,))
        if row and row["title"]:
            t = row["title"]
            return t[:50] + "…" if len(t) > 50 else t
        return video_id

    async def _mark_failed(self, video_id: str, error: str):
        """Fehlgeschlagene Analyse markieren → fällt aus Queue."""
        from datetime import datetime, timezone
        fail_json = json.dumps({
            "error": error,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False)
        await db.execute(
            "UPDATE videos SET ai_analysis = ?, ai_analyzed_at = datetime('now') WHERE id = ?",
            (fail_json, video_id)
        )
        await db.execute(
            "UPDATE rss_entries SET ai_analysis = ? WHERE video_id = ?",
            (fail_json, video_id)
        )

    async def _save_analysis(self, video_id: str, result: dict):
        """Analyse-Ergebnis in DB speichern + video_type korrigieren."""
        new_type = result.get("video_type", "").lower()
        confidence = result.get("confidence", 0)
        title = await self._get_video_title(video_id)

        # Nur bei ausreichender Confidence video_type ändern
        if new_type in ("video", "short", "live") and confidence >= 0.7:
            # Aktuellen Typ lesen
            row = await db.fetch_one("SELECT video_type FROM videos WHERE id = ?", (video_id,))
            if not row:
                row = await db.fetch_one("SELECT video_type FROM rss_entries WHERE video_id = ?", (video_id,))
            old_type = (row["video_type"] if row else "video") or "video"

            if old_type != new_type:
                await db.execute(
                    "UPDATE videos SET video_type = ?, updated_at = datetime('now') WHERE id = ?",
                    (new_type, video_id)
                )
                await db.execute(
                    "UPDATE rss_entries SET video_type = ? WHERE video_id = ?",
                    (new_type, video_id)
                )
                self.status["total_type_changes"] += 1
                self._add_log("info", f"⚡ {old_type} → {new_type}: {title}", {
                    "video_id": video_id, "old": old_type, "new": new_type, "confidence": confidence,
                })
            else:
                self._add_log("info", f"✓ bleibt {old_type}: {title}", {
                    "video_id": video_id, "type": old_type, "confidence": confidence,
                })
        else:
            self._add_log("info", f"✓ {new_type} (conf {confidence}): {title}", {
                "video_id": video_id, "confidence": confidence,
            })

        # Analyse-Daten als JSON in ai_analysis Spalte speichern
        analysis_json = json.dumps(result, ensure_ascii=False)
        await db.execute(
            "UPDATE videos SET ai_analysis = ?, ai_analyzed_at = datetime('now') WHERE id = ?",
            (analysis_json, video_id)
        )
        await db.execute(
            "UPDATE rss_entries SET ai_analysis = ? WHERE video_id = ?",
            (analysis_json, video_id)
        )

    # ─── Queue-basierte Batch-Analyse ────────────────────

    async def get_queue_count(self) -> int:
        """Anzahl noch nicht analysierter Videos."""
        # Videos + RSS-Einträge ohne AI-Analyse
        count = await db.fetch_val(
            """SELECT COUNT(*) FROM (
                SELECT id FROM videos WHERE ai_analysis IS NULL AND status = 'ready'
                UNION
                SELECT video_id FROM rss_entries WHERE ai_analysis IS NULL
                  AND video_id NOT IN (SELECT id FROM videos WHERE ai_analysis IS NOT NULL)
            )"""
        )
        return count or 0

    async def get_next_batch(self, limit: int = 5) -> list[str]:
        """Nächste Video-IDs für Analyse."""
        # Priorität: heruntergeladene Videos zuerst, dann RSS-Einträge
        rows = await db.fetch_all(
            """SELECT id FROM videos
               WHERE ai_analysis IS NULL AND status = 'ready'
               ORDER BY download_date DESC LIMIT ?""",
            (limit,)
        )
        ids = [r["id"] for r in rows]

        if len(ids) < limit:
            remaining = limit - len(ids)
            rss_rows = await db.fetch_all(
                """SELECT DISTINCT video_id FROM rss_entries
                   WHERE ai_analysis IS NULL
                   AND video_id NOT IN (SELECT id FROM videos WHERE ai_analysis IS NOT NULL)
                   AND video_id NOT IN ({})
                   ORDER BY published DESC LIMIT ?""".format(
                    ",".join("?" * len(ids)) if ids else "''"
                ),
                (*ids, remaining) if ids else (remaining,)
            )
            ids.extend(r["video_id"] for r in rss_rows)

        return ids

    # ─── Queue Reset ────────────────────────────────────────

    async def reset_queue_all(self) -> dict:
        """Alle AI-Analysen löschen → alles neu in Queue."""
        await db.execute("UPDATE videos SET ai_analysis = NULL, ai_analyzed_at = NULL WHERE ai_analysis IS NOT NULL")
        await db.execute("UPDATE rss_entries SET ai_analysis = NULL WHERE ai_analysis IS NOT NULL")
        count = await self.get_queue_count()
        self.status["queue_count"] = count
        self.status["total_analyzed"] = 0
        self.status["total_errors"] = 0
        self.status["total_type_changes"] = 0
        self._add_log("info", f"🔄 Queue komplett zurückgesetzt: {count} Videos")
        return {"message": f"Queue zurückgesetzt: {count} Videos", "count": count}

    async def reset_queue_errors(self) -> dict:
        """Nur fehlerhafte Analysen zurücksetzen."""
        await db.execute("UPDATE videos SET ai_analysis = NULL, ai_analyzed_at = NULL WHERE ai_analysis LIKE '%\"error\"%'")
        await db.execute("UPDATE rss_entries SET ai_analysis = NULL WHERE ai_analysis LIKE '%\"error\"%'")
        count = await self.get_queue_count()
        self.status["queue_count"] = count
        self._add_log("info", f"🔄 Fehlerhafte zurückgesetzt: {count} Videos in Queue")
        return {"message": f"Fehlerhafte zurückgesetzt", "count": count}

    async def reset_queue_recent(self, n: int = 100) -> dict:
        """Letzte N analysierte Videos zurücksetzen."""
        await db.execute(
            "UPDATE videos SET ai_analysis = NULL, ai_analyzed_at = NULL WHERE id IN "
            "(SELECT id FROM videos WHERE ai_analysis IS NOT NULL ORDER BY ai_analyzed_at DESC LIMIT ?)",
            (n,)
        )
        await db.execute(
            "UPDATE rss_entries SET ai_analysis = NULL WHERE video_id IN "
            "(SELECT video_id FROM rss_entries WHERE ai_analysis IS NOT NULL ORDER BY rowid DESC LIMIT ?)",
            (n,)
        )
        count = await self.get_queue_count()
        self.status["queue_count"] = count
        self._add_log("info", f"🔄 Letzte {n} zurückgesetzt: {count} Videos in Queue")
        return {"message": f"Letzte {n} zurückgesetzt", "count": count}

    # ─── Direkte Queue-Abarbeitung ─────────────────────────

    async def run_queue(self):
        """Gesamte Queue sequenziell abarbeiten."""
        if self._running:
            return {"error": "Läuft bereits"}

        conn = await self.check_connection()
        if not conn.get("connected"):
            return {"error": f"LM Studio nicht erreichbar: {conn.get('error', '?')}"}

        total = await self.get_queue_count()
        if total == 0:
            return {"message": "Queue leer", "count": 0}

        batch_size = max(1, min(self.config.get("batch_size", 20), 100))
        self.status["batch_total"] = total
        self.status["batch_done"] = 0
        self._running = True
        self._add_log("info", f"▶ Queue: {total} Videos")

        async def _process():
            try:
                while self._running:
                    batch = await self.get_next_batch(batch_size)
                    if not batch:
                        break

                    for vid in batch:
                        if not self._running:
                            break
                        await self.analyze_video(vid)

                    # Queue-Count nach jedem Batch aktualisieren
                    self.status["queue_count"] = await self.get_queue_count()

                done = self.status["batch_done"]
                changes = self.status["total_type_changes"]
                errors = self.status["total_errors"]
                self._add_log("info", f"■ Fertig: {done} analysiert, {changes} Typ-Änderungen, {errors} Fehler")
            except asyncio.CancelledError:
                self._add_log("info", f"■ Abgebrochen bei {self.status['batch_done']}/{self.status['batch_total']}")
            except Exception as e:
                self._add_log("error", f"■ Fehler: {type(e).__name__}: {e}")
            finally:
                self._running = False
                self.status["processing"] = False

        self._task = asyncio.create_task(_process())
        return {"message": f"Queue gestartet ({total} Videos)", "total": total}

    async def stop_queue(self):
        """Laufende Queue-Abarbeitung stoppen."""
        if self._running and self._task:
            self._running = False
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
            self._add_log("info", f"■ Gestoppt bei {self.status['batch_done']}/{self.status['batch_total']}")
        self.status["processing"] = False
        return {"message": "Gestoppt"}

    async def start_worker(self):
        """Alias für run_queue (Kompatibilität)."""
        return await self.run_queue()

    async def stop_worker(self):
        """Alias für stop_queue (Kompatibilität)."""
        return await self.stop_queue()


# Singleton
thumbnail_ai = ThumbnailAiService()
