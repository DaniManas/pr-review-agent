import logging
from typing import Optional

import requests
from github import Github, GithubException

from app.agent.schemas import PRReview
from app.config import settings

logger = logging.getLogger(__name__)


def fetch_diff(repo: str, pr_number: int) -> str:
    """Fetch the raw unified diff for a PR using the GitHub API."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {settings.github_token}",
        "Accept": "application/vnd.github.v3.diff",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def post_review(repo: str, pr_number: int, review: PRReview) -> None:
    """Post a structured PR review with inline comments."""
    g = Github(settings.github_token)
    gh_repo = g.get_repo(repo)
    pull = gh_repo.get_pull(pr_number)

    # Get the latest commit SHA for positioning comments
    commit = pull.get_commits().reversed[0]

    # Build review body from overall_risk
    risk_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(review.overall_risk, "⚪")
    cost_text = "N/A" if review.cost_usd is None else f"${review.cost_usd:.4f}"
    body = (
        f"## PR Review Summary\n\n"
        f"**Overall Risk:** {risk_emoji} {review.overall_risk.upper()}\n"
        f"**Issues Found:** {len(review.comments)}\n"
        f"**Prompt Version:** `{review.prompt_version}`\n"
        f"**Latency:** {review.latency_ms}ms | **Cost:** {cost_text}"
    )

    if not review.comments:
        pull.create_review(body=body, event="COMMENT")
        return

    # Build inline comments
    comments = []
    for c in review.comments:
        severity_label = {"critical": "[CRITICAL]", "warning": "[WARNING]", "info": "[INFO]"}.get(
            c.severity, "[INFO]"
        )
        comment_body = (
            f"{severity_label} **{c.issue_type.upper()}**\n\n"
            f"{c.description}\n\n"
            f"**Suggestion:** {c.suggestion}"
        )
        comments.append({
            "path": _get_diff_file(pull, c.line_number),
            "position": c.line_number,
            "body": comment_body,
        })

    try:
        pull.create_review(
            commit=commit,
            body=body,
            event="COMMENT",
            comments=comments,
        )
    except GithubException as e:
        # If inline positioning fails (common with generated line numbers), fall back to body-only review
        logger.warning("Inline comments failed (%s), posting body-only review", e.status)
        issues_text = "\n".join(
            f"- Line {c.line_number} [{c.severity}] {c.issue_type}: {c.description} → {c.suggestion}"
            for c in review.comments
        )
        pull.create_review(body=body + "\n\n### Issues\n" + issues_text, event="COMMENT")


def _get_diff_file(pull, line_number: int) -> str:
    """Get the first changed file path from the PR (used as fallback for positioning)."""
    files = list(pull.get_files())
    return files[0].filename if files else "unknown"
