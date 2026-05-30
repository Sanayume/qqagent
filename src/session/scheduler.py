"""Persistent scheduled message delivery."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from src.utils.logger import log


class ScheduledMessageStore:
    """SQLite-backed scheduler for delayed send_message tool calls."""

    def __init__(self, db_path: str = "data/scheduled_messages.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._adapter = None
        self._tasks: dict[int, asyncio.Task] = {}
        self._running = False
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_type TEXT NOT NULL,
                    target_id INTEGER NOT NULL,
                    command_json TEXT NOT NULL,
                    due_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    sent_at REAL
                )
                """
            )
            conn.commit()

    async def start(self, adapter) -> None:
        self._adapter = adapter
        self._running = True
        pending = self._load_pending()
        for row in pending:
            self._schedule_task(row)
        log.info(f"ScheduledMessageStore started with {len(pending)} pending messages")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    def schedule_from_event(self, event, command: dict[str, Any]) -> int:
        delay_minutes = max(0, int(command.get("delay_minutes", 0) or 0))
        due_at = time.time() + delay_minutes * 60
        target_type = "group" if getattr(event, "group_id", None) else "private"
        target_id = int(event.group_id if target_type == "group" else event.user_id)
        schedule_id = self._insert(target_type, target_id, command, due_at)
        row = self._get(schedule_id)
        if row and self._running:
            self._schedule_task(row)
        return schedule_id

    def get_stats(self) -> dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM scheduled_messages GROUP BY status"
            ).fetchall()
        stats = {"pending": 0, "sent": 0, "failed": 0}
        for status, count in rows:
            stats[status] = count
        stats["active_tasks"] = len(self._tasks)
        return stats

    def _insert(self, target_type: str, target_id: int, command: dict[str, Any], due_at: float) -> int:
        payload = json.dumps(command, ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO scheduled_messages
                    (target_type, target_id, command_json, due_at, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (target_type, target_id, payload, due_at, time.time()),
            )
            conn.commit()
            return int(cur.lastrowid)

    def _get(self, schedule_id: int) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT id, target_type, target_id, command_json, due_at, attempts
                FROM scheduled_messages
                WHERE id = ? AND status = 'pending'
                """,
                (schedule_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def _load_pending(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, target_type, target_id, command_json, due_at, attempts
                FROM scheduled_messages
                WHERE status = 'pending'
                ORDER BY due_at ASC
                """
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    @staticmethod
    def _row_to_dict(row) -> dict[str, Any]:
        return {
            "id": int(row[0]),
            "target_type": row[1],
            "target_id": int(row[2]),
            "command": json.loads(row[3]),
            "due_at": float(row[4]),
            "attempts": int(row[5]),
        }

    def _schedule_task(self, row: dict[str, Any]) -> None:
        schedule_id = row["id"]
        old_task = self._tasks.get(schedule_id)
        if old_task and not old_task.done():
            old_task.cancel()
        self._tasks[schedule_id] = asyncio.create_task(self._run_one(row))

    async def _run_one(self, row: dict[str, Any]) -> None:
        schedule_id = row["id"]
        try:
            delay = max(0.0, row["due_at"] - time.time())
            if delay:
                await asyncio.sleep(delay)
            await self._send(row)
            self._mark_sent(schedule_id)
            log.info(f"Scheduled message sent: id={schedule_id}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._mark_failed(schedule_id, str(e))
            log.warning(f"Scheduled message failed: id={schedule_id}, error={e}")
        finally:
            self._tasks.pop(schedule_id, None)

    async def _send(self, row: dict[str, Any]) -> None:
        if self._adapter is None:
            raise RuntimeError("OneBot adapter is not available")
        cmd = row["command"]
        await self._adapter.send_rich_to_target(
            target_type=row["target_type"],
            target_id=row["target_id"],
            text=cmd.get("text", ""),
            image=cmd.get("image", ""),
            record=cmd.get("record", ""),
            at_users=cmd.get("at_users"),
            reply_to=cmd.get("reply_to", 0),
        )

    def _mark_sent(self, schedule_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE scheduled_messages SET status = 'sent', sent_at = ? WHERE id = ?",
                (time.time(), schedule_id),
            )
            conn.commit()

    def _mark_failed(self, schedule_id: int, error: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE scheduled_messages
                SET status = 'failed', attempts = attempts + 1, last_error = ?
                WHERE id = ?
                """,
                (error[:500], schedule_id),
            )
            conn.commit()
