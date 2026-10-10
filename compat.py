"""兼容层：让 langchain-core 0.3.x 在新版 langchain 上正常导入。

项目真正依赖的是 langchain-core；langchain 本体是可选的。
若环境装了 langchain 1.x（移除了模块级属性），顺手补上；没装也照常工作。
这样干净 CI 环境（只装 langchain-core）也能通过。
"""
import importlib


def ensure_langchain_compat() -> None:
    """确保 langchain_core 可导入；若装了 langchain 1.x，补上缺失属性。

    幂等、无副作用，可在任意模块 import 后安全调用。
    """
    import langchain_core  # noqa: F401

    try:
        langchain = importlib.import_module("langchain")
    except ImportError:
        return

    for attr in ("debug", "verbose", "llm_cache"):
        if not hasattr(langchain, attr):
            setattr(langchain, attr, None if attr == "llm_cache" else False)
