"""状态 schema：客服一线支撑 Agent 的输入 / 中间 / 输出 / 可追溯字段。"""
from dataclasses import dataclass
from typing import Annotated, Literal, TypedDict


def _add(left: list, right: list) -> list:
    return left + right


# 客服场景意图：退款 / 退货 / 补发 / 赔付 / 活动 / 转人工 / 需澄清
TicketIntent = Literal[
    "refund",
    "return",
    "reship",
    "compensate",
    "promo",
    "ticket",
    "clarify",
]

# 工单优先级
TicketPriority = Literal["urgent", "normal"]

# 工单分派团队
TicketTeam = Literal["aftersales", "quality", "ops", "general"]


class AgentState(TypedDict, total=False):
    # 业务输入
    question: str
    session_id: str
    user_id: str

    # 中间状态
    intent: TicketIntent
    retrieved_docs: list[dict]
    confidence: float

    # 客服场景新增：工单分级
    ticket_priority: TicketPriority
    ticket_team: TicketTeam

    # LLM 用量（token / 成本 / 延迟）
    llm_usage: dict

    # 多轮会话历史（最近 N 轮，裁剪后）
    history: list[dict]

    # 输出
    answer: str
    sources: list[dict]
    created_ticket: bool

    # 可追溯性（多节点追加）
    trace: Annotated[list[str], _add]


@dataclass
class TraceEntry:
    """单条 trace 记录：步骤名 + ISO8601 时间戳。"""

    step: str
    ts: str


def init_state(question: str, session_id: str, user_id: str) -> AgentState:
    """统一的 state 入口：保证所有字段都有初值，避免节点读到缺失键。"""
    return AgentState(
        question=question,
        session_id=session_id,
        user_id=user_id,
        intent="clarify",
        retrieved_docs=[],
        confidence=0.0,
        ticket_priority="normal",
        ticket_team="general",
        llm_usage={},
        history=[],
        answer="",
        sources=[],
        created_ticket=False,
        trace=[],
    )
