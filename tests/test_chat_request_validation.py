from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


class TestQuestionValidation:
    def test_empty_question_returns_422(self):
        resp = client.post("/chat", json={"question": "", "user_id": "u1"})
        assert resp.status_code == 422

    def test_question_too_long_returns_422(self):
        resp = client.post("/chat", json={"question": "x" * 501, "user_id": "u1"})
        assert resp.status_code == 422

    def test_valid_question_accepted(self):
        resp = client.post("/chat", json={"question": "退款规则是什么", "user_id": "u1"})
        assert resp.status_code == 200


class TestUserIdValidation:
    def test_user_id_with_semicolon_rejected(self):
        resp = client.post("/chat", json={
            "question": "退款规则是什么",
            "user_id": '"; DROP TABLE sessions;--',
        })
        assert resp.status_code == 422

    def test_user_id_with_quotes_rejected(self):
        resp = client.post("/chat", json={
            "question": "退款规则是什么",
            "user_id": '"injected"',
        })
        assert resp.status_code == 422

    def test_default_user_id_still_works(self):
        resp = client.post("/chat", json={"question": "退款规则是什么"})
        assert resp.status_code == 200

    def test_valid_user_id_accepted(self):
        resp = client.post("/chat", json={
            "question": "退款规则是什么",
            "user_id": "user_123-test",
        })
        assert resp.status_code == 200