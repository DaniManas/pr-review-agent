import hashlib
import hmac
import json
import logging
import os
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from mangum import Mangum

from app.config import settings
from app.agent.graph import agent
from app.services.github import fetch_diff, post_review
from app.services.database import insert_run

# Enable LangSmith tracing if configured
if os.environ.get("LANGSMITH_API_KEY"):
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ.setdefault("LANGCHAIN_PROJECT", os.environ.get("LANGSMITH_PROJECT", "pr-review-agent"))

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI()

INTERNAL_REVIEW_SOURCE = "pr-review-agent.internal-review"


def _verify_signature(body: bytes, signature: str) -> bool:
    mac = hmac.new(
        settings.github_webhook_secret.encode(),
        msg=body,
        digestmod=hashlib.sha256,
    )
    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature)


def _run_review_pipeline(repo: str, pr_number: int) -> None:
    try:
        diff = fetch_diff(repo, pr_number)
        result = agent.invoke({"diff": diff, "pr_number": pr_number})
        review = result["review"]
        langsmith_trace_id = result.get("langsmith_trace_id")
        post_review(repo, pr_number, review)
        insert_run(
            pr_number=pr_number,
            repo=repo,
            prompt_version=settings.prompt_version,
            review=review,
            latency_ms=review.latency_ms,
            cost_usd=review.cost_usd,
            langsmith_trace_id=langsmith_trace_id,
            status="success",
        )
    except Exception as exc:
        logger.exception("Pipeline failed for PR #%s in %s", pr_number, repo)
        try:
            insert_run(
                pr_number=pr_number,
                repo=repo,
                prompt_version=settings.prompt_version,
                review=None,
                latency_ms=None,
                cost_usd=None,
                langsmith_trace_id=None,
                status="failed",
                error_message=str(exc),
            )
        except Exception:
            logger.exception("Failed to write failure row to Supabase")


def _get_lambda_client():
    import boto3

    return boto3.client("lambda")


def _enqueue_review(repo: str, pr_number: int) -> Literal["queued", "inline"]:
    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if not function_name:
        _run_review_pipeline(repo, pr_number)
        return "inline"

    payload = {
        "source": INTERNAL_REVIEW_SOURCE,
        "repo": repo,
        "pr_number": pr_number,
    }
    _get_lambda_client().invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=json.dumps(payload).encode(),
    )
    return "queued"


@app.post("/webhook")
async def webhook(
    request: Request,
    x_github_event: str = Header(None),
    x_hub_signature_256: str = Header(None),
):
    body = await request.body()

    if x_hub_signature_256 is None or not _verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_event not in ("pull_request",):
        return {"status": "ignored", "event": x_github_event}

    payload = json.loads(body)
    action = payload.get("action", "")

    if action not in ("opened", "synchronize"):
        return {"status": "ignored", "action": action}

    pr_number = payload["pull_request"]["number"]
    repo = payload["repository"]["full_name"]
    logger.info("PR #%s opened/updated in %s", pr_number, repo)

    try:
        mode = _enqueue_review(repo, pr_number)
        return {"status": "accepted", "pr": pr_number, "mode": mode}
    except Exception as exc:
        logger.exception("Failed to enqueue pipeline for PR #%s in %s", pr_number, repo)
        try:
            insert_run(
                pr_number=pr_number,
                repo=repo,
                prompt_version=settings.prompt_version,
                review=None,
                latency_ms=None,
                cost_usd=None,
                langsmith_trace_id=None,
                status="failed",
                error_message=str(exc),
            )
        except Exception:
            logger.exception("Failed to write failure row to Supabase")
        return {"status": "accepted", "pr": pr_number}


_asgi_handler = Mangum(app)


def handler(event, context):
    if isinstance(event, dict) and event.get("source") == INTERNAL_REVIEW_SOURCE:
        _run_review_pipeline(event["repo"], int(event["pr_number"]))
        return {"status": "processed", "pr": event["pr_number"]}

    return _asgi_handler(event, context)
