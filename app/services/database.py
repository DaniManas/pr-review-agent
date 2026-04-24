from supabase import create_client

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
    client = create_client(settings.supabase_url, settings.supabase_service_key)
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
    client.table("reviews").insert(row).execute()
