"""LLM 封装：基于 langchain-openai 的 ChatOpenAI（兼容 DeepSeek / Agnes 等 OpenAI 端点）。

- 未配置 key 时 build_llm() 返回 None，调用方应走兜底（clarify/ticket）
- 调用失败（网络/超时/限流）抛出 LLMUnavailable，同样走兜底
- complete_structured() 额外返回 token 用量与估算成本，供成本统计落库
"""
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import settings
from logging_config import get_ctx_logger

log = get_ctx_logger("agent_knowledge.llm")

# 粗略单价（美元 / 1K tokens），仅用于估算，按模型名关键词匹配；
# 精确计费以厂商账单为准。未命中用 _DEFAULT_PRICE_PER_1K。
_PRICE_PER_1K = {
    "deepseek-chat": (0.0006, 0.0018),
    "deepseek-reasoner": (0.00055, 0.0022),
    "agnes-3.0-flash": (0.0002, 0.0005),
    "agnes-2.5-flash": (0.00015, 0.0004),
    "gpt-4o-mini": (0.00015, 0.0006),
}
_DEFAULT_PRICE_PER_1K = (0.0005, 0.0015)


class LLMUnavailable(Exception):
    """LLM 不可用（未配置或调用失败）。调用方必须优雅降级。"""


@dataclass
class LLMResult:
    """一次 LLM 调用的完整产物：文本 / 结构化数据 + 用量与成本。"""

    text: str = ""
    data: dict = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    model: str = ""

    @property
    def usage(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "cost_usd": round(self.cost_usd, 6),
            "model": self.model,
        }


def _cost_estimate(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_price, out_price = _DEFAULT_PRICE_PER_1K
    for key, (i, o) in _PRICE_PER_1K.items():
        if key in model:
            in_price, out_price = i, o
            break
    return (prompt_tokens * in_price + completion_tokens * out_price) / 1000.0


def build_llm() -> Optional[ChatOpenAI]:
    if not settings.LLM_API_KEY:
        log.warning("llm_disabled reason=missing_api_key")
        return None
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=settings.LLM_TEMPERATURE,
        timeout=settings.LLM_TIMEOUT,
        max_retries=settings.LLM_MAX_RETRIES,
    )
    log.info(
        "llm_configured model=%s base_url=%s",
        settings.LLM_MODEL,
        settings.LLM_BASE_URL,
    )
    return llm


def _extract_usage(resp) -> tuple[int, int, int]:
    """从 langchain 响应里取 token 用量；取不到就返回 0。"""
    usage = getattr(resp, "usage_metadata", None) or {}
    prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
    completion_tokens = int(usage.get("completion_tokens", 0) or 0)
    total_tokens = int(usage.get("total_tokens", 0) or 0) or (prompt_tokens + completion_tokens)
    return prompt_tokens, completion_tokens, total_tokens


def complete(
    llm: ChatOpenAI,
    prompt: str,
    system: Optional[str] = None,
    ctx: Optional[dict] = None,
) -> LLMResult:
    """单次补全；任何失败（含超时/限流）都转成 LLMUnavailable，由调用方兜底。

    返回 LLMResult，含文本、token 用量、延迟与估算成本。
    """
    messages: list[BaseMessage] = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(AIMessage(content=prompt))
    start = time.perf_counter()
    try:
        resp = llm.invoke(messages)
    except Exception as exc:  # noqa: BLE001 - 统一兜底（含超时/限流/网络）
        log.warning("llm_call_failed error=%s", exc, ctx=ctx or {})
        raise LLMUnavailable(str(exc)) from exc
    latency_ms = int((time.perf_counter() - start) * 1000)

    text = getattr(resp, "content", "") or ""
    text = text if isinstance(text, str) else str(text)
    prompt_tokens, completion_tokens, total_tokens = _extract_usage(resp)
    cost = _cost_estimate(settings.LLM_MODEL, prompt_tokens, completion_tokens)

    return LLMResult(
        text=text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        cost_usd=cost,
        model=settings.LLM_MODEL,
    )


def complete_structured(
    llm: ChatOpenAI,
    prompt: str,
    system: Optional[str] = None,
    ctx: Optional[dict] = None,
) -> LLMResult:
    """要求 LLM 输出 JSON 对象；解析失败不抛错，返回空 data（用量照记）。

    返回 LLMResult，.data 为解析后的 dict，.usage 为用量/成本。
    """
    result = complete(llm, prompt, system, ctx=ctx)
    text = result.text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        result.data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("llm_json_parse_failed raw=%s", text[:200], ctx=ctx or {})
        result.data = {}
    return result
