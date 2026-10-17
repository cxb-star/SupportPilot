from logging_config import get_ctx_logger

audit = get_ctx_logger("audit")


def record(event: dict) -> None:
    audit.info("event=%s", event)
