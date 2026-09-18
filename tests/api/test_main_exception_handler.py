from __future__ import annotations

from fastapi.testclient import TestClient


def _client_with_failing_route() -> TestClient:
    from deeptutor.api.main import app

    @app.get("/api/__test_unhandled_exception__")
    def _raise_unhandled() -> None:
        raise RuntimeError("intentional test failure")

    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_exception_returns_json_error() -> None:
    response = _client_with_failing_route().get("/api/__test_unhandled_exception__")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["detail"] == "RuntimeError: intentional test failure"
    assert body["type"] == "RuntimeError"
    # The body carries the same token the response header does, so a learner can
    # quote one value that also finds the traceback in the server log.
    assert body["request_id"]
    assert body["request_id"] == response.headers["x-request-id"]


def test_inbound_request_id_is_echoed_and_bound_to_the_failure() -> None:
    """A caller-supplied id must survive, not be replaced by a fresh one.

    A proxy or client that already tracks a request needs its own token back on
    the error, otherwise the id in the body points at nothing the caller owns.
    """
    response = _client_with_failing_route().get(
        "/api/__test_unhandled_exception__",
        headers={"x-request-id": "caller-supplied-id"},
    )

    assert response.status_code == 500
    assert response.headers["x-request-id"] == "caller-supplied-id"
    assert response.json()["request_id"] == "caller-supplied-id"


def test_successful_response_carries_a_request_id() -> None:
    """The id is not error-only — every request is traceable end to end."""
    response = _client_with_failing_route().get("/health/live")

    assert response.status_code == 200
    assert response.headers["x-request-id"]


def test_unhandled_exception_response_carries_cors_headers() -> None:
    """The 500 must travel back out through CORSMiddleware.

    An ``@app.exception_handler(Exception)`` is installed on Starlette's
    outermost ServerErrorMiddleware, so its response skips CORS entirely and a
    cross-origin caller sees an opaque CORS failure rather than the JSON body
    above — defeating the point of returning JSON at all. The boundary is a
    middleware registered inside CORS precisely so this header survives.
    """
    client = _client_with_failing_route()
    origin = "http://cross-origin.test"

    ok = client.get("/api/health", headers={"Origin": origin})
    error = client.get("/api/__test_unhandled_exception__", headers={"Origin": origin})

    assert error.status_code == 500
    # Whatever the CORS policy grants a normal response, it must also grant this one.
    assert error.headers.get("access-control-allow-origin") == ok.headers.get(
        "access-control-allow-origin"
    )
    assert error.headers.get("access-control-allow-origin") is not None
