# AI Agent 全流程自研项目手册

> 目标：用最直接的方式讲清楚“企业知识库 Agent”怎么从 0 做到可演示、可评估、可进生产。
> 适合读者：会 Python 基础，学过 LangChain / LangGraph，目标是 AI Agent 岗位。

## 0. 这个项目到底在做什么

这不是“接入聊天框”，而是做一个最小的企业级 Agent 服务：

1. 用户输入自然语言问题
2. Agent 判断意图：直接回答 / 追问 / 转人工
3. 检索知识库
4. 调用 LLM 生成答案
5. 校验置信度
6. 如果不行就建工单兜底
7. 保存会话、审计日志、评估指标
8. 通过 API / 页面暴露给用户

关键词不是“聊天”，而是：

- 业务闭环
- 状态管理
- 工具调用
- 兜底
- 可审计
- 可评估

---

## 1. 产品目标定义

你先必须写清楚 4 件事：

- 目标用户：员工、客服、运营、IT？
- 核心任务：回答制度 / 查流程 / 查数据？
- 输出物：答案、来源、置信度、是否建单？
- 失败策略：什么时候追问、什么时候转人工？

如果这 4 件事说不清，后面写代码全是乱写。

---

## 2. 架构总览

当前项目是一个“最小可运行”的全链路：

```
用户输入
  -> FastAPI /chat
  -> Agent graph
      -> decide_intent
      -> retrieve_docs
      -> generate_answer
      -> ticket_if_needed
  -> 返回 answer / sources / confidence / created_ticket
  -> 写 sessions / audit_log 
```

你后面要升级，只需要往这个骨架里填真实组件，不需要推翻重来。

---

## 3. 目录结构与每个文件的职责

```text
agent_knowledge_self_built/
  app/
    main.py         # FastAPI 入口、静态页面
    routes.py       # /chat /health 等接口
  agent/
    graph.py        # 主流程编排
    nodes.py        # 每个节点的具体逻辑
    state.py        # 状态定义
    prompts.py      # prompt 模板
    tools.py        # 工具函数
  rag/
    ingest.py       # 文档切块
    retriever.py    # 检索
  store/
    session.py      # SQLite 会话与审计
    audit.py        # 日志
  eval/
    dataset.jsonl   # 评估集
    run_eval.py     # 跑评估
  scripts/
    seed_documents.py # 造测试数据
  static/
    index.html      # 最简单前端
```

每个文件解决一个问题，不要混在一起。这就是你以后读任何 Agent 框架代码的基本功。

---

## 4. 状态设计：Agent 的“工作记忆”

看 `agent/state.py`。

你需要想清楚：

- 哪些字段是输入
- 哪些字段是中间过程
- 哪些字段是最终输出
- 哪些字段要落库审计

当前状态包括：

- `question`
- `session_id`
- `user_id`
- `intent`
- `retrieved_docs`
- `confidence`
- `answer`
- `sources`
- `created_ticket`
- `trace`

面试里你能讲出：

> 我用状态 schema 把输入、中间产物、输出、可追溯字段分开管理，方便调试和审计。

---

## 5. 主流程设计：为什么先写 graph

看 `agent/graph.py`。

当前是固定 workflow：

- `decide_intent`
- `retrieve_docs`
- `generate_answer`
- `ticket_if_needed`

这对应你之前问的核心：

**企业业务不是全都自主 agent，多数是“固定流程 + 局部 LLM 判断”。**

你要掌握的是：

- 什么时候走检索
- 什么时候走追问
- 什么时候直接建单
- 什么时候结束

如果后面要升级成更自主的 agent，就在这里加条件边、加循环、加工具调用节点。

---

## 6. 节点设计：每个节点只负责一件事

看 `agent/nodes.py`。

原则：

- 一个节点做一件事
- 输入输出清晰
- 不塞太多逻辑
- 出错能定位

当前节点：

- `decide_intent`：判断走哪条路
- `retrieve_docs`：拿知识
- `generate_answer`：生成回答
- `ticket_if_needed`：兜底

你以后接真实系统时，通常就是：

- 改某个节点逻辑
- 增加一个新节点
- 增加一条条件边

不是整个重写。

---

## 7. Prompt 设计：不是文学创作，是受控输入

看 `agent/prompts.py`。

你要重点理解：

- 你要模型做什么
- 你给它的资料边界是什么
- 你要求它输出的格式是什么
- 你如何限制它不要瞎编

当前最关键是“只基于资料回答，资料不足就说资料不足”。

这就是产品化思维：

**不是追求最聪明，而是追求最稳、最可控、可审计。**

---

## 8. 工具设计：Agent 的“手”

看 `agent/tools.py`。

工具不是越多越好，而是要明确：

- 工具叫什么
- 输入是什么
- 输出是什么
- 失败怎么办
- 有没有权限边界

当前只有一个 `create_ticket`。

你升级时，可以加：

- 查数据库
- 查 CRM
- 查工单系统
- 发邮件
- 调内部 API

每个工具都要有：

- timeout
- retry
- error message
- log

---

