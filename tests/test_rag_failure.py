from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.auth import get_current_customer
from app.database import get_db


def fake_customer():
    class Customer:
        id = 1
    return Customer()


def test_rag_failure_returns_fallback():
    app.dependency_overrides[get_current_customer] = fake_customer

    try:
        with patch("app.chat.search_customer_invoices", return_value=[]):
            with patch(
                "app.chat.retrieve_customer_context",
                side_effect=RuntimeError("Simulated Qdrant failure"),
            ):
                client = TestClient(app)
                response = client.post(
                    "/chat/",
                    json={"message": "Show my invoices"},
                )

        assert response.status_code == 200
        assert "temporarily unavailable" in response.json()["response"].lower()

    finally:
        app.dependency_overrides.clear()