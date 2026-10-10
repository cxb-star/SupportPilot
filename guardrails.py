import os
"""工程护栏：角色权限、限流降级、灰度回滚最小实现。

设计目标：
- 不改 agent 核心节点，只在 API 层加护栏
- 权限：按角色限制“谁能改工单状态”
- 限流：按 user_id 做简单令牌桶（内存版，够用）
- 灰度：通过 env 控制新旧 prompt/策略开关，支持一键回滚
"""
import time
import threading
from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# 1. 角色权限
# ============================================================

ROLE_PERMISSIONS = {
    "operator": ["chat", "list_tickets"],
    "supervisor": ["chat", "list_tickets", "get_ticket", "transition_ticket"],
    "admin": ["chat", "list_tickets", "get_ticket", "transition_ticket", "rollback"],
}


def user_has_permission(role: str, action: str) -> bool:
    if not role:
        return False
    perms = ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["operator"])
    return action in perms


# ============================================================
# 2. 限流（内存令牌桶，按 user_id）
# ============================================================

@dataclass
class _Bucket:
    tokens: float
    last_refill: float
    capacity: float
    refill_rate: float  # tokens/sec


class RateLimiter:
    """简单令牌桶：每个 user_id 一个桶。
    默认：容量 10 个请求，每秒补充 2 个。
    """
    def __init__(self, capacity: float = 10.0, refill_rate: float = 2.0):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def allow(self, user_id: str) -> bool:
        with self._lock:
            now = time.time()
            bucket = self._buckets.get(user_id)
            if bucket is None:
                bucket = _Bucket(tokens=self.capacity, last_refill=now,
                                 capacity=self.capacity, refill_rate=self.refill_rate)
                self._buckets[user_id] = bucket
            # refill
            elapsed = now - bucket.last_refill
            bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_rate)
            bucket.last_refill = now
            if bucket.tokens >= 1:
                bucket.tokens -= 1
                return True
            return False


_rate_limiter: Optional[RateLimiter] = None
_rl_lock = threading.Lock()


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    with _rl_lock:
        if _rate_limiter is None:
            _rate_limiter = RateLimiter(capacity=10.0, refill_rate=2.0)
        return _rate_limiter


# ============================================================
# 3. 灰度开关（prompt / 策略版本）
# ============================================================

@dataclass
class FeatureFlags:
    """灰度标志：控制新旧策略切换，支持一键回滚。
    通过 env 变量控制，无需重启改代码。
    """
    use_llm_intent: bool = False
    # 支持 env 覆盖：USE_LLM_INTENT=1 时走 LLM 意图分类，默认 False（规则版，可回滚）
    _USE_LLM_INTENT_ENV = os.getenv('USE_LLM_INTENT', '0').strip().lower() in {'1','true','yes','on'}

    def __post_init__(self):
        if self._USE_LLM_INTENT_ENV:
            self.use_llm_intent = True
    use_history_in_prompt: bool = True  # True: 带多轮历史；False: 关闭（回滚）
    rag_top_k: int = 4
    confidence_threshold: float = 0.5
    active_version: str = "v2"        # 当前灰度版本标签，写进 trace 便于审计
