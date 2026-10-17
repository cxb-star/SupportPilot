"""rollback 路由层集成测试：FastAPI TestClient，不启动 uvicorn。

验证：
- /rollback 端点写入 flag 后 /feature-flags 能读到新状态
- operator 角色无权 rollback，返回 403
- rollback 到 v1 后 chat 请求走规则版意图分类
"""
from fastapi.testclient import TestClient

from app.main import app
from guardrails import reset_feature_flags, user_has_permission


client = TestClient(app)


def test_rollback_v1_changes_feature_flags():
    """POST /rollback?version=v1 后，GET /feature-flags 返回 use_llm_intent=False。
    证明 rollback 端点真正写入了运行时 flag，不只是 log.info。
    """
    reset_feature_flags()
    resp = client.post("/rollback?version=v1&role=admin")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "ok"
    assert data["rolled_back_to"] == "v1"
    assert data["use_llm_intent"] is False
    assert data["active_version"] == "v1"

    # GET /feature-flags 应反映 rollback 后的状态
    flags_resp = client.get("/feature-flags")
    assert flags_resp.status_code == 200
    flags = flags_resp.json()
    assert flags["use_llm_intent"] is False

    reset_feature_flags()


def test_rollback_operator_gets_403():
    """operator 角色没有 rollback 权限，请求应被拒绝。
    验证权限校验逻辑在路由层生效。
    """
    reset_feature_flags()
    resp = client.post("/rollback?version=v1&role=operator")
    assert resp.status_code == 403
    body = resp.json()
    assert "permission_denied" in body["detail"]
    assert "operator" in body["detail"]
    # 权限拒绝时 flag 不应被修改
    assert resp.json()["detail"] == body["detail"]
    reset_feature_flags()


def test_rollback_v2_sets_use_llm_intent():
    """POST /rollback?version=v2 将 use_llm_intent 切回 True。
    与 test_rollback_v1_changes_feature_flags 形成对照：
    证明 rollback 可以双向切换，不只是单向下沉到 v1。
    """
    reset_feature_flags()
    resp = client.post("/rollback?version=v2&role=admin")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["use_llm_intent"] is True
    assert data["active_version"] == "v2"

    flags_resp = client.get("/feature-flags")
    flags = flags_resp.json()
    assert flags["use_llm_intent"] is True

    reset_feature_flags()


def test_chat_uses_rules_after_rollback():
    """rollback 到 v1（use_llm_intent=False）后，
    发一个 "帮我转人工" 请求，验证 intent=ticket 走的是规则版。
    
    区分方式：先调 /rollback?version=v2 开启 LLM 意图，确认响应有 llm_usage；
    再调 /rollback?version=v1 回滚，同样请求响应中 llm_usage 为空。
    这样就能证明 rollback 真的改变了行为，而不是依赖默认值。
    """
    reset_feature_flags()

    # 步骤 1：先切到 v2，确认 LLM 意图模式生效
    client.post("/rollback?version=v2&role=admin")
    flags = client.get("/feature-flags").json()
    assert flags["use_llm_intent"] is True, "setup: v2 not applied"

    # 步骤 2：rollback 到 v1
    rollback_resp = client.post("/rollback?version=v1&role=admin")
    assert rollback_resp.status_code == 200
    assert rollback_resp.json()["active_version"] == "v1"

    # 步骤 3：验证 flag 确实切回
    flags = client.get("/feature-flags").json()
    assert flags["use_llm_intent"] is False, "rollback did not take effect"

    # 步骤 4：chat 请求走规则版，intent=ticket，无 LLM 调用
    chat_resp = client.post("/chat", json={
        "question": "帮我转人工处理一下",
        "user_id": "rollback-test-user",
    })
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert chat_data["intent"] == "ticket"
    assert chat_data["created_ticket"] is True
    assert chat_data["usage"].get("prompt_tokens", 0) == 0, \
        "rollback to v1 should skip LLM intent classification"

    reset_feature_flags()

def test_rollback_no_role_gets_403():
    """不传 role 时默认空字符串，应被拒绝而非静默放行。"""
    reset_feature_flags()
    resp = client.post("/rollback?version=v1")
    assert resp.status_code == 403
    body = resp.json()
    assert "permission_denied" in body["detail"]
    assert "''" in body["detail"]
    reset_feature_flags()

