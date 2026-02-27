"""向量记忆 / 长期知识库

SQLite + FTS5 全文搜索 + 向量余弦相似度 + 时间衰减
"""

import json
import math
import sqlite3
import time
from pathlib import Path

from src.utils.logger import log
from src.utils.config_loader import get_tuning

# ==================== 常量（默认值，可通过 config.yaml tuning 覆盖） ====================
MIN_CONTENT_LENGTH = 5
VECTOR_SEARCH_LIMIT = 200
COSINE_THRESHOLD = 0.3
BM25_WEIGHT = 0.4
VECTOR_WEIGHT = 0.6


class KnowledgeStore:
    """长期记忆存储"""

    def __init__(self, db_path: str = "data/knowledge.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        log.info(f"KnowledgeStore initialized: {self.db_path}")

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    role TEXT NOT NULL,
                    embedding TEXT,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_session
                ON memory_chunks(session_id)
            """)
            # FTS5 虚表
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
                USING fts5(content, content_rowid='id')
            """)
            conn.commit()

    def store(self, session_id: str, content: str, role: str = "user"):
        """存储一条记忆"""
        if not content or len(content.strip()) < MIN_CONTENT_LENGTH:
            return

        now = time.time()
        embedding_json = None
        try:
            from src.memory.embeddings import get_embedding
            embedding_json = json.dumps(get_embedding(content[:2000]))
        except Exception as e:
            log.debug(f"Embedding failed (will use FTS only): {e}")

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO memory_chunks (session_id, content, role, embedding, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, content[:5000], role, embedding_json, now),
            )
            row_id = cur.lastrowid
            conn.execute(
                "INSERT INTO memory_fts (rowid, content) VALUES (?, ?)",
                (row_id, content[:5000]),
            )
            conn.commit()

    def _bm25_search(self, conn, query: str, limit: int) -> dict[int, dict]:
        """BM25 全文搜索"""
        results = {}
        try:
            safe_query = '"' + query.replace('"', '""') + '"'
            rows = conn.execute(
                "SELECT rowid, content, rank FROM memory_fts "
                "WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?",
                (safe_query, limit * 2),
            ).fetchall()
            for row_id, content, rank in rows:
                results[row_id] = {"id": row_id, "content": content, "bm25": -rank, "cosine": 0.0}
        except Exception as e:
            log.debug(f"BM25 search failed: {e}")
        return results

    def _vector_search(self, conn, query_emb: list[float], session_id: str, existing: dict[int, dict]) -> dict[int, dict]:
        """向量余弦相似度搜索，合并到 existing 结果中"""
        rows = conn.execute(
            "SELECT id, content, embedding, created_at FROM memory_chunks "
            "WHERE session_id = ? AND embedding IS NOT NULL "
            "ORDER BY created_at DESC LIMIT ?",
            (session_id, get_tuning("knowledge_vector_search_limit", VECTOR_SEARCH_LIMIT)),
        ).fetchall()
        cosine_threshold = get_tuning("knowledge_cosine_threshold", COSINE_THRESHOLD)
        for row_id, content, emb_json, created_at in rows:
            emb = json.loads(emb_json)
            cos = self._cosine_sim(query_emb, emb)
            if row_id in existing:
                existing[row_id]["cosine"] = cos
            elif cos > cosine_threshold:
                existing[row_id] = {"id": row_id, "content": content, "bm25": 0.0, "cosine": cos}
        return existing

    @staticmethod
    def _merge_and_rank(results: dict[int, dict], limit: int) -> list[dict]:
        """归一化 BM25 + cosine 混合排序"""
        bm25_weight = get_tuning("knowledge_bm25_weight", BM25_WEIGHT)
        vector_weight = get_tuning("knowledge_vector_weight", VECTOR_WEIGHT)
        max_bm25 = max((r["bm25"] for r in results.values()), default=1.0) or 1.0
        for r in results.values():
            bm25_norm = r["bm25"] / max_bm25 if max_bm25 > 0 else 0
            r["score"] = bm25_weight * bm25_norm + vector_weight * r["cosine"]
        ranked = sorted(results.values(), key=lambda x: x["score"], reverse=True)
        return [{"content": r["content"], "score": r["score"]} for r in ranked[:limit]]

    def search(self, query: str, session_id: str, limit: int = 5) -> list[dict]:
        """搜索相关记忆，BM25 + 向量余弦混合排序"""
        with sqlite3.connect(self.db_path) as conn:
            results = self._bm25_search(conn, query, limit)

            query_emb = None
            try:
                from src.memory.embeddings import get_embedding
                query_emb = get_embedding(query)
            except Exception as e:
                log.debug(f"Embedding for search failed: {e}")

            if query_emb:
                results = self._vector_search(conn, query_emb, session_id, results)

        return self._merge_and_rank(results, limit)

    @staticmethod
    def _cosine_sim(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb) if na and nb else 0.0
