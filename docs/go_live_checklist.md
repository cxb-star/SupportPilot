# 企业知识库 Agent — 上线检查清单

> 项目当前已具备完整骨架。以下按"必须 / 应该 / 可以"三级列出上线前要做的事。

---

## 第一级：必须（不做就不能上线）

### 1. 真实密钥与模型
- [ ] `.env` 里填入真实 `OPENAI_API_KEY`（DeepSeek）
- [ ] 确认 `OPENAI_BASE_URL` = `https://api.deepseek.com/v1`
- [ ] 确认 `LLM_MODEL` = `deepseek-chat`
- [ ] 跑一次 `python -m eval.run_eval`，确认 intent hit rate > 0.8
- [ ] 确认日志里没有 `401` / `llm_call_failed`

### 2. 知识库内容
- [ ] 把真实公司制度文件放进 `docs/`（.txt 格式）
- [ ] 跑 `python -m rag.ingest_main` 完成入库
- [ ] 至少准备 10 条以上真实业务文档，不只是 `demo_policy.txt`
- [ ] 确认 `chromadb` collection 里有数据：查 `data/chroma/` 目录非空

### 3. 兜底策略
- [ ] 确认 `CONFIDENCE_THRESHOLD` 值符合业务要求（默认 0.5）
- [ ] 测试：问一个完全无关的问题，确认走 clarify 路径
- [ ] 测试：问"转人工"，确认走 ticket 路径且 `created_ticket=true`
- [ ] 测试：把 `OPENAI_API_KEY` 清空再跑一次，确认系统不崩、返回兜底文案

### 4. 审计与会话
- [ ] 跑一次 `/chat`，查 `data/app.db`：`sessions` 表有记录
- [ ] `audit_log` 表有记录，`trace` 字段是 JSON 数组
- [ ] 工单场景：`tickets` 表有记录，`ticket_no` 是真实的

---

## 第二级：应该（影响产品体验）

### 5. 前端展示
- [ ] 打开 `http://127.0.0.1:8000`，确认新前端正常渲染
- [ ] 确认"回答 / 状态 / 引用来源 / 执行轨迹"四个卡片都显示正确
- [ ] 确认 loading 状态有转圈动画，不是白屏
- [ ] 手机宽度（< 700px）下布局不溢出

### 6. 评估集
- [ ] `eval/dataset.jsonl` 至少扩展到 20 条
- [ ] 覆盖三类：可答（answer）/ 需澄清（clarify）/ 需转人工（ticket）
- [ ] 每条都有 `expect_keywords`，不只是空数组
- [ ] 跑完 eval 后，把指标截图存档，作为基线

### 7. 文档更新流程
- [ ] 写一份简短 SOP：新增制度文件后，跑什么命令重新入库
- [ ] 建议：`python scripts/seed_documents.py` → `python -m rag.ingest_main`
- [ ] 在 README 里加一段"知识库更新"说明

### 8. 日志与监控
- [ ] 确认 `LOG_LEVEL=INFO` 时，日志是 JSON 行格式
- [ ] 跑一次完整流程，在终端确认能看到：
  - `intent=answer` / `intent=ticket` 等关键日志
  - `ticket_created: TICKET-xxx` 日志
  - `llm_call_failed` 兜底日志（如果 key 无效）
- [ ] 生产部署时，建议把日志输出到文件或用 ELK / Loki 收集

---

## 第三级：可以（锦上添花）

### 9. 多轮对话
- [ ] 在 `AgentState` 加 `history: list[dict]` 字段
- [ ] `decide_intent` 节点把历史对话拼进 prompt
- [ ] 前端显示对话历史，不只是单轮

### 10. 流式输出
- [ ] `generate_answer` 节点改用 `llm.stream()` 逐 token 输出
- [ ] `POST /chat` 改成 `StreamingResponse`，前端用 `EventSource` 或 `fetch` stream
- [ ] 用户体验：不用等 5 秒才看到第一个字

### 11. 工单系统对接
- [ ] 把 `create_ticket()` 从 SQLite 换成真实工单系统 API（Jira / 自建 / 企业微信）
- [ ] 工单创建后，返回真实工单链接，而不是 `ticket_no`
- [ ] 加一个 `/tickets` 查询接口，前端可以查看工单状态

### 12. 用户权限
- [ ] 加 JWT / session 认证
- [ ] `POST /chat` 的 `user_id` 不再信任前端传值，而是从 token 解析
- [ ] 知识库加权限过滤：不同部门只能检索到自己有权看的文档

### 13. Docker 化
- [ ] 写 `Dockerfile`（python:3.10-slim 基础镜像）
- [ ] 写 `docker-compose.yml`：app + chromadb + 可选 sqlite volume
- [ ] 确认容器内 `CHROMA_PERSIST_DIR` 和 `SQLITE_PATH` 都挂到 volume，重启不丢数据

### 14. 灰度与回滚
- [ ] 新 prompt 上线前，先在 eval 集上跑分，对比基线
- [ ] 保留旧 prompt 版本，出问题可以快速回滚
- [ ] 加一个 `/admin` 管理接口，查看当前模型配置和阈值

---

## 上线前的最后 5 个必测 case

| # | 问题 | 期望结果 |
|---|------|---------|
| 1 | 差旅报销几天内提交？ | `intent=answer`，`created_ticket=false`，sources 非空 |
| 2 | 帮我转人工处理一下 | `intent=ticket`，`created_ticket=true`，trace 有 `ticket_created` |
| 3 | 随便聊聊天气 | `intent=clarify`，`created_ticket=true`（兜底建单） |
| 4 | （清空 API KEY 后）差旅报销几天内提交？ | 不崩，返回兜底文案，`mode=mock` |
| 5 | 一个完全不在知识库里的问题 | `retrieved_docs` 为空 → 走 clarify，不编造 |

5 个 case 全部通过，就可以给业务方演示了。
