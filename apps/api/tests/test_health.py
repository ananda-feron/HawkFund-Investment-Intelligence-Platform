from fastapi.testclient import TestClient

from app.main import app


def _explode() -> None:
    raise RuntimeError("sensitive internal detail")


app.add_api_route("/test/unhandled", _explode, methods=["GET"])


def test_liveness() -> None:
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "hawkfund-api",
        "release": "development",
    }
    assert response.headers["x-request-id"]


def test_valid_request_id_is_preserved() -> None:
    response = TestClient(app).get("/health/live", headers={"x-request-id": "trace-123"})
    assert response.headers["x-request-id"] == "trace-123"


def test_unhandled_errors_are_correlated_and_do_not_leak_details() -> None:
    response = TestClient(app, raise_server_exceptions=False).get("/test/unhandled")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error"}
    }
    assert "sensitive" not in response.text
    assert response.headers["x-request-id"]
