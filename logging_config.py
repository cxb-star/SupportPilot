"""结构化日志配置：JSON 行格式 + 可附加上下文字段，便于机器解析与审计。"""
import json
import logging
import sys


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        ctx = getattr(record, "ctx", None)
        if ctx:
            base.update(ctx)
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=False, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger("agent_knowledge")
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"agent_knowledge.{name}")


class _CtxLogger:
    """带上下文的 logger：bind() 返回固定 ctx 的日志器；
    ctx 字段合并进 JSON 输出。直接调用 info/warning/error 等。"""

    def __init__(self, name: str, ctx: dict | None = None):
        self._logger = logging.getLogger(f"agent_knowledge.{name}")
        self._ctx = ctx or {}

    def bind(self, **ctx: object) -> "_CtxLogger":
        return _CtxLogger(self._logger.name, {**self._ctx, **ctx})

    def _log(self, level: int, msg: str, *args, **kwargs) -> None:
        ctx = kwargs.pop("ctx", None)
        exc = kwargs.pop("exc_info", None)
        if exc is True:
            exc = sys.exc_info()
        record = self._logger.makeRecord(
            self._logger.name, level, "__main__", 0, msg, args, exc
        )
        merged = {**self._ctx}
        if ctx:
            merged.update(ctx)
        if merged:
            record.ctx = merged
        self._logger.handle(record)

    def debug(self, msg: str, *args, **kw):
        self._log(logging.DEBUG, msg, *args, **kw)

    def info(self, msg: str, *args, **kw):
        self._log(logging.INFO, msg, *args, **kw)

    def warning(self, msg: str, *args, **kw):
        self._log(logging.WARNING, msg, *args, **kw)

    def error(self, msg: str, *args, **kw):
        self._log(logging.ERROR, msg, *args, **kw)

    def exception(self, msg: str, *args, **kw):
        kw.setdefault("exc_info", True)
        self._log(logging.ERROR, msg, *args, **kw)


def get_ctx_logger(name: str) -> _CtxLogger:
    return _CtxLogger(name)
