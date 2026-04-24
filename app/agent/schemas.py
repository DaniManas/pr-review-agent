from typing import List
from pydantic import BaseModel


class ReviewComment(BaseModel):
    line_number: int
    issue_type: str   # security | logic | quality
    severity: str     # critical | warning | info
    description: str
    suggestion: str


class PRReview(BaseModel):
    pr_number: int
    comments: List[ReviewComment]
    overall_risk: str     # high | medium | low
    prompt_version: str
    latency_ms: int
    cost_usd: float
