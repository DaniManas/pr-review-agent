from typing import Literal
from pydantic import BaseModel


class ReviewComment(BaseModel):
    line_number: int
    issue_type: Literal["security", "logic", "quality"]
    severity: Literal["critical", "warning", "info"]
    description: str
    suggestion: str


class PRReview(BaseModel):
    pr_number: int
    comments: list[ReviewComment]
    overall_risk: Literal["critical", "high", "medium", "low"]
    prompt_version: str
    latency_ms: int
    cost_usd: float | None = None
