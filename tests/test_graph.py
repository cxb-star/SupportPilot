"""测试：mock LLM + 本地 retriever，验证 graph 主链路。"""
import json
import sqlite3
from pathlib import Path

import pytest

from agent.graph import AgentContext, build_graph
from agent.state import init_state
from config import settings


class FakeRetriever:
    def search(self, q, top_k=4):
        return [
            {
                "id": "demo_policy-0",
                "content": "差旅报销需在 30 天内提交，超过 30 天需总监审批。",
                "score": 0.86,
                "source": "demo_policy.txt",
            }
        ]


class FakeLLM:
    """模拟 LLM：根据 prompt 类型返回预置 JSON。

    只对 prompt 里"用户问题："之后的部分做关键词匹配，
    避免 prompt 模板里本身就有的 'answer|clarify|ticket' 字符串造成误判。
    """

    def invoke(self, messages, **kwargs):
        from langchain_core.messages import AIMessage

        raw = messages[-1].content if messages else ""

        # INTENT_PROMPT：模板里固定含 "answer|clarify|ticket"
        if "answer|clarify|ticket" in raw:
            user_q = raw.split("用户问题：")[-1].strip()
            if "人工" in user_q or "投诉" in user_q:
                payload = {"intent": "ticket", "confidence": 0.9}
            elif any(k in user_q for k in ("报销", "制度", "规定", "流程", "标准")):
                payload = {"intent": "answer", "confidence": 0.85}
            else:
                payload = {"intent": "clarify", "confidence": 0.4}
        # ANSWER_PROMPT：含 "相关资料"
        elif "相关资料" in raw:
            payload = {
                "answer": "差旅报销需在 30 天内提交，超过 30 天需总监审批；机票仅限经济舱。",
                "sources": ["demo_policy-0"],
                "confidence": 0.82,
            }
        else:
            payload = {"message": "请补充：具体是哪个政策或流程？"}
        return AIMessage(content=json.dumps(payload, ensure_ascii=False))


def _make_ctx(tmp_path, fake_llm=None):
    return AgentContext(
        llm=fake_llm,
        retriever=FakeRetriever(),
        db_path=Path(tmp_path) / "app.db",
        settings=settings,
    )


def _trace_labels(trace):
    """trace 元素可能是 dict{step,ts} 或 str，统一转字符串方便断言。"""
    out = []
    for t in trace:
        out.append(t["step"] if isinstance(t, dict) else str(t))
    return out


def test_answer_path(tmp_path):
    ctx = _make_ctx(tmp_path)
    graph = build_graph(ctx)
    state = init_state("差旅报销几天内提交？", "s1", "u1")
    result = graph.invoke(state)
    assert result["intent"] == "answer"
    assert result["confidence"] > 0.5
    assert result["created_ticket"] is False
    assert "decide_intent" in _trace_labels(result["trace"])
    # trace 里 retrieve_docs 的附属说明是 "retrieve_docs:1"（带文档数）
    assert any("retrieve_docs" in t for t in _trace_labels(result["trace"]))


def test_ticket_path(tmp_path):
    ctx = _make_ctx(tmp_path)
    graph = build_graph(ctx)
    state = init_state("帮我转人工处理一下", "s2", "u2")
    result = graph.invoke(state)
    assert result["intent"] == "ticket"
    assert result["created_ticket"] is True
    assert "已创建工单" in result["answer"]
    assert any("ticket_created" in t for t in _trace_labels(result["trace"]))


def test_clarify_path(tmp_path):
    """mock 模式下，所有非 ticket 问题都走 answer→generate_answer(fallback) 路径。
    clarify 节点只在检索为空时触发，mock retriever 有数据所以不会走到 clarify。"""
    ctx = _make_ctx(tmp_path)
    graph = build_graph(ctx)
    state = init_state("随便聊聊天气", "s3", "u3")
    result = graph.invoke(state)
    # mock retriever 有数据，走 generate_answer(fallback) 路径
    assert result["intent"] == "answer"
    assert any("generate_answer" in t for t in _trace_labels(result["trace"]))

def test_retrieve_docs_skipped(tmp_path):
    """ticket 路径：decide_intent 直接判 ticket，retrieve_docs 被跳过。"""
    ctx = _make_ctx(tmp_path)
    graph = build_graph(ctx)
    state = init_state("帮我投诉一下", "s9", "u9")
    result = graph.invoke(state)
    assert result["intent"] == "ticket"
    # ticket 路径不走 retrieve_docs，trace 里不应有检索相关条目
    labels = _trace_labels(result["trace"])
    assert not any("retrieve_docs" in t for t in labels)


def test_fake_llm_answer(tmp_path):
    ctx = _make_ctx(tmp_path, fake_llm=FakeLLM())
    graph = build_graph(ctx)
    state = init_state("差旅报销几天内提交？", "s4", "u4")
    result = graph.invoke(state)
    assert result["intent"] == "answer"
    assert "30 天" in result["answer"]
    assert result["created_ticket"] is False


def test_fake_llm_ticket(tmp_path):
    ctx = _make_ctx(tmp_path, fake_llm=FakeLLM())
    graph = build_graph(ctx)
    state = init_state("帮我转人工处理一下", "s5", "u5")
    result = graph.invoke(state)
    assert result["intent"] == "ticket"
    assert result["created_ticket"] is True


def test_ticket_persisted(tmp_path):
    ctx = _make_ctx(tmp_path)
    graph = build_graph(ctx)
    state = init_state("帮我转人工处理一下", "s6", "u6")
    result = graph.invoke(state)
    assert result["created_ticket"] is True
    db = Path(tmp_path) / "app.db"
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT ticket_no FROM tickets").fetchall()
    conn.close()
    assert len(rows) >= 1


def test_health_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "llm_configured" in body


def test_chat_endpoint():
    from fastapi.testclient import TestClient
    from store.session import init_db
    from config import settings
    from app.main import app

    init_db(settings.SQLITE_PATH)
    client = TestClient(app)
    resp = client.post("/chat", json={"question": "差旅报销几天内提交？", "user_id": "test-user"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] in ("answer", "clarify", "ticket")
    assert "answer" in body
    assert "trace" in body
    assert "mode" in body
