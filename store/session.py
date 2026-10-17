"""会话 / 审计持久化：SQLite，幂等建表。"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def init_db(path: str | Path) -> None:
    """幂等建表：sessions / audit_log / tickets。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            message TEXT,
            answer TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            session_id TEXT,
            question TEXT,
            intent TEXT,
            confidence REAL,
            created_ticket INTEGER,
            trace TEXT,
            usage TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_no TEXT UNIQUE NOT NULL,
            user_id TEXT NOT NULL,
            question TEXT NOT NULL,
            intent TEXT,
            priority TEXT NOT NULL DEFAULT 'normal',
            team TEXT NOT NULL DEFAULT 'general',
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            assigned_to TEXT,
            updated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def save_session(
    path: str | Path,
    user_id: str,
    session_id: str,
    question: str,
    answer: str,
) -> None:
    conn = sqlite3.connect(str(path))
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO sessions (id, user_id, message, answer, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, user_id, question, answer, now),
    )
    conn.commit()
    conn.close()


def save_audit(
    path: str | Path,
    user_id: str,
    session_id: str,
    question: str,
    intent: str,
    confidence: float,
    created_ticket: bool,
    trace: list[str],
    usage: dict | None = None,
) -> None:
    conn = sqlite3.connect(str(path))
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO audit_log (
            user_id, session_id, question, intent, confidence, created_ticket, trace, usage, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            session_id,
            question,
            intent,
            confidence,
            1 if created_ticket else 0,
            json.dumps(trace, ensure_ascii=False),
            json.dumps(usage, ensure_ascii=False) if usage else None,
            now,
        ),
    )
    conn.commit()
    conn.close()


def load_history(path: str | Path, session_id: str, limit: int = 5) -> list[dict]:
    """返回同一 session_id 最近 limit 轮的 (question, answer)，按时间正序（旧→新）。"""
    path = Path(path)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute(
            "SELECT message, answer FROM sessions WHERE id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [{"question": r[0], "answer": r[1]} for r in reversed(rows)]
