"""LLM 意图分类路径的 CI 测试：用 mock LLM，不依赖真实 OpenAI/DeepSeek。

验证：
- 灰度开关 use_llm_intent=True 且 LLM 可用时走 LLM 路径
- LLM 有效输出被采纳（意图/置信度）
- LLM 无效输出自动回退到规则版，主链路不断
- LLM 低置信度仍按阈值兜底建工单
- 灰度关闭 → 纯规则，LLM 路径不被调用
"""
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
    """非 None 的占位 LLM，让 LLM 意图分支真正执行（complete_structured 会被 patch）。"""
    pass


def _ctx(tmp_path, llm=None):
    return AgentContext(llm=llm, retriever=FakeRetriever(),
                       db_path=Path(tmp_path) / "app.db", settings=settings)


def _patch_nodes(monkeypatch, intent, confidence):
    """让节点内调用的 complete_structured 返回指定意图。

    节点内以模块级名 `complete_structured` 调用，所以 patch agent.nodes 模块属性。
    """
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
    """让节点内 `import guardrails; guardrails.FeatureFlags()` 构造的实例带指定开关。"""
    import guardrails
    _orig = guardrails.FeatureFlags

    class _Patched(_orig):
        def __init__(self):
            super().__init__()
            self.use_llm_intent = use_llm

    monkeypatch.setattr(guardrails, "FeatureFlags", _Patched)


def test_llm_intent_used_when_flag_on(tmp_path, monkeypatch):
    """灰度开启 + LLM 可用 + 有效输出 → 采纳 LLM 意图（覆盖规则结果）。"""
    _patch_flags(monkeypatch, True)
    # 规则版会把"双11满减"判为 promo；让 LLM 判成 refund，验证确实走了 LLM 路径
    _patch_nodes(monkeypatch, "refund", 0.9)
    g = build_graph(_ctx(tmp_path, llm=FakeLLM()))
    r = g.invoke(init_state("双11满减规则是什么", "s1", "u1"))
    assert r["intent"] == "refund"


def test_llm_invalid_falls_back_to_rules(tmp_path, monkeypatch):
    """灰度开启 + LLM 无效输出（不在合法标签集）→ 回退规则版，链路不断。"""
    _patch_flags(monkeypatch, True)
    _patch_nodes(monkeypatch, "not_a_real_intent", 0.99)
    g = build_graph(_ctx(tmp_path, llm=FakeLLM()))
    r = g.invoke(init_state("双11满减规则是什么", "s2", "u2"))
    # 回退到规则：promo
    assert r["intent"] == "promo"


def test_llm_confidence_low_creates_ticket(tmp_path, monkeypatch):
    """灰度开启 + LLM 低置信度 → 仍按阈值兜底建工单。"""
    _patch_flags(monkeypatch, True)
    _patch_nodes(monkeypatch, "clarify", 0.1)
    g = build_graph(_ctx(tmp_path, llm=FakeLLM()))
    r = g.invoke(init_state("随便聊聊天气", "s3", "u3"))
    assert r["created_ticket"] is True


def test_flag_off_uses_rules_only(tmp_path, monkeypatch):
    """默认灰度关闭 → 走规则意图，LLM 意图路径不被调用（但答案生成仍用 LLM）。"""
    _patch_flags(monkeypatch, False)
    import agent.nodes as nodes
    # 让 complete_structured 始终返回 clarify 意图（模拟 LLM 答案生成可用），
    # 如果误走 LLM 意图路径，会把 intent 设成 clarify，而规则版对"破损"会判 compensate
    monkeypatch.setattr(
        nodes, "complete_structured",
        lambda llm, prompt, **kw: LLMResult(text="{}", data={"intent":"clarify","confidence":0.1}, total_tokens=5),
    )
    g = build_graph(_ctx(tmp_path, llm=FakeLLM()))
    r = g.invoke(init_state("收到的商品有破损，怎么赔", "s4", "u4"))
    # 规则版：compensate；LLM 意图路径若被误触发：clarify。断言规则结果。
    assert r["intent"] == "compensate"
