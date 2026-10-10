"""依赖注入容器 + graph 构建器（客服一线支撑 Agent）。

路由：
  classify_intent
    - ticket → ticket_if_needed → END
    - 其余  → retrieve_docs
                 - 有资料 → generate_answer → ticket_if_needed → END
                 - 无资料 → clarify → ticket_if_needed → END
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from langchain_openai import ChatOpenAI

from agent.nodes import (
    classify_intent,
    clarify,
    generate_answer,
    retrieve_docs,
    route_after_retrieve,
    ticket_if_needed,
)
from agent.state import AgentState
from compat import ensure_langchain_compat
from config import Settings, settings as default_settings
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver


def get_checkpointer(cp_path: Path) -> SqliteSaver:
    import sqlite3
    cp_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(cp_path), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


from llm import build_llm
from rag.retriever import Retriever, get_retriever

ensure_langchain_compat()


@dataclass
class AgentContext:
    llm: Optional[ChatOpenAI]
    retriever: Retriever
    db_path: Path
    settings: Settings

    @classmethod
    def default(cls) -> "AgentContext":
        return cls(
            llm=build_llm(),
            retriever=get_retriever(),
            db_path=default_settings.SQLITE_PATH,
            settings=default_settings,
        )


def build_graph(ctx: AgentContext, checkpointer=None):
    graph = StateGraph(AgentState)

    graph.add_node("classify_intent", lambda s: classify_intent(ctx.llm, s))
    graph.add_node("retrieve_docs", lambda s: retrieve_docs(ctx.retriever, s))
    graph.add_node("generate_answer", lambda s: generate_answer(ctx.llm, s))
    graph.add_node("clarify", lambda s: clarify(ctx.llm, s))
    graph.add_node("ticket_if_needed", lambda s: ticket_if_needed(ctx.db_path, s))

    graph.set_entry_point("classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        lambda s: "ticket" if s["intent"] == "ticket" else "retrieve_docs",
        {"ticket": "ticket_if_needed", "retrieve_docs": "retrieve_docs"},
    )
    graph.add_conditional_edges(
        "retrieve_docs",
        route_after_retrieve,
        {"generate_answer": "generate_answer", "clarify": "clarify"},
    )
    graph.add_edge("generate_answer", "ticket_if_needed")
    graph.add_edge("clarify", "ticket_if_needed")
    graph.add_edge("ticket_if_needed", END)

    return graph.compile(checkpointer=checkpointer)


def get_agent_context() -> AgentContext:
    return AgentContext.default()
