import json
import logging
from io import StringIO

from logging_config import _JsonFormatter, get_ctx_logger
from store.audit import record


def test_record_outputs_json_line():
    """record() 输出为合法 JSON 行，含 logger/level/msg/ts 字段。"""
    out = StringIO()
    handler = logging.StreamHandler(out)
    handler.setFormatter(_JsonFormatter())
    audit_logger = get_ctx_logger("audit")._logger
    # 避免重复添加 handler（测试幂等）
    if not any(isinstance(h, type(handler)) for h in audit_logger.handlers):
        audit_logger.addHandler(handler)
    try:
        record({"event": "ticket_created", "ticket_no": "T-999"})
        line = out.getvalue().strip()
        parsed = json.loads(line)
        assert parsed["logger"] == "agent_knowledge.audit"
        assert parsed["level"] == "INFO"
        assert "event" in parsed["msg"]
        assert "ts" in parsed
    finally:
        audit_logger.removeHandler(handler)