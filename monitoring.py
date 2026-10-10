"""监控 / 告警 / 指标端点：给 CI 和运维用的最小可观测层。

端点：
    GET /metrics   返回当前系统指标（JSON）
    GET /alerts    查询最近的告警记录
    POST /alerts/webhook  接收外部告警（飞书/Slack/邮件的占位入口）

设计原则：
    - 不引入 Prometheus / Grafana 重型依赖
    - 直接读 SQLite 算指标，够用
    - 生产环境把 webhook 换成真实告警通道
"""
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from config import settings
from logging_config import get_ctx_logger

log = get_ctx_logger("monitoring")
router = APIRouter()

# 告警持久化表
def _ensure_alerts_table():
    db = Path(settings.SQLITE_PATH)
    if not db.exists():
        return
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,
            message TEXT,
            severity TEXT NOT NULL DEFAULT 'warning',
            source TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


# ============================================================
# 指标
# ============================================================

@router.get("/metrics")
def metrics() -> dict:
    """返回系统核心指标，供 CI 健康检查或监控脚本使用。"""
    db = Path(settings.SQLITE_PATH)
    result: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "customer_support_agent",
        "db_exists": db.exists(),
    }

    if not db.exists():
        result["status"] = "no_data"
        return result

    conn = sqlite3.connect(str(db))
    try:
        # 工单统计
        tickets_total = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        tickets_open = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE status = 'open'"
        ).fetchone()[0]
        tickets_urgent = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE priority = 'urgent' AND status = 'open'"
        ).fetchone()[0]

        # 审计日志：最近 100 条的置信度均值
        rows = conn.execute(
            "SELECT confidence FROM audit_log ORDER BY id DESC LIMIT 100"
        ).fetchall()
        avg_confidence = (
            sum(r[0] for r in rows) / len(rows) if rows else None
        )

        # LLM 用量：最近 100 条的总 token 和成本
        usage_rows = conn.execute(
            "SELECT usage FROM audit_log WHERE usage IS NOT NULL ORDER BY id DESC LIMIT 100"
        ).fetchall()
        total_tokens = 0
        total_cost = 0.0
        llm_calls = 0
        for (usage_json,) in usage_rows:
            try:
                u = json.loads(usage_json)
                total_tokens += u.get("total_tokens", 0)
                total_cost += u.get("cost_usd", 0.0)
                llm_calls += 1
            except json.JSONDecodeError:
                pass

        result.update(
            {
                "status": "ok",
                "tickets": {
                    "total": tickets_total,
                    "open": tickets_open,
                    "urgent_open": tickets_urgent,
                },
                "audit": {
                    "avg_confidence_last_100": round(avg_confidence, 4) if avg_confidence is not None else None,
                },
                "llm": {
                    "calls_last_100": llm_calls,
                    "total_tokens_last_100": total_tokens,
                    "total_cost_usd_last_100": round(total_cost, 6),
                },
                "rag": {
                    "collection": settings.CHROMA_COLLECTION,
                    "top_k": settings.RAG_TOP_K,
                    "min_score": settings.RAG_MIN_SCORE,
                },
                "threshold": {
                    "confidence": settings.CONFIDENCE_THRESHOLD,
                },
            }
        )
    finally:
        conn.close()

    return result


# ============================================================
# 告警
# ============================================================

class AlertRequest(BaseModel):
    alert_type: str
    message: str = ""
    severity: str = "warning"
    source: str = "api"


@router.post("/alerts")
def create_alert(req: AlertRequest) -> dict:
    """手动触发告警（CI 脚本 / 运维脚本调用）。"""
    _ensure_alerts_table()
    db = Path(settings.SQLITE_PATH)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO alerts (alert_type, message, severity, source, created_at) VALUES (?, ?, ?, ?, ?)",
        (req.alert_type, req.message, req.severity, req.source, now),
    )
    conn.commit()
    alert_id = cur.lastrowid
    conn.close()
    log.warning(
        "alert_created id=%s type=%s severity=%s source=%s",
        alert_id, req.alert_type, req.severity, req.source,
    )
    return {"id": alert_id, "status": "created"}


@router.get("/alerts")
def list_alerts(limit: int = 20, severity: str | None = None) -> dict:
    """查询最近告警，可按 severity 过滤。"""
    _ensure_alerts_table()
    db = Path(settings.SQLITE_PATH)
    if not db.exists():
        return {"alerts": []}
    conn = sqlite3.connect(str(db))
    try:
        query = "SELECT id, alert_type, message, severity, source, created_at FROM alerts WHERE 1=1"
        params: list = []
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    cols = ("id", "alert_type", "message", "severity", "source", "created_at")
    return {"alerts": [dict(zip(cols, r)) for r in rows]}


@router.post("/alerts/webhook")
def alert_webhook(req: AlertRequest) -> dict:
    """外部系统（飞书 / Slack / 邮件）调用此接口上报告警。
    生产环境在这里接真实告警通道，当前只落库 + 打日志。
    """
    _ensure_alerts_table()
    db = Path(settings.SQLITE_PATH)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO alerts (alert_type, message, severity, source, created_at) VALUES (?, ?, ?, ?, ?)",
        (req.alert_type, req.message, req.severity, "webhook", now),
    )
    conn.commit()
    conn.close()
    log.warning("alert_webhook type=%s severity=%s source=%s", req.alert_type, req.severity, req.source)
    return {"status": "received", "note": "生产环境请在此处接飞书/Slack/邮件通道"}


# ============================================================
# 主动告警检测（供 cron / CI 定时调用）
# ============================================================

def check_health() -> dict:
    """主动健康检查：返回需要告警的条目列表。
    CI 脚本可以定时调用这个，有告警就 POST /alerts。
    """
    alerts: list[dict] = []
    try:
        m = metrics()
        if m.get("status") != "ok":
            alerts.append({
                "alert_type": "db_unavailable",
                "message": "数据库不存在或无法读取",
                "severity": "critical",
            })
            return {"alerts": alerts, "metrics": m}

        urgent = m.get("tickets", {}).get("urgent_open", 0)
        if urgent > 5:
            alerts.append({
                "alert_type": "urgent_tickets_high",
                "message": f"紧急未处理工单 {urgent} 条，超过阈值 5",
                "severity": "warning",
            })

        llm_calls = m.get("llm", {}).get("calls_last_100", 0)
        if llm_calls > 0:
            cost = m.get("llm", {}).get("total_cost_usd_last_100", 0)
            if cost > 1.0:
                alerts.append({
                    "alert_type": "llm_cost_high",
                    "message": f"最近 {llm_calls} 次 LLM 调用成本 ${cost:.4f}，超过 $1 阈值",
                    "severity": "warning",
                })
    except Exception as exc:
        alerts.append({
            "alert_type": "health_check_error",
            "message": str(exc),
            "severity": "critical",
        })

    return {"alerts": alerts, "metrics": metrics()}
