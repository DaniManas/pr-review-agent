from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.agent.schemas import PRReview, ReviewComment


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
    mock_structured_chain.invoke.return_value = fake_review

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
    mock_structured_chain.invoke.return_value = fake_review

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
    mock_structured_chain.invoke.return_value = fake_review

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_chain

    with patch("app.agent.nodes.retrieve_similar_patterns", return_value=[]), \
         patch("app.agent.nodes.ChatAnthropic", return_value=mock_llm):
        from app.agent.graph import agent
        result = agent.invoke({"diff": "+ print('hello')", "pr_number": 7})

    assert result["review"].cost_usd is None
