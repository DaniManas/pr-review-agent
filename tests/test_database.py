from unittest.mock import Mock, patch

from app.services.database import insert_run


def test_insert_run_posts_review_row_to_supabase_rest():
    review = Mock()
    review.overall_risk = "LOW"
    review.comments = [Mock(), Mock()]
    response = Mock()

    with patch("app.services.database.httpx.post", return_value=response) as post:
        insert_run(
            pr_number=12,
            repo="owner/repo",
            prompt_version="v1",
            review=review,
            latency_ms=1234,
            cost_usd=0.0123,
            langsmith_trace_id="trace-123",
            status="success",
        )

    post.assert_called_once()
    url = post.call_args.args[0]
    kwargs = post.call_args.kwargs

    assert url.endswith("/rest/v1/reviews")
    assert kwargs["headers"]["apikey"]
    assert kwargs["headers"]["Authorization"].startswith("Bearer ")
    assert kwargs["headers"]["Prefer"] == "return=minimal"
    assert kwargs["json"] == {
        "pr_number": 12,
        "repo": "owner/repo",
        "prompt_version": "v1",
        "overall_risk": "LOW",
        "comment_count": 2,
        "latency_ms": 1234,
        "cost_usd": 0.0123,
        "status": "success",
        "error_message": None,
        "langsmith_trace_id": "trace-123",
    }
    response.raise_for_status.assert_called_once()
