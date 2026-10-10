import logging

logger = logging.getLogger("agent_knowledge.audit")


def record(event: dict) -> None:
    logger.info("audit_event=%s", event)
