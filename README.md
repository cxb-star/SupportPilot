<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-blue" />
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115-0095e6?logo=fastapi&amp;logoColor=white" />
  <img alt="LangGraph" src="https://img.shields.io/badge/LangGraph-0.3-6f42c1" />
  <img alt="Vector DB" src="https://img.shields.io/badge/Vectordb-Chroma-cc1830?logo=chroma&amp;logoColor=white" />
  <img alt="CI" src="https://github.com/cxb-star/SupportPilot/actions/workflows/ci.yml/badge.svg" />
</p>

# SupportPilot · 客服一线支撑 Agent（全流程自研）

一个企业知识库 / 客服一线支撑 Agent，跑在 FastAPI + LangGraph 上。
它不是"套壳聊天框"，而是一条完整的业务闭环：

意图判断 → 检索 → 生成答案 → 置信度校验 → 兜底建单 → 会话/审计/评估落库。

## 它解决什么问题

客服一线高频场景（退款、退货、补发、质量赔付、活动规则、转人工）。
系统保证三件事：**不编造**（检索不到就追问，绝不硬答）、**可兜底**
（低置信度/需人工自动建工单）、**可追溯**（每步都有 trace、审计、指标）。

## 主链路

```
用户提问
   │
   ▼
classify_intent ──── 命中"转人工"强信号 ──────────────┐
   │ (规则版 / LLM 版，灰度可回滚)                      │
   ▼                                                   │
retrieve_docs  (Chroma 向量检索)                       │
   │                                                   │
   ├─ 有资料 → generate_answer (LLM + 引用来源 + 置信度) │
   └─ 无资料 → clarify (LLM 生成追问)                   │
   │                                                   │
   ▼                                                   ▼
ticket_if_needed  ← 低置信度 / clarify / ticket 都进来
   │
   ├─ 需要 → create_ticket (写 SQLite，带优先级+团队)
   └─ 不需要 → 直接返回答案
   │
   ▼
持久化 sessions / audit_log / 指标 + 可评估集回流
```

## 亮点（值得看的设计判断）

- **双版本意图分类，灰度可回滚**：规则版零 LLM 成本、离线可跑；LLM 版输出
  JSON 意图+置信度。`USE_LLM_INTENT=1` 切换，LLM 失败/输出非法自动回退规则版。
- **不编造兜底**：检索为空走 `clarify` 追问；LLM 全程失败有固定兜底文案，不崩。
- **工单分级**：意图 → 团队（售后/质量/运营）+ 优先级（urgent/normal）自动映射。
- **自研可观测层**（不上 Prometheus）：直接读 SQLite 出 `/metrics` + `alerts` 表 + 健康检查。
- **评估闭环**：`run_eval` 真跑 graph 算意图命中率/关键词命中/兜底正确率，
  `collect_badcase` 把低置信度/失败请求回流进评估集，支持回归。
- **工程护栏**：角色权限、内存令牌桶限流、灰度开关 + 一键回滚。

## 快速开始

```bash
cd agent_knowledge_self_built
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt

python -m scripts.seed_documents   # 生成示例知识库
python -m rag.ingest_main         # 入库到 Chroma
python -m app.main                 # 启动，访问 http://127.0.0.1:8000
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
| `SQLITE_PATH` / `CHROMA_PERSIST_DIR` | 默认 `./data/app.db` / `./data/chroma` |

### 测试与评估（无需真实 LLM）

```bash
python -m pytest tests/ -v        # 9 CI + 4 LLM 意图，全 mock
python -m eval.run_eval           # mock 模式跑评估集
```

## API 端点总览

| 方法 路径 | 作用 |
|------|------|
| `POST /chat` | 主问答入口（限流、会话、审计、trace） |
| `GET /health` | 健康检查 + LLM/Embedding 是否配置 |
| `GET /tickets?status=&team=` | 工单查询；`POST /tickets/{no}/status` 改状态 |
| `GET /metrics` | 核心指标（工单/成本/置信度/告警） |
| `GET /alerts` · `POST /alerts/webhook` | 告警查询 / 外部告警入口 |
| `GET /feature-flags` · `POST /rollback` | 查看灰度开关 / 一键回滚 v1 |
| `GET /run-eval?with_badcase=` | 跑评估；`POST /collect-badcase` 回流 |
| `GET /sessions` · `GET /sessions/{id}` | 会话列表 / 单会话回放 + 审计 |
| `/` `/tickets-page` `/monitoring-page` `/evals-page` `/sessions-page` | 前端页面 |

## 目录结构

```
agent/        LangGraph 节点、状态 schema、图构建（意图/检索/生成/兜底）
rag/          Chroma 向量检索 + 文档切块入库
app/          FastAPI 入口 + 全部路由
store/        SQLite 持久化（会话/工单/审计）
guardrails.py 权限 / 限流 / 灰度开关
monitoring.py 指标 / 告警 / 健康检查端点
eval/         评估集 + 评估脚本 + badcase 回流
scripts/      seed_documents / health_check
static/       5 个前端页面（问答/工单/监控/评估/会话回放）
```

## 深入文档

- [项目手册](docs/project_playbook.md) — 从 0 到生产的完整设计思路
- [上线检查清单](docs/go_live_checklist.md) — 必须/应该/可以三级
- [技能自查表](docs/skill_checklist.md) — 当前能力盘点 + 待补项

> ⚠️ 现状说明：意图分类默认规则版，工单为本地 SQLite mock（未接真实工单系统），
> 检索为单路向量（未加混合检索/rerank），暂无用户鉴权。真实数据（会话/工单/评估集）
> 需随业务运行积累，当前为示例数据。详见[上线清单](docs/go_live_checklist.md)。