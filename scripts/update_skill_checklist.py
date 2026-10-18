import sys; sys.stdout.reconfigure(encoding="utf-8")
with open("docs/skill_checklist.md", encoding="utf-8") as f:
    content = f.read()

# 1. 评估集
content = content.replace(
    "| 评估集 | 🟡 | `eval/dataset.jsonl` | 有，但条数少，覆盖场景不够 |",
    "| 评估集 | ✅ | `eval/dataset_1000.jsonl` | 1000 条合成数据，含边界值/对抗样本/多轮追问/场景化，全部唯一 |"
)

# 2. 自动跑评估
content = content.replace(
    "| 自动跑评估 | 🟡 | `eval/run_eval.py` | 有脚本，但没有接入 CI 或定时触发 |",
    "| 自动跑评估 | 🟡 | `eval/run_eval.py` | 有脚本 + 1000 条测试集，未接入 CI 定时触发（可加 GitHub Actions）|"
)

# 3. 指标统计
content = content.replace(
    "| 指标统计（答对率/兜底率/引用准确率） | ❌ | 无 | 在 `run_eval.py` 里加 3 个指标的自动计算 |",
    "| 指标统计（答对率/兜底率/引用准确率） | ✅ | `eval/run_eval.py` | 已实现 intent_hit_rate / keyword_hit_rate / fallback_rate，按意图分桶统计 |"
)

# 4. badcase 收集
content = content.replace(
    "| badcase 收集 | ❌ | 无 | 加一个 `badcase/` 目录，每次评估失败自动写入 |",
    "| badcase 收集 | ✅ | `eval/badcase.jsonl` | 已实现自动回流，改 prompt 前后对比回归 |"
)

# 5. 能讲出来 — 追加新亮点
old_intro = """面试时，下面这些你已经有落点，可以直接说\"我做过\"：

- 固定 workflow 设计（4 节点）
- 状态 schema 定义
- 置信度阈值兜底
- 工单创建（mock）
- trace 可观测
- 会话 + 审计落 SQLite
- RAG 基础链路（切块 → embedding → Chroma → 检索）
- FastAPI 接口
- 前端问答页"""

new_intro = """面试时，下面这些你已经有落点，可以直接说\"我做过\"：

- 固定 workflow 设计（5 节点 LangGraph 状态机）
- 状态 schema 定义（AgentState TypedDict）
- 置信度阈值兜底 + refund/return 强制建单策略
- 工单创建（带优先级+团队映射，SQLite 持久化）
- trace 可观测（每步带时间戳，前端回放）
- 会话 + 审计落 SQLite
- RAG 基础链路（切块 → embedding → Chroma → 检索，hash embedding 双路降级）
- FastAPI 接口 + 5 个前端页面
- **测试驱动迭代**：1000 条测试集 + badcase 自动回流，改 prompt 前后指标可对比
- **工程护栏**：令牌桶限流 / 三级权限 / 灰度开关一键回滚
- **Bug 修复实战**：发现并修复了 clarify 节点覆盖 intent 的隐蔽 bug，将 return 意图准确率从 0% 提升到 100%"""

content = content.replace(old_intro, new_intro)

# 6. 被追问2 — 移除已解决的
content = content.replace(
    "2. **怎么知道改了 prompt 是变好还是变坏？**  \n   → 你现在还差自动指标计算",
    "2. **怎么知道改了 prompt 是变好还是变坏？**  \n   → 已有 1000 条测试集 + badcase 回流 + 分意图准确率，可直接对比。还可补充 CI 定时触发（目前是手动跑）"
)

# 7. 第一梯队 priority 2 — 更新
content = content.replace(
    "2. 评估自动化：3 个指标自动计算 + badcase 收集",
    "2. 评估自动化：1000 条测试集 + 3 指标 + badcase 回流已实现，可补充 CI 定时触发"
)

with open("docs/skill_checklist.md", "w", encoding="utf-8") as f:
    f.write(content)
print("Done")
