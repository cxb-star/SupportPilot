"""API 路由：客服一线支撑 Agent，统一返回结构、记录会话与审计。"""
import uuid

from pathlib import Path
import sqlite3

from fastapi import APIRouter
from pydantic import BaseModel, Field, constr

from agent.graph import AgentContext, build_graph, get_checkpointer
from agent.state import init_state
from config import settings
from logging_config import get_ctx_logger
from store.session import save_audit, save_session, load_history
from guardrails import get_rate_limiter, user_has_permission, FeatureFlags, set_feature_flag

log = get_ctx_logger("routes")

MAX_TRACES = 10


def _collect_session_traces(cp_path: Path, session_id: str) -> list[dict]:
    if not cp_path.exists():
        return []
    conn = sqlite3.connect(str(cp_path))
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        from langchain_core.runnables import RunnableConfig

        saver = SqliteSaver(conn)
        cfg: RunnableConfig = {"configurable": {"thread_id": session_id}}
        ckpt_tuple = saver.get_tuple(cfg)
        if ckpt_tuple is None:
            return []
        state = ckpt_tuple.checkpoint.get("channel_values", {})
        trace = state.get("trace", []) if isinstance(state, dict) else []
        normalized = []
        for t in trace:
            if isinstance(t, dict):
                normalized.append(t)
            else:
                normalized.append({"step": str(t), "ts": None})
        return normalized[-MAX_TRACES:]
    finally:
        conn.close()


router = APIRouter()

