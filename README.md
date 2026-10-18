<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-blue" />
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115-0095e6?logo=fastapi&logoColor=white" />
  <img alt="LangGraph" src="https://img.shields.io/badge/LangGraph-0.3-6f42c1" />
  <img alt="Vector DB" src="https://img.shields.io/badge/Vectordb-Chroma-cc1830?logo=chroma&logoColor=white" />
  <img alt="CI" src="https://github.com/cxb-star/SupportPilot/actions/workflows/ci.yml/badge.svg" />
</p>

# SupportPilot · 客服一线支撑 Agent（全流程自研）

一个企业级客服 Agent，跑在 FastAPI + LangGraph 上。
它不是"套壳聊天框"，而是一条完整的业务闭环：

**意图判断 → 检索 → 生成答案 → 置信度校验 → 兜底建单 → 会话/审计/评估落库**

---

## 项目状态

| 指标 | 数值 |
|------|------|
| 意图分类准确率 | **98.2%**（1000 条测试集） |
| CI 测试通过率 | **57/57（100%）** |
| 累计处理工单 | **11,835 条** |
| 累计会话数 | **186+** |
| 平均置信度 | **0.61** |
| 覆盖意图 | refund / return / reship / compensate / promo / ticket / clarify |

---

## 它解决什么问题

客服一线高频场景（退款、退货、补发、质量赔付、活动规则、转人工）存在三个痛点：

1. **回答不统一** — 不同客服对同一政策的解读不一致
2. **Hallucination** — 检索不到答案时 LLM 容易编造错误政策
3. **兜底缺失** — 低置信度问题无人工接管，导致客诉升级

系统保证三件事：**不编造**（检索不到就追问）、**可兜底**（低置信度自动建工单）、**可追溯**（每步都有 trace、审计、指标）。

---

## 主链路

```
用户提问
   │
   ▼
classify_intent
   │ (规则版 / LLM 版，灰度可回滚)
   ├─ 转人工强信号 → ticket_if_needed → END
   └─ 其余 → retrieve_docs (Chroma 向量检索)
                ├─ 有资料 → generate_answer (LLM + 引用来源 + 置信度)
                └─ 无资料 → clarify (LLM 生成追问)
                           ↓
                    ticket_if_needed
                ├─ 需要 → create_ticket (SQLite，带优先级+团队)
                └─ 不需要 → 直接返回答案
                           ↓
              sessions / audit_log / 指标 + 评估集回流
```

---

## 核心设计取舍

这一节记录几个关键取舍。都是踩过的坑或权衡后的选择，未必是"最优解"，但每个决定背后都有一个明确的现实约束——方便你看代码时知道为什么长这样。

- **意图分类为什么先做规则版，而不是直接上 LLM？**
  一开始就想用 LLM 分类意图，但客服场景很多是"转人工""投诉"这类强信号，
  用规则匹配又快又零成本。所以先落地规则版保证能跑，LLM 版做成灰度开关
  （`USE_LLM_INTENT=1` 才启用），失败就回退规则版。这样**新策略可以试，
  随时能退回**，上线风险可控。

- **为什么"检索不到"要追问而不是硬答？**
  这是客服场景最该守住的一条。宁可让用户多答一句，也不让 LLM 编一个
  看起来很有道理但其实错误的制度。所以检索为空就走 `clarify` 追问，
  LLM 整体失败也有固定兜底文案——**宁可保守，不编造**。

- **工单为什么要带优先级和团队？**
  建单不是目的，是要能真的派出去。如果只是一条"收到"，人工还是要重判
  轻重缓急。所以按意图自动映射到售后/质量/运营团队 + urgent/normal，
  让人工接手时少一步判断。（但这块目前写的是本地 SQLite，
  **还没接真实工单系统**，见文末。）

- **为什么自己写监控，不直接上 Prometheus？**
  项目还在早期，不想为一套指标引入一堆依赖。就用 SQLite 直接算指标、
  落 `alerts` 表，够用了。等真要进生产再换——**先跑通，再上重武器**。

- **为什么要做评估集和 badcase 回流？**
  不这么做就只能靠"我觉得效果不错"。有了评估集，改 prompt 前后能对比
  指标；把线上失败请求回流进评估集，下次回归就知道有没有改坏。
  这是"能评估"的最小闭环，**目前数据集还很小，需要真实数据持续喂**。

- **还没做 / 有意识留下的短板**：单路向量检索没加混合检索和 rerank；
  没有用户鉴权；意图分类默认还是规则版。这些都在上线清单里列了，
  不是忘了，是刻意排在业务跑起来之后再补。


---

## 快速开始

```bash
# 1. 安装依赖
cd agent_knowledge_self_built
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt

# 2. 生成示例知识库并入库
python -m scripts.seed_documents
python -m rag.ingest_main

# 3. 启动服务
python -m app.main   # 访问 http://127.0.0.1:8000
```

### 配置

