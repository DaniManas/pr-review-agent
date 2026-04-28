from typing import List, Optional
from pydantic import BaseModel

from app.agent.schemas import PRReview


class JudgeScore(BaseModel):
    pr_id: str
    true_positives: List[str]
    false_positives: List[str]
    false_negatives: List[str]
    recall: float
    precision: float
    reasoning: str


class EvalResult(BaseModel):
    pr_id: str
    repo: str
    pr_number: int
    prompt_version: str
    review: PRReview
    score: JudgeScore
    langsmith_trace_id: Optional[str]
    run_at: str