## 9. RAG 设计：企业知识库的核心

看 `rag/ingest.py` 和 `rag/retriever.py`。

你现在要理解 4 层：

- 文档解析
- 切块
- embedding / 检索
- 召回结果怎么给 LLM

当前是 mock，但真实项目要换：

- 向量库：Chroma / Qdrant / pgvector / Milvus
- 检索：向量召回 + 关键词召回 + rerank
- 切块：按标题 / 段落 / 表格 / 固定长度

面试里别说“我用了向量库”，要说：

> 我做了文档切块、embedding 入库、检索调优，并基于召回质量评估命中率与兜底率。

---

## 10. 会话与审计：为什么必须做

看 `store/session.py`。

你必须把两类东西分开：

- `sessions`：用户说了什么，系统回了什么
- `audit_log`：系统内部走了哪些节点，置信度多少，是否建单

这是企业级和 demo 的分界线。

没有审计，你后面没法回答：

- 为什么答错
- 为什么建单
- 谁在什么时候问了什么
- 模型行为能不能复盘

---

## 11. API 设计：产品入口

看 `app/routes.py`。

当前接口：

- `GET /health`
- `POST /chat`

你后续可扩展：

- 多轮会话
- 流式输出
- 管理后台
- 批量导入
- 用户权限

API 是 Agent 产品对外暴露的标准形态。

---

## 12. 评估设计：你怎么知道好不好

看 `eval/dataset.jsonl` 和 `eval/run_eval.py`。

你要建立 3 个指标：

- 答对率
- 兜底率
- 引用准确率

没有评估，你只能靠“我觉得不错”。

有了评估，你才能说：

- 改 prompt 后提升多少
- 换检索策略后提升多少
- 哪个业务场景还不稳定

---

## 13. 如何接入真实 LLM

当前代码是 mock。真实接入通常改 3 处：

1. `agent/nodes.py` 里的 `generate_answer` / `decide_intent` 调用 LLM
2. `agent/prompts.py` 里补完整 prompt
3. `.env` 里配置模型和密钥

你要自己决定：

- 用哪家模型
- 是单模型还是大小模型分工
- 是否加缓存
- 是否加超时
- 是否加 token 限额

这就是“接入业务”里真正的工程决策。

---

## 14. 如何接入真实向量库

当前 `retriever.py` 是 mock。真实接入通常改 3 处：

1. `rag/ingest.py`：embedding 入库
2. `rag/retriever.py`：检索逻辑
3. `.env`：向量库连接参数

你要决定：

- 向量库选型
- 切块策略
- top-k
- 是否混合检索
- 是否 rerank

这些都是“能写进简历”的工程点。

---

## 15. 哪些部分可以交给 AI 处理

可以交给 AI：

- 生成项目骨架
- 写 FastAPI 模板
- 写 SQLite 建表语句
- 写基础测试集
- 写 prompt 初稿
- 写 README
- 写接口文档

但要你来验收：

- 代码是否符合你的业务
- 状态字段是否够用
- 审计字段是否合规
- 兜底策略是否合适

原则：

**AI 负责“初稿”，你负责“判断、取舍、验收、担责”。**

---

## 16. 哪些部分必须你自己拍板

这些不建议直接让 AI 替你做主：

- 业务边界
- 谁可以用
- 哪些工具可暴露
- 哪些回答可以自动发
- 哪些必须人工确认
- 置信度阈值定多少
- 转人工规则是什么
- 审计保存多久
- 成本预算是多少

这些一旦错了，不是代码 bug，是业务事故。

---

## 17. 从 mock 到生产，你还要补什么

按顺序补：

1. 真实 LLM 接入
2. 真实向量库接入
3. 多轮会话历史
4. 用户权限
5. 日志与 trace 统一
6. 评估自动化
7. Docker 化
8. 灰度发布

你简历里不用都做完，但你要知道这条线。

---

## 18. 这个项目怎么讲成面试话术

建议你这样说：

> 我做过一个企业知识库 Agent，基于 LangGraph 设计主流程，包含意图判断、RAG 检索、答案生成、置信度兜底和工单创建。系统有状态持久化、审计日志和评估集，目标是把 LLM 接进业务，同时保证可控、可追踪、可回归。

这句话比“我学过 LangChain”强十倍。

---

## 19. 你现在最容易踩的坑

1. 只做聊天框，没有业务闭环
2. 工具设计太随意，没有边界
3. 只有 LLM，没有校验和兜底
4. 只有 demo，没有评估
5. 不会讲“我改了哪里、为什么”
6. 把 AI 写的代码当成自己理解的东西各个 各个各个

---

## 20. 建议你今晚就看这 6 个文件

- `agent/state.py`
- `agent/graph.py`
- `agent/nodes.py`
- `agent/tools.py`
- `store/session.py`
- `eval/run_eval.py`

看完后你问自己 5 个问题：

- 状态为什么这样设计
- 为什么先意图再检索
- 工具为什么单独放
- 审计为什么必须落库
- 评估怎么量化好坏

答得上来，你就真的入门了。
