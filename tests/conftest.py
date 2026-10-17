"""共享 fixture：测试前后重置 guardrails._runtime_flags，保证测试隔离。

_runtime_flags 是进程级全局，不重置会导致后续测试读到前一个测试留下的状态。
"""
import guardrails
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def _reset_runtime_flags():
    """每个测试用例开始前清零运行时 flag，结束后也清零。"""
    guardrails.reset_feature_flags()
    yield
    guardrails.reset_feature_flags()




