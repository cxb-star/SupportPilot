"""兼容层：langchain 1.x 移除了模块级 debug/verbose/llm_cache 属性，
langchain-core 0.3.x 会因 AttributeError 崩溃。
在 import langchain_core.callbacks 前调用 ensure_langchain_compat()。"""
import langchain


def ensure_langchain_compat() -> None:
    for attr in ("debug", "verbose", "llm_cache"):
        if not hasattr(langchain, attr):
            try:
                setattr(langchain, attr, False if attr != "llm_cache" else None)
            except Exception:
                setattr(langchain, attr, False if attr != "llm_cache" else None)
