"""Prompt 模板：客服一线支撑 Agent，要求 LLM 输出 JSON，便于程序解析与兜底。"""

INTENT_PROMPT = """你是客服一线支撑助手。请判断用户问题属于哪类：
1) refund: 退款
2) return: 退货
3) reship: 补发
4) compensate: 赔付 / 破损 / 质量
5) promo: 活动 / 规则 / 优惠
6) ticket: 明确要人工 / 投诉 / 升级
7) clarify: 信息不足，需要追问

用户问题：
{question}

只返回 JSON：{{"intent": "refund|return|reship|compensate|promo|ticket|clarify", "confidence": 0.0-1.0}}"""

ANSWER_PROMPT = """你是客服一线支撑助手。只基于下面的资料回答问题。
如果资料不足，请明确说明"资料不足"，不要编造。

相关资料：
{context}

用户问题：
{question}

只返回 JSON：
{{
  "answer": "答案文本",
  "sources": ["来源编号", ...],
  "confidence": 0.0-1.0
}}"""

CLARIFY_PROMPT = """你是客服一线支撑助手。用户问题不够明确，请给一个简短追问。

用户问题：
{question}

只返回 JSON：{{"message": "追问文本"}}"""

TICKET_PROMPT = """你是客服一线支撑助手。当前问题需要转人工，请生成一句简短提示。

用户问题：
{question}

只返回 JSON：{{"message": "提示文本"}}"""
