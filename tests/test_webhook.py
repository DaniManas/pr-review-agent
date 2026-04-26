import hashlib
import hmac
import json
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

TEST_SECRET = "test-secret"
TEST_PAYLOAD = {
    "action": "opened",
    "number": 42,
    "pull_request": {"number": 42},
    "repository": {"full_name": "testuser/repo"},
}


def make_signature(body: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), msg=body, digestmod=hashlib.sha256)
    return "sha256=" + mac.hexdigest()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_valid_signature_accepted(client):
    body = json.dumps(TEST_PAYLOAD).encode()
    sig = make_signature(body, TEST_SECRET)
    mock_review = MagicMock()
    mock_review.latency_ms = 100
    mock_review.cost_usd = 0.001
    with patch("app.main.fetch_diff", return_value="diff text") as mock_fetch, \
         patch("app.main.agent") as mock_agent, \
         patch("app.main.post_review") as mock_post, \
         patch("app.main.insert_run") as mock_insert:
        mock_agent.invoke.return_value = {"review": mock_review, "langsmith_trace_id": None}
        resp = client.post(
            "/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sig,
            },
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert resp.json()["pr"] == 42
    mock_insert.assert_called_once()
    call_kwargs = mock_insert.call_args.kwargs
    assert call_kwargs["status"] == "success"
    assert call_kwargs["prompt_version"] == "v1"


def test_lambda_webhook_queues_review_without_running_pipeline(client):
    body = json.dumps(TEST_PAYLOAD).encode()
    sig = make_signature(body, TEST_SECRET)
    mock_lambda = MagicMock()

    with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "test-function"}), \
         patch("app.main._get_lambda_client", return_value=mock_lambda), \
         patch("app.main.fetch_diff") as mock_fetch:
        resp = client.post(
            "/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sig,
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {"status": "accepted", "pr": 42, "mode": "queued"}
    mock_fetch.assert_not_called()
    mock_lambda.invoke.assert_called_once()
    call_kwargs = mock_lambda.invoke.call_args.kwargs
    assert call_kwargs["FunctionName"] == "test-function"
    assert call_kwargs["InvocationType"] == "Event"
    payload = json.loads(call_kwargs["Payload"].decode())
    assert payload == {
        "source": "pr-review-agent.internal-review",
        "repo": "testuser/repo",
        "pr_number": 42,
    }


def test_internal_lambda_event_runs_pipeline():
    from app.main import handler

    event = {
        "source": "pr-review-agent.internal-review",
        "repo": "testuser/repo",
        "pr_number": 42,
    }
    with patch("app.main._run_review_pipeline") as mock_pipeline:
        response = handler(event, None)

    assert response == {"status": "processed", "pr": 42}
    mock_pipeline.assert_called_once_with("testuser/repo", 42)


def test_invalid_signature_rejected(client):
    body = json.dumps(TEST_PAYLOAD).encode()
    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=badhash",
        },
    )
    assert resp.status_code == 401


def test_non_pr_event_ignored(client):
    body = json.dumps({"action": "created"}).encode()
    sig = make_signature(body, TEST_SECRET)
    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_pipeline_failure_returns_200(client):
    body = json.dumps(TEST_PAYLOAD).encode()
    sig = make_signature(body, TEST_SECRET)
    with patch("app.main.fetch_diff", side_effect=RuntimeError("network error")), \
         patch("app.main.insert_run") as mock_insert:
        resp = client.post(
            "/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sig,
            },
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert resp.json()["pr"] == 42
    mock_insert.assert_called_once()
    call_kwargs = mock_insert.call_args.kwargs
    assert call_kwargs["status"] == "failed"
    assert call_kwargs["error_message"] == "network error"


def test_synchronize_action_accepted(client):
    payload = {
        "action": "synchronize",
        "number": 42,
        "pull_request": {"number": 42},
        "repository": {"full_name": "testuser/repo"},
    }
    body = json.dumps(payload).encode()
    sig = make_signature(body, TEST_SECRET)
    mock_review = MagicMock()
    mock_review.latency_ms = 100
    mock_review.cost_usd = 0.001
    with patch("app.main.fetch_diff", return_value="diff text"), \
         patch("app.main.agent") as mock_agent, \
         patch("app.main.post_review"), \
         patch("app.main.insert_run"):
        mock_agent.invoke.return_value = {"review": mock_review, "langsmith_trace_id": None}
        resp = client.post(
            "/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sig,
            },
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


def test_pr_action_ignored(client):
    payload = {
        "action": "closed",
        "number": 42,
        "pull_request": {"number": 42},
        "repository": {"full_name": "testuser/repo"},
    }
    body = json.dumps(payload).encode()
    sig = make_signature(body, TEST_SECRET)
    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": sig,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    assert resp.json()["action"] == "closed"


def test_supabase_failure_still_returns_200(client):
    body = json.dumps(TEST_PAYLOAD).encode()
    sig = make_signature(body, TEST_SECRET)
    mock_review = MagicMock()
    mock_review.latency_ms = 100
    mock_review.cost_usd = 0.001
    with patch("app.main.fetch_diff", return_value="diff"), \
         patch("app.main.agent") as mock_agent, \
         patch("app.main.post_review"), \
         patch("app.main.insert_run", side_effect=RuntimeError("db down")):
        mock_agent.invoke.return_value = {"review": mock_review, "langsmith_trace_id": None}
        resp = client.post(
            "/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sig,
            },
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
