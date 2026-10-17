"""工具函数：工单持久化到 SQLite（含优先级与团队），trace 写入 state。"""
import sqlite3
from datetime import datetime, timezone

from logging_config import get_ctx_logger
from store.audit import record

log = get_ctx_logger("agent_knowledge.tickets")

# 意图 → 默认团队映射（业务可改，不写死在节点里）
INTENT_TO_TEAM = {
    "refund": "aftersales",
    "return": "aftersales",
    "reship": "aftersales",
    "compensate": "quality",
    "promo": "ops",
    "ticket": "general",
    "clarify": "general",
}

# 意图 → 默认优先级映射（破损/质量类紧急）
INTENT_TO_PRIORITY = {
    "compensate": "urgent",
    "ticket": "urgent",
    "clarify": "normal",
}


def _team_for(intent: str) -> str:
    return INTENT_TO_TEAM.get(intent, "general")


def _priority_for(intent: str) -> str:
    return INTENT_TO_PRIORITY.get(intent, "normal")


def create_ticket(
    db_path,
    user_id: str,
    question: str,
    intent: str = "general",
    priority: str | None = None,
    team: str | None = None,
    session_id: str | None = None,
) -> dict:
    """在 SQLite 中创建持久化工单，含优先级与团队，返回含真实 id 的 dict。"""
    from pathlib import Path

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    priority = priority or _priority_for(intent)
    team = team or _team_for(intent)

    conn = sqlite3.connect(str(db_path))
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
    now = datetime.now(timezone.utc).isoformat()
    import uuid

    ticket_no = f"TICKET-{int(datetime.now(timezone.utc).timestamp())}-{uuid.uuid4().hex[:6]}"
    cur = conn.execute(
        "INSERT INTO tickets (ticket_no, user_id, question, intent, priority, team, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'open', ?)",
        (ticket_no, user_id, question, intent, priority, team, now),
    )
    row_id = cur.lastrowid
    conn.commit()
    rec = {
        "event": "ticket_created",
        "ticket_no": ticket_no,
        "user_id": user_id,
        "intent": intent,
        "priority": priority,
        "team": team,
    }
    if session_id:
        rec["session_id"] = session_id
    record(rec)
    conn.close()
    log.info(
        "ticket_created row_id=%s ticket_no=%s user_id=%s intent=%s priority=%s team=%s",
        row_id,
        ticket_no,
        user_id,
        intent,
        priority,
        team,
    )
    return {
        "id": row_id,
        "ticket_no": ticket_no,
        "ticket_id": ticket_no,
        "user_id": user_id,
        "question": question,
        "intent": intent,
        "priority": priority,
        "team": team,
        "status": "open",
    }


def log_trace(state: dict, step: str) -> None:
    trace = state.setdefault("trace", [])
    trace.append(step)


# ============================================================
# 工单生命周期：查询 / 改状态 / 指派（open -> in_progress -> closed）
# ============================================================

_VALID_TRANSITIONS = {
    "open": {"in_progress", "closed"},
    "in_progress": {"closed", "open"},
    # closed 是默认终态，但支持"重开"能力：closed -> open
    "closed": {"open"},
}


def list_tickets(db_path, status: str | None = None, team: str | None = None, limit: int = 50) -> list[dict]:
    """查询工单，可按 status / team 过滤，返回倒序（最新在前）。"""
    from pathlib import Path

    db_path = Path(db_path)
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    try:
        query = "SELECT id, ticket_no, user_id, question, intent, priority, team, status, created_at, assigned_to, updated_at FROM tickets WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if team:
            query += " AND team = ?"
            params.append(team)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    cols = ("id", "ticket_no", "user_id", "question", "intent", "priority", "team", "status", "created_at", "assigned_to", "updated_at")
    return [dict(zip(cols, r)) for r in rows]


def get_ticket(db_path, ticket_no: str) -> dict | None:
    """按 ticket_no 取单条工单，不存在返回 None。"""
    from pathlib import Path

    db_path = Path(db_path)
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT id, ticket_no, user_id, question, intent, priority, team, status, created_at, assigned_to, updated_at FROM tickets WHERE ticket_no = ?",
            (ticket_no,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    cols = ("id", "ticket_no", "user_id", "question", "intent", "priority", "team", "status", "created_at", "assigned_to", "updated_at")
    return dict(zip(cols, row))


def transition_ticket(db_path, ticket_no: str, new_status: str, assignee: str | None = None, user_id: str | None = None) -> dict:
    """工单状态流转：open->in_progress/closed, in_progress->closed/open。

    非法流转（如 closed->open）会抛 ValueError，由调用方决定如何兜底。
    可选 assignee：指派处理人，写入 assigned_to 列（不存在则自动建列）。
    """
    from pathlib import Path
    from datetime import datetime, timezone

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        # 保证表存在（兼容全新空库）
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tickets ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "ticket_no TEXT UNIQUE NOT NULL, user_id TEXT NOT NULL, "
            "question TEXT NOT NULL, intent TEXT, priority TEXT NOT NULL DEFAULT 'normal', "
            "team TEXT NOT NULL DEFAULT 'general', status TEXT NOT NULL DEFAULT 'open', "
            "created_at TEXT NOT NULL, assigned_to TEXT, updated_at TEXT)"
        )
        # 保证 assigned_to 列存在（兼容旧库）
        existing = {r[1] for r in conn.execute("PRAGMA table_info(tickets)").fetchall()}
        if "assigned_to" not in existing:
            conn.execute("ALTER TABLE tickets ADD COLUMN assigned_to TEXT")

        ticket = get_ticket(db_path, ticket_no)
        if ticket is None:
            raise ValueError(f"ticket_not_found: {ticket_no}")

        current = ticket["status"]
        if new_status not in _VALID_TRANSITIONS.get(current, set()):
            raise ValueError(f"illegal_transition: {current} -> {new_status}")

        now = datetime.now(timezone.utc).isoformat()
        if assignee:
            conn.execute(
                "UPDATE tickets SET status = ?, assigned_to = ?, updated_at = ? WHERE ticket_no = ?",
                (new_status, assignee, now, ticket_no),
            )
        else:
            conn.execute(
                "UPDATE tickets SET status = ?, updated_at = ? WHERE ticket_no = ?",
                (new_status, now, ticket_no),
            )
        conn.commit()
        rec = {
            "event": "ticket_transition",
            "ticket_no": ticket_no,
            "from": current,
            "to": new_status,
            "assignee": assignee,
        }
        if user_id:
            rec["user_id"] = user_id
        record(rec)
        log.info(
            "ticket_transition ticket_no=%s %s -> %s assignee=%s",
            ticket_no,
            current,
            new_status,
            assignee,
        )
    finally:
        conn.close()
    return get_ticket(db_path, ticket_no) or {}
