from typing import Any, Dict
from langchain_anthropic import ChatAnthropic

from app.agent.schemas import PRReview
from eval.schemas import JudgeScore


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def judge_review(
    review: PRReview,
    ground_truth_entry: Dict[str, Any],
    api_key: str | None = None,
    model: str | None = None,
) -> JudgeScore:
    pr_id = ground_truth_entry["pr_id"]
    expected_issues = ground_truth_entry["expected_issues"]

    expected_text = "\n".join(
        f"- [{e['severity']}] {e['issue_type']}: {e['description']}"
        for e in expected_issues
    )
    agent_text = "\n".join(
        f"- [{c.severity}] {c.issue_type} line {c.line_number}: {c.description}"
        for c in review.comments
    ) or "No issues detected."

    prompt = f"""You are an evaluation judge. Compare the agent's PR review against the labeled ground truth.

Ground truth expected issues for PR {pr_id}:
{expected_text}

Agent's detected issues:
{agent_text}

For each expected issue, decide if the agent caught it (true positive) or missed it (false negative).
For each agent issue, decide if it matches a ground truth issue (true positive) or is spurious (false positive).

An agent issue "matches" a ground truth issue if it describes the same underlying problem, even if worded differently.

Compute:
- recall = true_positives / (true_positives + false_negatives)
- precision = true_positives / (true_positives + false_positives)

Return 0.0 for recall or precision if the denominator is 0.
"""

    if api_key is None:
        from app.config import settings
        api_key = settings.anthropic_api_key
    if model is None:
        from app.config import settings
        model = settings.anthropic_model

    llm = ChatAnthropic(model=model, api_key=api_key)
    structured_llm = llm.with_structured_output(JudgeScore)
    score: JudgeScore = structured_llm.invoke(prompt)
    score.pr_id = pr_id
    tp = len(score.true_positives)
    fp = len(score.false_positives)
    fn = len(score.false_negatives)
    score.recall = _rate(tp, tp + fn)
    score.precision = _rate(tp, tp + fp)
    return score
