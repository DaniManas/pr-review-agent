from unittest.mock import MagicMock, patch

from app.agent.schemas import PRReview
from app.services.github import post_review


def test_post_review_renders_unknown_cost_as_unavailable():
    review = PRReview(
        pr_number=42,
        comments=[],
        overall_risk="high",
        prompt_version="v1",
        latency_ms=1234,
        cost_usd=None,
    )

    pull = MagicMock()
    pull.get_commits.return_value.reversed = ["commit-sha"]
    repo = MagicMock()
    repo.get_pull.return_value = pull
    github = MagicMock()
    github.get_repo.return_value = repo

    with patch("app.services.github.Github", return_value=github):
        post_review("test/repo", 42, review)

    body = pull.create_review.call_args.kwargs["body"]
    assert "**Overall Risk:** 🔴 HIGH" in body
    assert "**Issues Found:** 0" in body
    assert "**Prompt Version:** `v1`" in body
    assert "**Latency:** 1234ms | **Cost:** N/A" in body
