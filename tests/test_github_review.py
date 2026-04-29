from unittest.mock import MagicMock, patch

from app.agent.schemas import PRReview, ReviewComment
from app.services.github import post_review


class FakePaginatedCommits:
    def __init__(self, commits):
        self.commits = commits

    def __getitem__(self, index):
        if index < 0:
            raise IndexError("list index out of range")
        return self.commits[index]

    def __iter__(self):
        return iter(self.commits)


def test_post_review_renders_unknown_cost_and_critical_risk():
    review = PRReview(
        pr_number=42,
        comments=[],
        overall_risk="critical",
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
    assert "**Overall Risk:** 🔴 CRITICAL" in body
    assert "**Issues Found:** 0" in body
    assert "**Prompt Version:** `v1`" in body
    assert "**Latency:** 1234ms | **Cost:** N/A" in body


def test_post_review_uses_latest_commit_for_inline_comments():
    review = PRReview(
        pr_number=42,
        comments=[
            ReviewComment(
                line_number=1,
                issue_type="security",
                severity="critical",
                description="Unsafe input reaches SQL query",
                suggestion="Use parameterized queries",
            )
        ],
        overall_risk="critical",
        prompt_version="v1",
        latency_ms=1234,
    )

    latest_commit = MagicMock()
    commits = FakePaginatedCommits([MagicMock(), latest_commit])
    pull = MagicMock()
    pull.get_commits.return_value = commits
    pull.get_files.return_value = [MagicMock(filename="app/example.py")]
    repo = MagicMock()
    repo.get_pull.return_value = pull
    github = MagicMock()
    github.get_repo.return_value = repo

    with patch("app.services.github.Github", return_value=github):
        post_review("test/repo", 42, review)

    create_kwargs = pull.create_review.call_args.kwargs
    assert create_kwargs["commit"] is latest_commit
    assert create_kwargs["comments"][0]["path"] == "app/example.py"
