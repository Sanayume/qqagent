import sqlite3

from src.memory.knowledge import KnowledgeStore


def test_bm25_search_is_scoped_to_session(tmp_path):
    store = KnowledgeStore(db_path=str(tmp_path / "knowledge.db"))

    with sqlite3.connect(store.db_path) as conn:
        cur = conn.execute(
            "INSERT INTO memory_chunks (session_id, content, role, embedding, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("session_a", "shared keyword belongs to session a", "user", None, 1.0),
        )
        conn.execute(
            "INSERT INTO memory_fts (rowid, content) VALUES (?, ?)",
            (cur.lastrowid, "shared keyword belongs to session a"),
        )
        cur = conn.execute(
            "INSERT INTO memory_chunks (session_id, content, role, embedding, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("session_b", "shared keyword belongs to session b", "user", None, 2.0),
        )
        conn.execute(
            "INSERT INTO memory_fts (rowid, content) VALUES (?, ?)",
            (cur.lastrowid, "shared keyword belongs to session b"),
        )
        conn.commit()

    results = store.search("shared keyword", "session_a", limit=5)

    assert results
    assert all("session b" not in item["content"] for item in results)
    assert any("session a" in item["content"] for item in results)