# 挂载监控路由
from monitoring import router as monitoring_router
router.include_router(monitoring_router, tags=["monitoring"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    user_id: str = Field(default="demo-user", pattern=r"^[a-zA-Z0-9_-]+$")
    session_id: str | None = None
    role: str = "operator"


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[dict]
    confidence: float
    created_ticket: bool
    intent: str
    ticket_priority: str
    ticket_team: str
    trace: list[dict]
    traces: list[dict]
    usage: dict
    mode: str


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_configured": settings.llm_configured(),
        "embedding_configured": settings.embedding_configured(),
        "chroma_collection": settings.CHROMA_COLLECTION,
        "confidence_threshold": settings.CONFIDENCE_THRESHOLD,
    }


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    from fastapi.responses import JSONResponse
    # 限流：按 user_id
    limiter = get_rate_limiter()
    if not limiter.allow(req.user_id):
        return JSONResponse(status_code=429, content={"detail": "rate_limit_exceeded: 请求过于频繁，请稍后重试"})
    session_id = req.session_id or str(uuid.uuid4())
    ctx = AgentContext.default()

    history = load_history(settings.SQLITE_PATH, session_id, limit=5)
    state = init_state(
        question=req.question,
        session_id=session_id,
        user_id=req.user_id,
    )
    state["history"] = history
    try:
        cp_path = Path(settings.SQLITE_PATH).parent / "graph.db"
        thread_cfg = {"configurable": {"thread_id": session_id}}
        saver = get_checkpointer(cp_path)
        g = build_graph(ctx, checkpointer=saver)
        result = g.invoke(state, config=thread_cfg)
        session_traces = _collect_session_traces(cp_path, session_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("chat_invoke_failed error=%s", exc)
        result = {
            **state,
            "intent": "ticket",
            "confidence": 0.0,
            "ticket_priority": "urgent",
            "ticket_team": "general",
            "answer": "系统处理失败，已自动转人工跟进。",
            "sources": [],
            "created_ticket": False,
            "trace": state.get("trace", []) + [f"invoke_failed:{type(exc).__name__}"],
        }
        session_traces = []

    save_session(
        settings.SQLITE_PATH,
        req.user_id,
        session_id,
        req.question,
        result["answer"],
    )
    save_audit(
        settings.SQLITE_PATH,
        req.user_id,
        session_id,
        req.question,
        result["intent"],
        result["confidence"],
        result["created_ticket"],
        result["trace"],
        usage=result.get("llm_usage"),
    )

    mode = "api" if settings.llm_configured() else "mock"
    return ChatResponse(
        session_id=session_id,
        answer=result["answer"],
        sources=result["sources"],
        confidence=result["confidence"],
        created_ticket=result["created_ticket"],
        intent=result["intent"],
        ticket_priority=result.get("ticket_priority", "normal"),
        ticket_team=result.get("ticket_team", "general"),
        trace=result["trace"],
        traces=session_traces,
        usage=result.get("llm_usage", {}),
        mode=mode,
    )


# ============================================================
# 工单接口：GET /tickets  查询；POST /tickets/{no}/status  改状态
# ============================================================
from agent.tools import get_ticket, list_tickets, transition_ticket


class TicketStatusRequest(BaseModel):
    new_status: str
    assignee: str | None = None


@router.get("/tickets")
def list_tickets_route(status: str | None = None, team: str | None = None, limit: int = 50):
    return {"tickets": list_tickets(settings.SQLITE_PATH, status=status, team=team, limit=limit)}


@router.get("/tickets/{ticket_no}")
def get_ticket_route(ticket_no: str):
    t = get_ticket(settings.SQLITE_PATH, ticket_no)
    if t is None:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": f"ticket_not_found: {ticket_no}"})
    return t


@router.post("/tickets/{ticket_no}/status", response_model=TicketStatusRequest)
def set_ticket_status(ticket_no: str, req: TicketStatusRequest, role: str = "operator"):
    from fastapi.responses import JSONResponse
    if not user_has_permission(role, "transition_ticket"):
        return JSONResponse(status_code=403, content={"detail": f"permission_denied: role '{role}' cannot transition tickets"})
    import sqlite3
    from fastapi.responses import JSONResponse
    try:
        updated = transition_ticket(
            settings.SQLITE_PATH, ticket_no, req.new_status, assignee=req.assignee
        )
    except ValueError as exc:
        # 非法状态流转 / 工单不存在：业务错误，返回 400
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except sqlite3.Error as exc:
        # 数据库层错误（缺列等）：不应再裸露成 500，返回 500 但带可读 detail
        log.exception("ticket_transition_db_error ticket_no=%s", ticket_no)
        return JSONResponse(status_code=500, content={"detail": "internal_server_error"})
    return updated

# ============================================================
# 灰度 / 回滚：切换 prompt 策略版本
# ============================================================
@router.get("/feature-flags")
def get_flags():
    """查看当前灰度开关状态。"""
    from guardrails import FeatureFlags
    flags = FeatureFlags()
    return {
        "use_llm_intent": flags.use_llm_intent,
        "use_history_in_prompt": flags.use_history_in_prompt,
        "rag_top_k": flags.rag_top_k,
        "confidence_threshold": flags.confidence_threshold,
    }


@router.post("/rollback")
def rollback(version: str = "v1", role: str = ""):
    """灰度回滚接口：将 active_version 切到 v1/v2，同时切换 LLM 意图分类。

    v1 -> use_llm_intent=False，v2 -> use_llm_intent=True。
    运行时写入共享 flag 存储，所有后续请求立即生效，无需重启。
    """
    if not user_has_permission(role, "rollback"):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=403,
            content={'detail': f"permission_denied: role '{role}' cannot rollback"},
        )
    if version == "v1":
        set_feature_flag("use_llm_intent", False)
        set_feature_flag("use_history_in_prompt", False)
        set_feature_flag("active_version", "v1")
    else:
        set_feature_flag("use_llm_intent", True)
        set_feature_flag("active_version", version)
    log.info("rollback applied version=%s", version)
    flags = FeatureFlags()
    return {
        "status": "ok",
        "rolled_back_to": version,
        "use_llm_intent": flags.use_llm_intent,
        "active_version": flags.active_version,
    }

@router.get('/tickets-page')
def tickets_page():
    from fastapi.responses import FileResponse
    from config import BASE_DIR
    return FileResponse(BASE_DIR / 'static' / 'tickets.html')

# ============================================================
# 页面路由
# ============================================================
from config import BASE_DIR


@router.get("/monitoring-page")
def monitoring_page():
    from fastapi.responses import FileResponse
    return FileResponse(BASE_DIR / "static" / "monitoring.html")


@router.get("/evals-page")
def evals_page():
    from fastapi.responses import FileResponse
    return FileResponse(BASE_DIR / "static" / "evals.html")


@router.get("/sessions-page")
def sessions_page():
    from fastapi.responses import FileResponse
    return FileResponse(BASE_DIR / "static" / "sessions.html")


# ============================================================
# 评估接口
# ============================================================
@router.get("/run-eval")
def run_eval_api(with_badcase: int = 0):
    import json as _json
    from pathlib import Path as _P
    from eval.run_eval import load_dataset, run
    base = _P(__file__).resolve().parent.parent
    cases = load_dataset(base / "eval" / "dataset.jsonl")
    if with_badcase:
        cases.extend(load_dataset(base / "eval" / "badcase.jsonl"))
    metrics = run(cases)
    return metrics


@router.post("/collect-badcase")
def collect_badcase_api():
    from eval.collect_badcase import collect_badcases, merge_into_dataset
    collected = collect_badcases()
    merged = merge_into_dataset()
    return {"collected": collected, "merged": merged}


@router.get("/badcase-list")
def badcase_list_api():
    import json as _json
    from pathlib import Path as _P
    path = _P(__file__).resolve().parent.parent / "eval" / "badcase.jsonl"
    if not path.exists():
        return {"items": []}
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                items.append(_json.loads(line))
            except _json.JSONDecodeError:
                pass
    return {"items": items}


@router.get("/badcase-count")
def badcase_count_api():
    from pathlib import Path as _P
    path = _P(__file__).resolve().parent.parent / "eval" / "badcase.jsonl"
    if not path.exists():
        return {"count": 0}
    count = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return {"count": count}


# ============================================================
# 会话回放接口
# ============================================================
import sqlite3 as _sqlite3


@router.get("/sessions")
def list_sessions(limit: int = 50):
    db = Path(settings.SQLITE_PATH)
    if not db.exists():
        return {"sessions": []}
    conn = _sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT id, user_id, message, answer, created_at FROM sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return {"sessions": [
        {"id": r[0], "user_id": r[1], "message": r[2], "answer": r[3], "created_at": r[4]}
        for r in rows
    ]}


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    from fastapi.responses import JSONResponse
    db = Path(settings.SQLITE_PATH)
    if not db.exists():
        return JSONResponse(status_code=404, content={"detail": "no_db"})
    conn = _sqlite3.connect(str(db))
    try:
        s_row = conn.execute(
            "SELECT id, user_id, message, answer, created_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if s_row is None:
            return JSONResponse(status_code=404, content={"detail": "session_not_found"})
        a_rows = conn.execute(
            "SELECT question, answer, intent, confidence, created_ticket, trace, usage, created_at FROM audit_log WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    finally:
        conn.close()

    import json as _json
    messages = []
    audit = {}
    for r in a_rows:
        try:
            trace = _json.loads(r[5]) if r[5] else []
        except _json.JSONDecodeError:
            trace = []
        try:
            usage = _json.loads(r[6]) if r[6] else {}
        except _json.JSONDecodeError:
            usage = {}
        messages.append({"question": r[0], "answer": r[1], "created_at": r[7]})
        audit = {"intent": r[2], "confidence": r[3], "created_ticket": bool(r[4]),
                 "trace": trace, "usage": usage}
    return {
        "session": {"id": s_row[0], "user_id": s_row[1], "message": s_row[2],
                     "answer": s_row[3], "created_at": s_row[4]},
        "audit": audit,
        "messages": messages,
    }
