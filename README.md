# agent_knowledge_self_built

全流程自研企业知识库 Agent：意图判断 → 检索 → 回答 → 工单兜底，含持久化、审计、评估。

## 快速开始

```bash
cd agent_knowledge_self_built
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
python -m scripts.seed_documents   # 生成 docs/demo_policy.txt
python -m rag.ingest_main          # 把 docs/*.txt 入库到 Chroma
python -m app.main                 # 启动 FastAPI 服务
```

访问：`http://127.0.0.1:8000`

### 测试与评估

```bash
python -m pytest
python -m eval.run_eval
```

## 配置

复制 `.env.example` 为 `.env` 并填入你的密钥：

```bash
cp .env.example .env
```

关键项：

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | DeepSeek / OpenAI 兼容 API Key |
| `OPENAI_BASE_URL` | 默认 `https://api.deepseek.com/v1` |
| `LLM_MODEL` | 默认 `deepseek-chat` |
| `EMBEDDING_MODEL` | 留空则使用本地 hash embedding 兜底 |
| `CHROMA_PERSIST_DIR` | 向量库路径，默认 `./data/chroma` |
| `SQLITE_PATH` | 会话/工单/审计数据库，默认 `./data/app.db` |
| `CONFIDENCE_THRESHOLD` | 低于此值自动建单，默认 `0.5` |
| `USE_LLM_INTENT` | 意图分类灰度开关：`1` 走 LLM 意图分类（新），默认 `0` 走规则版（可回滚） |

## 目录结构

## 意图分类：规则版 + LLM 版（灰度可回滚）

主链路入口 `classify_intent` 支持两种实现，由灰度开关控制，生产可一键回滚：

- **规则版（默认）**：关键词/强信号匹配，零 LLM 成本，离线可跑。转人工强信号直接建单。
- **LLM 版**：调用 LLM 输出 JSON 意图标签（refund/return/reship/compensate/promo/ticket/clarify）
  + 置信度。输出不在合法标签集、或 LLM 调用失败时，自动回退到规则版，主链路不中断。

```bash
USE_LLM_INTENT=1 python -m app.main   # 启用 LLM 意图分类
```

对应的灰度回滚接口：`GET /feature-flags` 查看当前开关，`POST /rollback` 切回 v1（规则版）。


```
agent/       LangGraph 节点、状态、图构建
  state.py   AgentState 定义
  graph.py   图 + AgentContext（依赖注入）
  nodes.py   各节点实现
  tools.py   create_ticket / log_trace
rag/
  ingest.py      文档切块
  ingest_main.py 入库入口
  retriever.py   向量检索
app/
  main.py    FastAPI 入口
  routes.py  /chat /health
store/
  session.py  SQLite 持久化
eval/
  dataset.jsonl  评估集
  run_eval.py    评估脚本
scripts/
  seed_documents.py  生成示例文档
```

## 测试

```bash
python -m pytest tests/ -v
```
