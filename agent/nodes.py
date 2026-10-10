"""Agent 节点：客服一线支撑场景，每个节点只做一件事，失败统一走 clarify/ticket 兜底。

路由：
  classify_intent → retrieve_docs → route_after_retrieve
  有资料 → generate_answer → ticket_if_needed
  无资料 → clarify → ticket_if_needed
  人工信号 → 直接 ticket_if_needed
"""
from datetime import datetime, timezone

from agent.prompts import ANSWER_PROMPT, CLARIFY_PROMPT, INTENT_PROMPT
from agent.state import AgentState
from agent.tools import create_ticket
from config import settings

from llm import LLMUnavailable, complete_structured

# 客服场景意图标签
_INTENTS = ("refund", "return", "reship", "compensate", "promo", "ticket", "clarify")

# 明确的“转人工”强信号；命中即走 ticket，不检索
_TICKET_SIGNALS = ("人工", "转人工", "建单", "投诉", "找客服", "找管理员", "升级", "找负责人")

# 意图 → 团队映射（与 tools.py 保持一致，节点侧也存一份方便 trace 展示）
_INTENT_TEAM = {
    "refund": "aftersales",
    "return": "aftersales",
    "reship": "aftersales",
    "compensate": "quality",
    "promo": "ops",
    "ticket": "general",
    "clarify": "general",
}
# LLM 意图分类输出的合法标签集合（用于校验，非法标签视为 LLM 失败回退）
_VALID_INTENTS = set(_INTENTS)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _steps(*items: str) -> list[dict]:
    out = []
    for i in items:
        out.append(i if isinstance(i, dict) else {"step": i, "ts": _ts()})
    return out

def _classify_intent_by_rules(question: str) -> dict:
    """规则版意图分类：无 LLM 或灰度回滚时使用。强信号直接 ticket，其余关键词匹配。"""
    q = question.lower()

    if any(s in q for s in _TICKET_SIGNALS):
        return {
            "intent": "ticket",
            "confidence": 1.0,
            "ticket_team": "general",
            "ticket_priority": "urgent",
            "trace": _steps("classify_intent", "intent=ticket(规则)"),
        }

    if any(w in q for w in ("退款", "退货", "退钱", "退掉")):
        intent = "refund" if "退" in q else "return"
    elif "补发" in q or "重新发" in q or "没收到" in q:
        intent = "reship"
    elif "破损" in q or "质量" in q or "赔偿" in q or "赔" in q:
        intent = "compensate"
    elif "活动" in q or "优惠" in q or "满减" in q or "促销" in q:
        intent = "promo"
    else:
        intent = "clarify"

    return {
        "intent": intent,
        "confidence": 0.0,
        "ticket_team": _INTENT_TEAM.get(intent, "general"),
        "ticket_priority": "urgent" if intent == "compensate" else "normal",
        "trace": _steps("classify_intent", f"intent={intent}(规则)"),
    }


