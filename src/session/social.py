"""Lightweight social runtime for more natural chat behavior."""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.utils.logger import log


DEFAULT_SOCIAL_CONFIG = {
    "enabled": True,
    "quiet_hour_start": 1,
    "quiet_hour_end": 7,
    "familiar_threshold": 12,
    "lively_threshold": 4,
    "recent_window_seconds": 180,
    "max_prompt_chars": 1400,
}


@dataclass
class SocialSnapshot:
    chat_key: str
    chat_type: str
    mood: str
    energy: str
    familiarity: str
    message_count: int
    recent_count: int
    participant_count: int
    user_message_count: int
    user_name: str


class SocialRuntime:
    """Tracks lightweight social state and builds per-turn guidance.

    This intentionally stays heuristic and transparent. It does not decide final
    content; it gives the main persona a compact read of the room.
    """

    def __init__(
        self,
        db_path: str = "data/social_state.db",
        config: dict[str, Any] | None = None,
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.config = {**DEFAULT_SOCIAL_CONFIG, **(config or {})}
        self._lock = threading.Lock()
        self._recent_events: dict[str, list[tuple[float, int]]] = {}
        self._init_db()
        log.info(f"SocialRuntime initialized: {self.db_path}")

    def update_config(self, config: dict[str, Any] | None) -> None:
        self.config = {**DEFAULT_SOCIAL_CONFIG, **(config or {})}

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS social_users (
                    chat_key TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    nickname TEXT NOT NULL DEFAULT '',
                    message_count INTEGER NOT NULL DEFAULT 0,
                    last_seen REAL NOT NULL DEFAULT 0,
                    last_text TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (chat_key, user_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS social_chats (
                    chat_key TEXT PRIMARY KEY,
                    chat_type TEXT NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    last_seen REAL NOT NULL DEFAULT 0,
                    last_mood TEXT NOT NULL DEFAULT 'calm'
                )
                """
            )
            conn.commit()

    @staticmethod
    def chat_key_for_event(event) -> str:
        if getattr(event, "is_group", False) and getattr(event, "group_id", None):
            return f"group:{event.group_id}"
        return f"private:{event.user_id}"

    @staticmethod
    def chat_type_for_event(event) -> str:
        return "group" if getattr(event, "is_group", False) else "private"

    def observe_message(self, event, text: str, sender_name: str = "") -> None:
        if not self.enabled:
            return

        now = time.time()
        chat_key = self.chat_key_for_event(event)
        chat_type = self.chat_type_for_event(event)
        user_id = int(getattr(event, "user_id", 0) or 0)
        text = (text or "").strip()
        sender_name = sender_name or getattr(event, "sender_nickname", "") or str(user_id)

        with self._lock:
            recent = self._recent_events.setdefault(chat_key, [])
            recent.append((now, user_id))
            window = float(self.config.get("recent_window_seconds", 180))
            self._recent_events[chat_key] = [(ts, uid) for ts, uid in recent if now - ts <= window]

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO social_chats (chat_key, chat_type, message_count, last_seen, last_mood)
                    VALUES (?, ?, 1, ?, 'calm')
                    ON CONFLICT(chat_key) DO UPDATE SET
                        message_count = message_count + 1,
                        last_seen = excluded.last_seen
                    """,
                    (chat_key, chat_type, now),
                )
                conn.execute(
                    """
                    INSERT INTO social_users (chat_key, user_id, nickname, message_count, last_seen, last_text)
                    VALUES (?, ?, ?, 1, ?, ?)
                    ON CONFLICT(chat_key, user_id) DO UPDATE SET
                        nickname = excluded.nickname,
                        message_count = message_count + 1,
                        last_seen = excluded.last_seen,
                        last_text = excluded.last_text
                    """,
                    (chat_key, user_id, sender_name, now, text[:500]),
                )
                conn.commit()

    def build_prompt(
        self,
        event,
        session_id: str,
        message_count: int = 1,
        participant_count: int = 1,
    ) -> str:
        if not self.enabled:
            return ""

        snapshot = self.snapshot(event, message_count=message_count, participant_count=participant_count)
        guidance = self._guidance(snapshot)
        prompt = (
            "## 社交运行时\n"
            "下面是隐藏的社交状态，只用于调整说话分寸；不要向用户解释这些字段，也不要说自己在读取状态。\n"
            f"- 会话: {session_id}\n"
            f"- 场景: {'群聊' if snapshot.chat_type == 'group' else '私聊'}\n"
            f"- 当前气氛: {snapshot.mood} / 能量: {snapshot.energy}\n"
            f"- 本轮输入: {snapshot.message_count} 条消息，约 {snapshot.participant_count} 人参与\n"
            f"- 最近热度: {snapshot.recent_count} 条消息\n"
            f"- 和 {snapshot.user_name} 的熟悉度: {snapshot.familiarity} "
            f"({snapshot.user_message_count} 条历史互动)\n"
            f"- 回复策略: {guidance}\n"
            "- 像群友一样自然接话，短句优先；认真求助时再展开。\n"
            "- 可以接梗、吐槽、自嘲，但不要每句话都强行卖萌或解释设定。\n"
            "- 群里很热闹时少长篇说教，优先抓住一个点回应。\n"
        )
        max_chars = int(self.config.get("max_prompt_chars", 1400))
        return prompt[:max_chars]

    def snapshot(self, event, message_count: int = 1, participant_count: int = 1) -> SocialSnapshot:
        chat_key = self.chat_key_for_event(event)
        chat_type = self.chat_type_for_event(event)
        user_id = int(getattr(event, "user_id", 0) or 0)
        now = time.time()

        with self._lock:
            recent = self._recent_events.get(chat_key, [])
            window = float(self.config.get("recent_window_seconds", 180))
            recent = [(ts, uid) for ts, uid in recent if now - ts <= window]
            self._recent_events[chat_key] = recent
            recent_count = len(recent)

            with sqlite3.connect(self.db_path) as conn:
                chat_row = conn.execute(
                    "SELECT message_count FROM social_chats WHERE chat_key = ?",
                    (chat_key,),
                ).fetchone()
                user_row = conn.execute(
                    "SELECT nickname, message_count, last_text FROM social_users WHERE chat_key = ? AND user_id = ?",
                    (chat_key, user_id),
                ).fetchone()

        total_messages = int(chat_row[0]) if chat_row else 0
        user_name = user_row[0] if user_row else (getattr(event, "sender_nickname", "") or str(user_id))
        user_messages = int(user_row[1]) if user_row else 0
        last_text = user_row[2] if user_row else ""

        mood = self._classify_mood(last_text, recent_count)
        energy = self._classify_energy(recent_count)
        familiar_threshold = int(self.config.get("familiar_threshold", 12))
        if user_messages >= familiar_threshold * 2:
            familiarity = "很熟"
        elif user_messages >= familiar_threshold:
            familiarity = "熟悉"
        elif user_messages >= 3:
            familiarity = "见过几次"
        else:
            familiarity = "新近互动"

        return SocialSnapshot(
            chat_key=chat_key,
            chat_type=chat_type,
            mood=mood,
            energy=energy,
            familiarity=familiarity,
            message_count=message_count,
            recent_count=recent_count,
            participant_count=participant_count,
            user_message_count=user_messages,
            user_name=user_name,
        )

    def get_stats(self) -> dict[str, int | bool]:
        with sqlite3.connect(self.db_path) as conn:
            users = conn.execute("SELECT COUNT(*) FROM social_users").fetchone()[0]
            chats = conn.execute("SELECT COUNT(*) FROM social_chats").fetchone()[0]
            messages = conn.execute("SELECT COALESCE(SUM(message_count), 0) FROM social_chats").fetchone()[0]
        return {
            "enabled": self.enabled,
            "chats": int(chats),
            "users": int(users),
            "observed_messages": int(messages or 0),
        }

    def _classify_mood(self, text: str, recent_count: int) -> str:
        lowered = text.lower()
        if any(k in text for k in ("急", "救", "报错", "崩", "坏了", "怎么办", "求助")):
            return "求助/紧张"
        if any(k in text for k in ("笑死", "哈哈", "草", "乐", "绷", "233")):
            return "玩梗/轻松"
        if any(k in text for k in ("烦", "难受", "累", "麻了", "崩溃")):
            return "低落/需要温柔"
        if any(k in lowered for k in ("bug", "error", "failed", "exception")):
            return "技术求助"
        if self._is_quiet_hour():
            return "深夜/安静"
        if recent_count >= int(self.config.get("lively_threshold", 4)):
            return "热闹"
        return "平静"

    def _classify_energy(self, recent_count: int) -> str:
        if self._is_quiet_hour():
            return "低"
        if recent_count >= int(self.config.get("lively_threshold", 4)):
            return "高"
        if recent_count >= 2:
            return "中"
        return "低"

    def _guidance(self, snapshot: SocialSnapshot) -> str:
        if snapshot.chat_type == "private":
            return "更像一对一聊天，回应可以多一点陪伴感；先理解对方，再给建议。"
        if snapshot.mood in ("求助/紧张", "技术求助"):
            return "先解决问题，少玩梗；如果信息不足，问一个最关键的问题。"
        if snapshot.mood == "低落/需要温柔":
            return "语气放软，不要锐评；短短接住情绪即可。"
        if snapshot.mood == "玩梗/轻松":
            return "可以接梗，但只抓一个点，不要把笑话解释死。"
        if snapshot.energy == "高":
            return "群里热闹，回复短一点，像插一句话，不要开长篇。"
        if snapshot.familiarity in ("熟悉", "很熟"):
            return "可以更随意一点，允许轻微吐槽或熟人式玩笑。"
        return "自然、简短、不要过度热情。"

    def _is_quiet_hour(self) -> bool:
        hour = time.localtime().tm_hour
        start = int(self.config.get("quiet_hour_start", 1))
        end = int(self.config.get("quiet_hour_end", 7))
        if start <= end:
            return start <= hour < end
        return hour >= start or hour < end
