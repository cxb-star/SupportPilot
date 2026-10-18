# -*- coding: utf-8 -*-
"""LLM intent classification CI tests."""
from pathlib import Path

from agent.graph import AgentContext, build_graph
from agent.state import init_state
from config import settings
from llm import LLMResult


class FakeRetriever:
    def search(self, q, top_k=4):
        return [
            {"id": "refund_policy-0", "content": "签收后 7 天内，商品完好未拆封，可申请全额退款。",
             "score": 0.82, "source": "refund_policy.txt"},
        ]


class FakeLLM:
    pass


def _ctx(tmp_path, llm=None):
    return AgentContext(llm=llm, retriever=FakeRetriever(),
                       db_path=Path(tmp_path) / "app.db", settings=settings)


def _patch_nodes(monkeypatch, intent, confidence):
    import agent.nodes as nodes
    monkeypatch.setattr(
        nodes, "complete_structured",
        lambda llm, prompt, **kw: LLMResult(
            text="{}",
            data={"intent": intent, "confidence": confidence},
            total_tokens=10,
        ),
    )


def _patch_flags(monkeypatch, use_llm):
    import guardrails
    _orig = guardrails.FeatureFlags

    class _Patched(_orig):
        def __init__(self):
            super().__init__()
            self.use_llm_intent = use_llm

    monkeypatch.setattr(guardrails, "FeatureFlags", _Patched)


def test_llm_intent_used_when_flag_on(tmp_path, monkeypatch):
    _patch_flags(monkeypatch, True)
    _patch_nodes(monkeypatch, "refund", 0.9)
    g = build_graph(_ctx(tmp_path, llm=FakeLLM()))
    r = g.invoke(init_state("双11满减规则是什么", "s1", "u1"))
    assert r["intent"] == "refund"


def test_llm_invalid_falls_back_to_rules(tmp_path, monkeypatch):
    _patch_flags(monkeypatch, True)
    _patch_nodes(monkeypatch, "not_a_real_intent", 0.99)
    g = build_graph(_ctx(tmp_path, llm=FakeLLM()))
    r = g.invoke(init_state("双11满减规则是什么", "s2", "u2"))
    assert r["intent"] == "promo"


def test_llm_confidence_low_creates_ticket(tmp_path, monkeypatch):
    _patch_flags(monkeypatch, True)
    _patch_nodes(monkeypatch, "clarify", 0.1)
    g = build_graph(_ctx(tmp_path, llm=FakeLLM()))
    r = g.invoke(init_state("随便聊聊天气", "s3", "u3"))
    assert r["created_ticket"] is True


def test_flag_off_uses_rules_only(tmp_path, monkeypatch):
    _patch_flags(monkeypatch, False)
    import agent.nodes as nodes
    monkeypatch.setattr(
        nodes, "complete_structured",
        lambda llm, prompt, **kw: LLMResult(text="{}", data={"intent":"clarify","confidence":0.1}, total_tokens=5),
    )
    g = build_graph(_ctx(tmp_path, llm=FakeLLM()))
    r = g.invoke(init_state("收到的商品有破损，怎么赔", "s4", "u4"))
    assert r["intent"] == "compensate"
