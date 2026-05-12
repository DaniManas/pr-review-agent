from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewStats:
    issue_count: int
    warning_count: int
    critical_count: int


def summarize_review_counts(comments: list[dict]) -> ReviewStats:
    warnings = sum(1 for comment in comments if comment.get("severity") == "warning")
    critical = sum(1 for comment in comments if comment.get("severity") == "critical")
    return ReviewStats(
        issue_count=len(comments),
        warning_count=warnings,
        critical_count=critical,
    )
