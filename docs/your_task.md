# 你的实操任务：做一个“工单/运营自动化 Agent”

## 目标

我给你的示例是企业知识库问答。

你的任务不是抄它，而是照着这个骨架，自己做一个不同业务场景：

> 做一个“工单/运营自动化 Agent”。

---

## 业务背景（你直接拿去用）

某公司有运营团队，每天会收到这些需求：

- 用户投诉
- 活动咨询
- 数据异常反馈
- 权限开通申请

你的 Agent 要做到：

1. 接收自然语言输入
2. 自动判断意图
3. 查询内部数据或知识库
4. 生成处理建议
5. 必要时自动创建工单
6. 输出结果并留痕

---

## 你要交付的东西

- 一个可运行项目
- 一个 README
- 一个最小前端或 curl 示例
- 一个评估集
- 一段 1 分钟口述说明

---

## 最小功能清单

按顺序做，不要贪多：

1. 定义 `state.py`
   - 输入：question, user_id, session_id
   - 中间：intent, context, confidence
   - 输出：answer, action, created_ticket

2. 写 `nodes.py`
   - classify_intent
   - fetch_context
   - generate_advice
   - ticket_if_needed

3. 写 `graph.py`
   - 串成固定 workflow

4. 写 `tools.py`
   - create_ticket
   - query_policy
   - query_metrics

5. 写 `app/routes.py`
   - POST /chat
   - GET /health

6. 写 `store/session.py`
   - 保存 sessions
   - 保存 audit_log

7. 写 `eval/dataset.jsonl`
   - 至少 10 条真实感问题

---

## 你必须自己拍板的 5 个问题

1. 哪些意图可以自动处理，哪些必须转人工？
2. 哪些工具允许 agent 调用？
3. 置信度低于多少时建单？
4. 审计要记录哪些字段？
5. 什么算“答对”、什么算“兜底成功”？

---

## 哪些可以交给 AI

- 生成代码骨架
- 写 prompt 初稿
- 生成测试集
- 写 README
- 写接口示例

## 哪些必须你自己做

- 定业务边界
- 定工具白名单
- 定阈值
- 定验收标准
- 跑 badcase 并复盘

---

## 做完后你要回答的 4 句话

1. 我做了什么产品？
2. 我改了哪些模块，为什么？
3. 哪里最不稳定？我怎么兜底？
4. 如果继续做一周，我下一步加什么？

能答这 4 句，你就算真正入门“Agent 落地”了。