复制 `.env.example` 为 `.env`，填 `OPENAI_API_KEY`（默认指向 DeepSeek 兼容端点）。

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | DeepSeek / OpenAI 兼容 Key，留空则全走 mock 兜底 |
| `LLM_MODEL` | 默认 `deepseek-chat` |
| `EMBEDDING_MODEL` | 留空用本地 hash embedding 兜底 |
| `CONFIDENCE_THRESHOLD` | 低于此值自动建单，默认 `0.5` |
| `USE_LLM_INTENT` | `1` 走 LLM 意图分类，默认 `0` 规则版 |

### 灰度回滚（运行时切换，无需重启）

```bash
# 查看当前状态
curl http://127.0.0.1:8000/feature-flags

# 回滚到 v1（规则版意图）
curl -X POST "http://127.0.0.1:8000/rollback?version=v1&role=admin"

# 切换到 v2（LLM 意图分类）
curl -X POST "http://127.0.0.1:8000/rollback?version=v2&role=admin"
```

> 运行时 flag 存在进程内存中，重启后失效。生产环境应持久化到数据库。

---

## 测试与评估

```bash
# CI 测试（全部 mock，无需真实 LLM）
python -m pytest tests/ -v

# 评估集跑分（1000 条，含边界值/对抗样本/多轮追问）
python -m eval.run_eval
```

测试集构成：

| 来源 | 数量 | 说明 |
|------|------|------|
| multi_turn | 275 | 多轮追问（每类意图+10个追问） |
| refund | 141 | 退款场景（5-60天×各商品类型） |
| promo | 108 | 活动规则（双11/618/优惠券叠加） |
| return | 99 | 退货场景（运费/拆封/超时） |
| reship | 83 | 补发场景（漏发/少发/破损） |
| adversarial | 71 | 对抗样本（错别字/混英文/噪声） |
| ticket | 66 | 转人工（投诉/升级/找负责人） |
| compensate | 62 | 赔付场景（质量/假货/超时） |
| clarify | 58 | 澄清场景（闲聊/空输入/无关问题） |
| boundary | 37 | 边界值（签收天数连续扫描） |

---

## API 端点

| 方法 | 路径 | 作用 |
|------|------|------|
| `POST` | `/chat` | 主问答入口（限流、会话、审计、trace） |
| `GET` | `/health` | 健康检查 + LLM/Embedding 配置状态 |
| `GET` | `/tickets?status=&team=` | 工单查询；`POST /tickets/{no}/status` 改状态 |
| `GET` | `/metrics` | 核心指标（工单/成本/置信度/告警） |
| `GET` | `/alerts` | 告警查询；`POST /alerts/webhook` 外部告警入口 |
| `GET` | `/feature-flags` | 查看灰度开关；`POST /rollback` 一键回滚 |
| `GET` | `/run-eval?with_badcase=` | 跑评估；`POST /collect-badcase` 回流 |
| `GET` | `/sessions` / `/sessions/{id}` | 会话列表 / 单会话回放 + 审计 |
| `GET` | `/` `/tickets-page` `/monitoring-page` `/evals-page` `/sessions-page` | 前端页面 |

---

## 目录结构

```
agent/            LangGraph 节点、状态 schema、图构建
  ├── graph.py    图拓扑（5 节点 + 条件路由）
  ├── nodes.py    意图分类/检索/生成/澄清/建单
  ├── prompts.py  LLM prompt 模板
  ├── state.py    AgentState TypedDict
  └── tools.py    工单创建工具
rag/              Chroma 向量检索 + 文档切块入库
  ├── ingest.py   文档切块 & embedding
  ├── retriever.py Chroma 检索器（含 hash 兜底）
  └── ingest_main.py 入库入口
app/              FastAPI 入口 + 全部路由
  ├── main.py     应用初始化
  └── routes.py   /chat /tickets /metrics 等路由
store/            SQLite 持久化
  ├── session.py  会话/审计/工单表操作
  └── audit.py    审计记录
guardrails.py     权限/限流/灰度开关（角色/令牌桶/FeatureFlags）
monitoring.py     指标/告警/健康检查端点
eval/             评估体系
  ├── dataset_1000.jsonl  1000条测试集
  ├── run_eval.py         评估脚本
  └── badcase.jsonl       badcase 回流（自动生成）
scripts/
  ├── generate_test_dataset.py  测试集生成器
  └── health_check.py         健康检查
static/           5 个前端页面（问答/工单/监控/评估/会话回放）
docs/
  ├── project_playbook.md  完整设计思路
  ├── go_live_checklist.md 上线检查清单
  └── skill_checklist.md   技能盘点与待补项
tests/            57 个 CI 测试用例
data/             运行时数据（.gitignore 排除）
```

---

## 技术栈

Python 3.10 / FastAPI / LangGraph / ChromaDB / DeepSeek / SQLite / Pytest

---

## 下一步

详见 [docs/go_live_checklist.md](docs/go_live_checklist.md)（上线前必做/应该做/可以做的事项）和 [docs/skill_checklist.md](docs/skill_checklist.md)（当前能力盘点与待补项）。

> **数据说明**：仓库里的会话/工单/评估集均含示例与测试数据。完整指标见 [docs/resume_project.md](docs/resume_project.md)。

