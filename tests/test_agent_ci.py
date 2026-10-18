# -*- coding: utf-8 -*-
"""CI tests for agent intent classification."""
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
            {"id": "refund_policy-0", "content": "签收后 7 天内，商品完好未拆封，可申请全额退款。",
             "score": 0.82, "source": "refund_policy.txt"},
            {"id": "promo_faq-0", "content": "双11 满减：跨店满 300 减 50，满 600 减 100，可与店铺券叠加。",
             "score": 0.78, "source": "promo_faq.txt"},
        ]


def _make_ctx(tmp_path):
    return AgentContext(llm=None, retriever=FakeRetriever(),
                        db_path=Path(tmp_path) / "app.db", settings=settings)


def _trace_labels(trace):
    return [t["step"] if isinstance(t, dict) else str(t) for t in trace]


def test_intent_refund(tmp_path):
    g = build_graph(_make_ctx(tmp_path))
    r = g.invoke(init_state("订单12345能退款吗，买了3天", "s1", "u1"))
    assert r["intent"] == "refund"
    assert r["created_ticket"] is True


def test_intent_promo(tmp_path):
    g = build_graph(_make_ctx(tmp_path))
    r = g.invoke(init_state("双11满减规则是什么", "s2", "u2"))
    assert r["intent"] == "promo"
    assert r["created_ticket"] is False


def test_intent_compensate_urgent(tmp_path):
    g = build_graph(_make_ctx(tmp_path))
    r = g.invoke(init_state("收到的商品有破损，怎么赔", "s3", "u3"))
    assert r["intent"] == "compensate"
    assert r.get("ticket_priority") == "urgent"


def test_intent_ticket_signal(tmp_path):
    g = build_graph(_make_ctx(tmp_path))
    r = g.invoke(init_state("帮我转人工处理一下", "s4", "u4"))
    assert r["intent"] == "ticket"
    assert r["created_ticket"] is True


def test_intent_return(tmp_path):
    g = build_graph(_make_ctx(tmp_path))
    r = g.invoke(init_state("我要退货，商品尺码不对", "s_ret", "u_ret"))
    assert r["intent"] == "return"
    assert r["created_ticket"] is True


def test_intent_clarify_fallback(tmp_path):
    g = build_graph(_make_ctx(tmp_path))
    r = g.invoke(init_state("随便聊聊天气", "s5", "u5"))
    assert r["intent"] == "clarify"
    assert r["created_ticket"] is True


def test_ticket_created_in_db(tmp_path):
    g = build_graph(_make_ctx(tmp_path))
    r = g.invoke(init_state("帮我转人工", "s6", "u6"))
    assert r["created_ticket"] is True
    conn = sqlite3.connect(str(Path(tmp_path) / "app.db"))
    count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    conn.close()
    assert count >= 1


def test_ticket_has_team_and_priority(tmp_path):
    g = build_graph(_make_ctx(tmp_path))
    r = g.invoke(init_state("收到的商品有破损，怎么赔", "s7", "u7"))
    assert r.get("ticket_team") == "quality"
    assert r.get("ticket_priority") == "urgent"


def test_history_in_state(tmp_path):
    ctx = _make_ctx(tmp_path)
    g = build_graph(ctx)
    state = init_state("双11满减规则是什么", "s8", "u8")
    state["history"] = [
        {"question": "退款规则", "answer": "7天内可退"},
        {"question": "满减规则", "answer": "满300减50"},
    ]
    result = g.invoke(state)
    assert "llm_usage" in result


def test_trace_contains_all_nodes(tmp_path):
    g = build_graph(_make_ctx(tmp_path))
    r = g.invoke(init_state("双11满减规则是什么", "s9", "u9"))
    labels = _trace_labels(r["trace"])
    assert any("classify_intent" in t for t in labels)
    assert any("retrieve_docs" in t for t in labels)
    assert any("generate_answer" in t for t in labels)
