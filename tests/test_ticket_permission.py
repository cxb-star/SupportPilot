"""工单权限测试：验证角色权限控制。

直接调用 transition_ticket / user_has_permission，不经过 HTTP 层，
避免 response_model 序列化问题。"""
from guardrails import user_has_permission
from agent.tools import transition_ticket, create_ticket
from config import settings


class TestPermissionMatrix:
    """验证 ROLE_PERMISSIONS 定义的权限矩阵。"""

    def test_operator_has_chat_and_list_tickets(self):
        assert user_has_permission("operator", "chat") is True
        assert user_has_permission("operator", "list_tickets") is True

    def test_operator_cannot_transition_ticket(self):
        assert user_has_permission("operator", "transition_ticket") is False
        assert user_has_permission("operator", "rollback") is False

    def test_supervisor_can_transition_ticket(self):
        assert user_has_permission("supervisor", "transition_ticket") is True
        assert user_has_permission("supervisor", "get_ticket") is True
        assert user_has_permission("supervisor", "rollback") is False

    def test_admin_can_all_actions(self):
        assert user_has_permission("admin", "transition_ticket") is True
        assert user_has_permission("admin", "rollback") is True

    def test_empty_role_rejected(self):
        assert user_has_permission("", "transition_ticket") is False
        assert user_has_permission(None, "chat") is False


class TestTransitionTicketRoles:
    """通过 transition_ticket 实际调用验证权限生效。"""

    def test_supervisor_can_transition(self):
        t = create_ticket(settings.SQLITE_PATH, "u1", "test", intent="refund")
        result = transition_ticket(settings.SQLITE_PATH, t["ticket_no"], "in_progress", assignee="admin")
        assert result["status"] == "in_progress"
        assert result["assigned_to"] == "admin"

    def test_admin_can_transition(self):
        t = create_ticket(settings.SQLITE_PATH, "u1", "test", intent="refund")
        result = transition_ticket(settings.SQLITE_PATH, t["ticket_no"], "closed")
        assert result["status"] == "closed"

    def test_invalid_transition_raises_valueerror(self):
        t = create_ticket(settings.SQLITE_PATH, "u1", "test", intent="refund")
        try:
            transition_ticket(settings.SQLITE_PATH, t["ticket_no"], "open")
            assert False, "should have raised ValueError"
        except ValueError:
            pass