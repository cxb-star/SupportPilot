"""DB 错误处理测试：验证错误信息不泄露给客户端，服务端日志能记录 traceback。"""
import sqlite3
from unittest.mock import patch

import logging
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_ticket_transition_db_error_does_not_leak_to_client():
    """DB 层异常返回 500，响应体不含原始错误详情。
    验证修复后 f"db_error: {exc}" 不再出现在响应里。
    """
    with patch("app.routes.transition_ticket") as mock_fn:
        mock_fn.side_effect = sqlite3.OperationalError("database disk image is malformed")
        resp = client.post("/tickets/FAKE-123/status", json={"new_status": "closed"}, params={"role": "admin"})
        assert resp.status_code == 500
        body = resp.json()
        assert body["detail"] == "internal_server_error"
        # 不再泄露原始 DB 错误信息
        assert "database disk" not in body["detail"]
        assert "disk image" not in body["detail"]


def test_log_exception_records_traceback_after_fix():
    """验证 _CtxLogger.exception 调用后 _log 能捕获当前异常栈。
    修复前 exc_info=True 传进去是 bool，formatException 收到 bool 会崩溃或返回空字符串。
    """
    import logging_config
    logger = logging_config.get_ctx_logger("test_traceback")

    with patch.object(logger._logger, "handle") as mock_handle:
        try:
            raise RuntimeError("test traceback content")
        except RuntimeError:
            logger.exception("something went wrong")

    # handle 被调用一次，record.exc_info 应为三元组而非 bool
    assert mock_handle.called
    record = mock_handle.call_args[0][0]
    assert record.exc_info is not True
    assert record.exc_info is not None
    assert isinstance(record.exc_info, tuple)
    assert len(record.exc_info) == 3
    assert record.exc_info[1] is not None
    assert "test traceback content" in str(record.exc_info[1])


def test_log_exception_other_levels_still_work():
    """修复只影响 exception 路径；debug/info/warning/error 不受影响。
    验证其他方法仍然正常调用 handle。
    """
    import logging_config
    logger = logging_config.get_ctx_logger("test_levels")

    with patch.object(logger._logger, "handle") as mock_handle:
        logger.debug("debug msg")
        logger.info("info msg")
        logger.warning("warn msg")
        logger.error("error msg")

    assert mock_handle.call_count == 4
    levels = [c[0][0].levelno for c in mock_handle.call_args_list]
    assert levels[0] == logging.DEBUG
    assert levels[1] == logging.INFO
    assert levels[2] == logging.WARNING
    assert levels[3] == logging.ERROR

    # exception 额外加一次（内部 setdefault exc_info=True）
    with patch.object(logger._logger, "handle") as mock_handle2:
        try:
            raise ValueError("ctx exc")
        except ValueError:
            logger.exception("ctx error")
    assert mock_handle2.called
    record2 = mock_handle2.call_args[0][0]
    assert record2.exc_info is not True
    assert isinstance(record2.exc_info, tuple)

