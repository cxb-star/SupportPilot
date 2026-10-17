"""guardrails module tests."""
import threading
import time
import pytest
from guardrails import (
    FeatureFlags, RateLimiter,
    get_feature_flags_snapshot, reset_feature_flags,
    set_feature_flag, user_has_permission,
)


@pytest.fixture(autouse=True)
def _reset_runtime_flags():
    yield
    reset_feature_flags()


def test_flags_default_values():
    reset_feature_flags()
    flags = FeatureFlags()
    assert flags.use_llm_intent is False
    assert flags.use_history_in_prompt is True
    assert flags.rag_top_k == 4
    assert flags.confidence_threshold == 0.5
    assert flags.active_version == "v2"


def test_flags_runtime_and_env_priority():
    # runtime flag overrides default
    reset_feature_flags()
    set_feature_flag("use_llm_intent", True)
    set_feature_flag("rag_top_k", 8)
    set_feature_flag("active_version", "v3")
    flags = FeatureFlags()
    assert flags.use_llm_intent is True
    assert flags.rag_top_k == 8
    assert flags.active_version == "v3"
    assert flags.confidence_threshold == 0.5  # 未覆盖
    # snapshot 是深拷贝，修改不影响运行时
    snap = get_feature_flags_snapshot()
    snap["use_llm_intent"] = False
    assert FeatureFlags().use_llm_intent is True
    # reset 后所有运行时覆盖消失
    reset_feature_flags()
    assert get_feature_flags_snapshot() == {}
    assert FeatureFlags().use_llm_intent is False
    # env 作为次级优先级（无运行时覆盖时生效）
    with pytest.MonkeyPatch().context() as m:
        m.setenv("USE_LLM_INTENT", "1")
        assert FeatureFlags().use_llm_intent is True
    assert get_feature_flags_snapshot() == {}


def test_permission_roles_coverage():
    assert user_has_permission("operator", "chat") is True
    assert user_has_permission("operator", "list_tickets") is True
    assert user_has_permission("operator", "transition_ticket") is False
    assert user_has_permission("operator", "rollback") is False
    assert user_has_permission("supervisor", "transition_ticket") is True
    assert user_has_permission("supervisor", "rollback") is False
    assert user_has_permission("admin", "rollback") is True
    assert user_has_permission("admin", "transition_ticket") is True
    assert user_has_permission("unknown", "chat") is True
    assert user_has_permission("", "chat") is False
    assert user_has_permission(None, "chat") is False


def test_rate_limiter_token_bucket_behavior():
    small = RateLimiter(capacity=2.0, refill_rate=10.0)
    assert small.allow("u1") is True
    assert small.allow("u1") is True
    assert small.allow("u1") is False
    assert small.allow("u2") is True
    time.sleep(0.2)
    assert small.allow("u1") is True


def test_flags_thread_safety_no_crash():
    reset_feature_flags()
    errors = []
    def writer(i):
        try:
            set_feature_flag(f"key_{i}", i)
        except Exception as exc:
            errors.append(exc)
    def reader():
        try:
            _ = FeatureFlags()
            _ = get_feature_flags_snapshot()
        except Exception as exc:
            errors.append(exc)
    threads = [threading.Thread(target=writer, args=(i,)) for i in range(50)]
    threads += [threading.Thread(target=reader) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [], str(errors)
    snap = get_feature_flags_snapshot()
    assert len(snap) == 50
