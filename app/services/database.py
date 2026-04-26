import httpx

from app.config import settings


def insert_run(
    pr_number: int,
    repo: str,
    prompt_version: str,
    review,           # PRReview | None
    latency_ms: int | None,
    cost_usd: float | None,
    langsmith_trace_id: str | None,
    status: str,      # 'success' | 'failed'
    error_message: str | None = None,
) -> None:
    row = {
        "pr_number": pr_number,
        "repo": repo,
        "prompt_version": prompt_version,
        "overall_risk": review.overall_risk if review else None,
        "comment_count": len(review.comments) if review else None,
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
        "status": status,
        "error_message": error_message,
        "langsmith_trace_id": langsmith_trace_id,
    }
    response = httpx.post(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/reviews",
        headers={
            "apikey": settings.supabase_service_key,
            "Authorization": f"Bearer {settings.supabase_service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=row,
        timeout=10,
    )
    response.raise_for_status()
