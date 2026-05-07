from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.agent.schemas import PRReview, ReviewComment


def _structured_output_result(review: PRReview, usage_metadata: dict | None = None) -> dict:
    raw = MagicMock()
    raw.usage_metadata = usage_metadata
    return {"parsed": review, "raw": raw, "parsing_error": None}


def test_schema_roundtrip():
    review = PRReview(
        pr_number=42,
        comments=[
            ReviewComment(
                line_number=10,
                issue_type="security",
                severity="critical",
                description="Hardcoded password",
                suggestion="Use environment variable",
            ),
            ReviewComment(
                line_number=25,
                issue_type="logic",
                severity="warning",
                description="Missing error handling",
                suggestion="Wrap in try/except",
            ),
        ],
        overall_risk="high",
        prompt_version="v1",
        latency_ms=1200,
        cost_usd=0.004,
    )
    json_str = review.model_dump_json()
    restored = PRReview.model_validate_json(json_str)
    assert review == restored


def test_agent_on_sample_diff():
    fake_patterns = [
        {"severity": "critical", "name": "SQL Injection", "description": "Unsanitized input in query"},
        {"severity": "warning", "name": "Hardcoded Secret", "description": "Secret found in source"},
    ]

    fake_review = PRReview(
        pr_number=0,  # will be overwritten by review_code node
        comments=[
            ReviewComment(
                line_number=5,
                issue_type="security",
                severity="critical",
                description="Potential SQL injection via unsanitized user input",
                suggestion="Use parameterized queries instead of string formatting",
            )
        ],
        overall_risk="high",
        prompt_version="v1",
        latency_ms=0,  # will be overwritten
        cost_usd=0.0,
    )

    # Mock the structured output chain: llm.with_structured_output(PRReview).invoke(...)
    mock_structured_chain = MagicMock()
    mock_structured_chain.invoke.return_value = _structured_output_result(
        fake_review,
        {"input_tokens": 20_000, "output_tokens": 2_000},
    )

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_chain

    with patch("app.agent.nodes.retrieve_similar_patterns", return_value=fake_patterns), \
         patch("app.agent.nodes.ChatAnthropic", return_value=mock_llm):
        from app.agent.graph import agent
        result = agent.invoke({"diff": "+ password = 'hunter2'\n+ query = f'SELECT * FROM users WHERE id={user_id}'", "pr_number": 1})

    assert "review" in result
    review = result["review"]
    assert isinstance(review, PRReview)
    assert review.pr_number == 1
    assert any(c.issue_type == "security" for c in review.comments)
    assert review.cost_usd == pytest.approx(0.09)
    mock_llm.with_structured_output.assert_called_once_with(PRReview, include_raw=True)


def test_review_comment_validation():
    # Missing required fields should raise ValidationError
    with pytest.raises(ValidationError):
        ReviewComment()  # all fields missing

    with pytest.raises(ValidationError):
        ReviewComment(line_number=1)  # most fields missing

    # Missing required fields on PRReview should raise ValidationError
    with pytest.raises(ValidationError):
        PRReview()  # all fields missing

    with pytest.raises(ValidationError):
        PRReview(pr_number=1)  # comments, overall_risk, etc. missing

    with pytest.raises(ValidationError):
        ReviewComment(
            line_number=1,
            issue_type="performance",
            severity="warning",
            description="Invalid issue type",
            suggestion="Use a valid issue type",
        )

    with pytest.raises(ValidationError):
        PRReview(
            pr_number=1,
            comments=[],
            overall_risk="urgent",
            prompt_version="v1",
            latency_ms=100,
        )


def test_review_cost_defaults_to_unknown():
    review = PRReview(
        pr_number=1,
        comments=[],
        overall_risk="low",
        prompt_version="v1",
        latency_ms=100,
    )

    assert review.cost_usd is None


def test_estimate_cost_usd_from_usage_metadata():
    from app.agent.nodes import estimate_cost_usd

    usage = {"input_tokens": 20_000, "output_tokens": 2_000}

    assert estimate_cost_usd(usage) == pytest.approx(0.09)


def test_estimate_cost_usd_returns_none_without_usage_metadata():
    from app.agent.nodes import estimate_cost_usd

    assert estimate_cost_usd(None) is None
    assert estimate_cost_usd({}) is None


def test_agent_returns_pr_number_from_state():
    fake_patterns = [
        {"severity": "warning", "name": "Hardcoded Secret", "description": "Secret found in source"},
    ]

    fake_review = PRReview(
        pr_number=0,  # will be overwritten by review_code node
        comments=[
            ReviewComment(
                line_number=3,
                issue_type="security",
                severity="warning",
                description="Hardcoded secret detected",
                suggestion="Use environment variables",
            )
        ],
        overall_risk="medium",
        prompt_version="v1",
        latency_ms=0,
        cost_usd=0.0,
    )

    mock_structured_chain = MagicMock()
    mock_structured_chain.invoke.return_value = _structured_output_result(fake_review)

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_chain

    with patch("app.agent.nodes.retrieve_similar_patterns", return_value=fake_patterns), \
         patch("app.agent.nodes.ChatAnthropic", return_value=mock_llm):
        from app.agent.graph import agent
        result = agent.invoke({"diff": "+ secret = 'abc123'", "pr_number": 99})

    assert "review" in result
    review = result["review"]
    assert isinstance(review, PRReview)
    assert review.pr_number == 99


def test_agent_does_not_trust_model_generated_cost():
    fake_review = PRReview(
        pr_number=0,
        comments=[],
        overall_risk="low",
        prompt_version="v1",
        latency_ms=0,
        cost_usd=0.008,
    )

    mock_structured_chain = MagicMock()
    mock_structured_chain.invoke.return_value = _structured_output_result(
        fake_review,
        {"input_tokens": 1_000, "output_tokens": 1_000},
    )

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_chain

    with patch("app.agent.nodes.retrieve_similar_patterns", return_value=[]), \
         patch("app.agent.nodes.ChatAnthropic", return_value=mock_llm):
        from app.agent.graph import agent
        result = agent.invoke({"diff": "+ print('hello')", "pr_number": 7})

    assert result["review"].cost_usd == pytest.approx(0.018)
    assert result["review"].pr_number == 7