def _classify_intent_by_llm(llm, state: AgentState) -> dict | None:
    """LLM 意图分类：调用 LLM 输出 JSON 意图标签。失败或无效输出返回 None，由调用方回退。"""
    if llm is None:
        return None
    try:
        result = complete_structured(
            llm,
            INTENT_PROMPT.format(question=state["question"]),
            ctx={"step": "classify_intent", "session_id": state["session_id"]},
        )
    except LLMUnavailable:
        return None

    data = result.data or {}
    intent = str(data.get("intent", "")).strip().lower()
    if intent not in _VALID_INTENTS:
        return None
    try:
        confidence = min(1.0, max(0.0, float(data.get("confidence", 0.0) or 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0

    # 强"转人工"信号即便 LLM 没识别，也强制 ticket，避免漏建单
    q = state["question"].lower()
    if intent != "ticket" and any(s in q for s in _TICKET_SIGNALS):
        intent = "ticket"
        confidence = 1.0

    return {
        "intent": intent,
        "confidence": confidence,
        "ticket_team": _INTENT_TEAM.get(intent, "general"),
        "ticket_priority": "urgent" if intent == "compensate" else "normal",
        "llm_usage": result.usage,
        "trace": _steps(
            "classify_intent",
            f"intent={intent}(LLM) conf={confidence:.2f} tokens={result.total_tokens}",
        ),
    }


def classify_intent(llm, state: AgentState) -> dict:
    """意图分类入口：灰度开关 use_llm_intent=True 时走 LLM，否则走规则版（回滚态）。

    LLM 路径失败/无效时自动回退到规则版，保证主链路不中断。
    """
    import guardrails
    flags = guardrails.FeatureFlags()

    if flags.use_llm_intent:
        llm_result = _classify_intent_by_llm(llm, state)
        if llm_result is not None:
            return llm_result
        # LLM 失败，回退规则
        fallback = _classify_intent_by_rules(state["question"])
        fallback["trace"] = fallback.get("trace", []) + ["classify_llm_fallback:rule"]
        return fallback

    return _classify_intent_by_rules(state["question"])

def retrieve_docs(retriever, state: AgentState) -> dict:
    """检索客服政策库；clarify / ticket 意图跳过检索。"""
    intent = state.get("intent", "clarify")
    if intent in ("ticket", "clarify"):
        return {"trace": _steps("retrieve_docs_skipped")}
    try:
        docs = retriever.search(state["question"], top_k=settings.RAG_TOP_K)
    except Exception:
        docs = []
    docs = [d for d in docs if d.get("score", 0.0) >= settings.RAG_MIN_SCORE]
    return {"retrieved_docs": docs, "trace": _steps(f"retrieve_docs:{len(docs)}")}


def route_after_retrieve(state: AgentState) -> str:
    """有检索结果 → 生成回答；没有 → 追问澄清。"""
    return "generate_answer" if state.get("retrieved_docs") else "clarify"


def clarify(llm, state: AgentState) -> dict:
    """检索为空或意图不明时，生成追问。"""
    delta: dict = {"intent": "clarify", "confidence": 0.0, "ticket_team": "general"}
    if llm is None:
        delta["answer"] = "请补充一下：是退款、退货、补发，还是质量问题？以便我给您准确的答复。"
    else:
        try:
            result = complete_structured(
                llm,
                CLARIFY_PROMPT.format(question=state["question"]),
                ctx={"step": "clarify", "session_id": state["session_id"]},
            )
            delta["answer"] = result.data.get("message", "请补充更多信息。")
            delta["llm_usage"] = result.usage
        except LLMUnavailable:
            delta["answer"] = "请补充一下：是退款、退货、补发，还是质量问题？"
    delta["trace"] = _steps("clarify")
    return delta


def generate_answer(llm, state: AgentState) -> dict:
    """基于检索结果生成答案，带引用来源、置信度和 token/成本统计。"""
    docs = state.get("retrieved_docs", [])
    sources = [
        {"id": d["id"], "source": d.get("source", ""), "score": d.get("score", 0.0)}
        for d in docs
    ]
    intent = state.get("intent", "clarify")

    if llm is None:
        top = docs[0] if docs else {}
        return {
            "intent": intent,
            "confidence": min(1.0, top.get("score", 0.0)),
            "answer": top.get("content", "资料不足，请补充更多细节或转人工处理。"),
            "sources": sources,
            "trace": _steps("generate_answer(fallback)"),
        }

    context = "\n\n".join(
        f"[来源{i + 1}] {d.get('source', d.get('id', ''))}: {d['content']}"
        for i, d in enumerate(docs)
    )
    # 多轮历史裁剪：取最近 3 轮，避免 token 溢出
    history = state.get("history", [])
    if history:
        h_lines = "\n".join(
            f"  用户: {h['question']}\n  助手: {h['answer']}"
            for h in history[-3:]
        )
        context = f"【历史对话】\n{h_lines}\n\n【相关资料】\n{context}"
    result = complete_structured(
        llm,
        ANSWER_PROMPT.format(context=context, question=state["question"]),
        ctx={"step": "generate_answer", "session_id": state["session_id"]},
    )
    data = result.data or {}
    answer = str(data.get("answer", "")).strip()
    confidence = min(1.0, max(0.0, float(data.get("confidence", 0.0) or 0.0)))

    if not answer:
        return {
            "intent": intent,
            "confidence": 0.0,
            "answer": "抱歉，回答服务暂时不可用，请补充问题细节或稍后再试。",
            "sources": sources,
            "llm_usage": result.usage,
            "trace": _steps("generate_answer_fallback"),
        }
    return {
        "intent": intent,
        "confidence": confidence,
        "answer": answer,
        "sources": sources,
        "llm_usage": result.usage,
        "trace": _steps(f"generate_answer tokens={result.total_tokens} cost=${result.cost_usd:.6f}"),
    }


def ticket_if_needed(db_path, state: AgentState) -> dict:
    """判断是否需要建工单；需要时带优先级和团队信息。"""
    intent = state.get("intent", "clarify")
    confidence = state.get("confidence", 0.0)
    ticket_team = state.get("ticket_team", "general")
    ticket_priority = state.get("ticket_priority", "normal")

    need_ticket = (
        intent in ("ticket", "clarify")
        or confidence < settings.CONFIDENCE_THRESHOLD
    )
    if not need_ticket:
        return {"trace": _steps("ticket_skipped")}

    ticket = create_ticket(
        db_path,
        state["user_id"],
        state["question"],
        intent=intent,
        priority=ticket_priority,
        team=ticket_team,
    )
    return {
        "created_ticket": True,
        "ticket_priority": ticket_priority,
        "ticket_team": ticket_team,
        "ticket_no": ticket["ticket_no"],
        "answer": f"已创建工单：{ticket['ticket_no']}（优先级：{ticket_priority}，团队：{ticket_team}），稍后会由人工继续跟进。",
        "trace": _steps(f"ticket_created:{ticket['ticket_no']} priority={ticket_priority} team={ticket_team}"),
    }
