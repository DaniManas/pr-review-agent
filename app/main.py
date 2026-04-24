import hashlib
import hmac
import json
import logging
import os

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


def _verify_signature(body: bytes, signature: str) -> bool:
    mac = hmac.new(
        settings.github_webhook_secret.encode(),
        msg=body,
        digestmod=hashlib.sha256,
    )
    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature)


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
        return {"status": "accepted", "pr": pr_number}
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
        return {"status": "accepted", "pr": pr_number}


handler = Mangum(app)
