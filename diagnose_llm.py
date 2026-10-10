"""临时诊断脚本：直接跑 graph，验证方向 A 的完整链路。"""
import json
import os
from dotenv import load_dotenv
load_dotenv(".env")

from compat import ensure_langchain_compat
ensure_langchain_compat()

from agent.graph import AgentContext, build_graph
from agent.state import init_state

ctx = AgentContext.default()
graph = build_graph(ctx)

CASES = [
    ("差旅报销几天内提交？", "期望: answer + 有来源 + conf<1"),
    ("帮我转人工处理一下", "期望: ticket + 建单"),
    ("随便聊聊天气", "期望: clarify(检索不到) + 建单兜底"),
    ("住宿标准怎么执行？", "期望: answer + 有来源"),
]

for question, note in CASES:
    state = init_state(question, "diag", "diag-user")
    r = graph.invoke(state)
    print("=" * 60)
    print("Q :", question)
    print("说明:", note)
    print("intent=%s conf=%.2f ticket=%s mode=api" % (
        r["intent"], r["confidence"], r["created_ticket"]))
    print("sources=%d trace=%s" % (len(r["sources"]), ", ".join(r["trace"])))
    print("answer=", r["answer"][:80])
