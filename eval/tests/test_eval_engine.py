from typing import List
import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock, patch
import json
import os
import tempfile

from eval.schemas import JudgeScore, EvalResult
from app.agent.schemas import PRReview, ReviewComment


def _sample_review() -> PRReview:
    return PRReview(
        pr_number=1,
        comments=[
            ReviewComment(
                line_number=3,
                issue_type="security",
                severity="critical",
                description="Hardcoded secret",
                suggestion="Use env var",
            )
        ],
        overall_risk="high",
        prompt_version="v1",
        latency_ms=800,
        cost_usd=0.002,
    )


def _sample_review_unknown_cost() -> PRReview:
    return PRReview(
        pr_number=1,
        comments=[],
        overall_risk="low",
        prompt_version="v1",
        latency_ms=800,
    )


def _sample_score() -> JudgeScore:
    return JudgeScore(
        pr_id="owner__repo__1",
        true_positives=["Hardcoded secret on line 3"],
        false_positives=[],
        false_negatives=["SQL injection on line 12"],
        recall=0.5,
        precision=1.0,
        reasoning="Caught the hardcoded secret but missed SQL injection.",
    )


def test_judge_score_roundtrip():
    score = _sample_score()
    restored = JudgeScore.model_validate(score.model_dump())
    assert restored == score


def test_eval_result_roundtrip():
    result = EvalResult(
        pr_id="owner__repo__1",
        repo="owner/repo",
        pr_number=1,
        prompt_version="v1",
        review=_sample_review(),
        score=_sample_score(),
        langsmith_trace_id="abc-123",
        run_at="2026-04-27T10:00:00Z",
    )
    restored = EvalResult.model_validate(result.model_dump())
    assert restored.pr_id == "owner__repo__1"
    assert restored.score.recall == 0.5


def test_eval_result_langsmith_trace_defaults_to_none():
    result = EvalResult(
        pr_id="owner__repo__1",
        repo="owner/repo",
        pr_number=1,
        prompt_version="v1",
        review=_sample_review(),
        score=_sample_score(),
        run_at="2026-04-27T10:00:00Z",
    )

    assert result.langsmith_trace_id is None


def test_judge_score_missing_fields():
    with pytest.raises(ValidationError):
        JudgeScore()


def test_eval_result_missing_fields():
    with pytest.raises(ValidationError):
        EvalResult()


def test_judge_returns_judge_score():
    review = _sample_review()
    ground_truth_entry = {
        "pr_id": "owner__repo__1",
        "repo": "owner/repo",
        "pr_number": 1,
        "expected_issues": [
            {"issue_type": "security", "severity": "critical", "description": "Hardcoded secret on line 3"},
            {"issue_type": "security", "severity": "critical", "description": "SQL injection on line 12"},
        ],
        "overall_risk": "high",
    }

    fake_score = JudgeScore(
        pr_id="owner__repo__1",
        true_positives=["Hardcoded secret on line 3"],
        false_positives=[],
        false_negatives=["SQL injection on line 12"],
        recall=0.5,
        precision=1.0,
        reasoning="Caught 1 of 2 expected issues.",
    )

    mock_structured_chain = MagicMock()
    mock_structured_chain.invoke.return_value = fake_score

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_chain

    with patch("eval.judge.ChatAnthropic", return_value=mock_llm):
        from eval.judge import judge_review
        result = judge_review(review, ground_truth_entry, api_key="test-key")

    assert isinstance(result, JudgeScore)
    assert result.recall == 0.5
    assert result.precision == 1.0
    assert "SQL injection" in result.false_negatives[0]


def test_judge_recomputes_inconsistent_llm_scores():
    review = _sample_review()
    ground_truth_entry = {
        "pr_id": "owner__repo__1",
        "repo": "owner/repo",
        "pr_number": 1,
        "expected_issues": [
            {"issue_type": "security", "severity": "critical", "description": "Hardcoded secret"},
            {"issue_type": "security", "severity": "critical", "description": "SQL injection"},
        ],
        "overall_risk": "high",
    }

    fake_score = JudgeScore(
        pr_id="wrong",
        true_positives=["Hardcoded secret"],
        false_positives=["Style nit"],
        false_negatives=["SQL injection"],
        recall=1.0,
        precision=1.0,
        reasoning="LLM returned inconsistent math.",
    )

    mock_structured_chain = MagicMock()
    mock_structured_chain.invoke.return_value = fake_score

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_chain

    with patch("eval.judge.ChatAnthropic", return_value=mock_llm):
        from eval.judge import judge_review
        result = judge_review(review, ground_truth_entry, api_key="test-key", model="test-model")

    assert result.pr_id == "owner__repo__1"
    assert result.recall == 0.5
    assert result.precision == 0.5


def test_recall_metric_score():
    score = JudgeScore(
        pr_id="owner__repo__1",
        true_positives=["issue A", "issue B"],
        false_positives=[],
        false_negatives=["issue C"],
        recall=0.667,
        precision=1.0,
        reasoning="Caught 2 of 3.",
    )
    result = EvalResult(
        pr_id="owner__repo__1",
        repo="owner/repo",
        pr_number=1,
        prompt_version="v1",
        review=_sample_review(),
        score=score,
        langsmith_trace_id=None,
        run_at="2026-04-27T10:00:00Z",
    )

    from eval.metrics import RecallMetric, PrecisionMetric, ValidityMetric, LatencyMetric, CostMetric
    recall = RecallMetric()
    recall.measure(result)
    assert recall.score == pytest.approx(0.667, abs=1e-3)
    assert recall.is_successful()

    precision = PrecisionMetric()
    precision.measure(result)
    assert precision.score == pytest.approx(1.0, abs=1e-3)

    validity = ValidityMetric()
    validity.measure(result)
    assert validity.score == 1.0

    latency = LatencyMetric(threshold_ms=2000)
    latency.measure(result)
    assert latency.score == 1.0
    assert latency.is_successful()

    cost = CostMetric(threshold_usd=0.01)
    cost.measure(result)
    assert cost.score == pytest.approx(0.002 / 0.01, abs=1e-3)
    assert cost.is_successful()


def test_cost_metric_handles_unknown_cost():
    result = EvalResult(
        pr_id="owner__repo__1",
        repo="owner/repo",
        pr_number=1,
        prompt_version="v1",
        review=_sample_review_unknown_cost(),
        score=_sample_score(),
        langsmith_trace_id=None,
        run_at="2026-04-27T10:00:00Z",
    )

    from eval.metrics import CostMetric
    cost = CostMetric(threshold_usd=0.01)
    assert cost.measure(result) is None
    assert cost.is_successful() is None


def test_dashboard_formats_unknown_cost():
    from eval.dashboard import format_cost

    assert format_cost(None) == "N/A"
    assert format_cost(0.002) == "$0.0020"


def test_runner_produces_eval_results(tmp_path):
    import json

    gt = [
        {
            "pr_id": "owner__repo__1",
            "repo": "owner/repo",
            "pr_number": 1,
            "expected_issues": [
                {"issue_type": "security", "severity": "critical", "description": "Hardcoded secret"}
            ],
            "overall_risk": "high",
        }
    ]
    gt_path = tmp_path / "ground_truth.json"
    gt_path.write_text(json.dumps(gt))

    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    (dataset_dir / "owner__repo__1.json").write_text(
        json.dumps({"pr_id": "owner__repo__1", "repo": "owner/repo", "pr_number": 1, "diff": "+secret='abc'"})
    )

    results_dir = tmp_path / "results"

    fake_review = _sample_review()
    fake_score = _sample_score()

    mock_agent = MagicMock()
    mock_agent.invoke.return_value = {"review": fake_review, "langsmith_trace_id": "trace-abc"}

    from eval.runner import run_eval
    results = run_eval(
        ground_truth_path=str(gt_path),
        dataset_dir=str(dataset_dir),
        results_dir=str(results_dir),
        agent_runner=mock_agent,
        judge_fn=MagicMock(return_value=fake_score),
        prompt_version="v1",
    )

    assert len(results) == 1
    assert results[0].pr_id == "owner__repo__1"
    assert results[0].score.recall == 0.5
    saved_files = list(results_dir.glob("*.json"))
    assert len(saved_files) == 1
    assert saved_files[0].read_text().endswith("\n")


def test_runner_continues_after_entry_error(tmp_path):
    gt = [
        {
            "pr_id": "owner__repo__1",
            "repo": "owner/repo",
            "pr_number": 1,
            "expected_issues": [],
            "overall_risk": "high",
        },
        {
            "pr_id": "owner__repo__2",
            "repo": "owner/repo",
            "pr_number": 2,
            "expected_issues": [],
            "overall_risk": "high",
        },
    ]
    gt_path = tmp_path / "ground_truth.json"
    gt_path.write_text(json.dumps(gt))

    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    for pr_id in ("owner__repo__1", "owner__repo__2"):
        (dataset_dir / f"{pr_id}.json").write_text(
            json.dumps({"pr_id": pr_id, "repo": "owner/repo", "pr_number": 1, "diff": "+change"})
        )

    fake_review = _sample_review()
    fake_score = _sample_score()
    mock_agent = MagicMock()
    mock_agent.invoke.side_effect = [
        RuntimeError("agent failed"),
        {"review": fake_review, "langsmith_trace_id": None},
    ]

    from eval.runner import run_eval
    results = run_eval(
        ground_truth_path=str(gt_path),
        dataset_dir=str(dataset_dir),
        results_dir=str(tmp_path / "results"),
        agent_runner=mock_agent,
        judge_fn=MagicMock(return_value=fake_score),
        prompt_version="v1",
    )

    assert len(results) == 1
    assert results[0].pr_id == "owner__repo__2"


def test_collector_saves_dataset_file():
    import json
    import os
    import tempfile

    fake_diff = "+password = 'hunter2'\n+query = f'SELECT * FROM users WHERE id={uid}'"

    mock_file = MagicMock()
    mock_file.patch = fake_diff
    mock_file.filename = "app.py"

    mock_pr = MagicMock()
    mock_pr.number = 42
    mock_pr.get_files.return_value = [mock_file]

    mock_repo = MagicMock()
    mock_repo.get_pull.return_value = mock_pr

    mock_github = MagicMock()
    mock_github.get_repo.return_value = mock_repo

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("eval.collector.Github", return_value=mock_github):
            from eval.collector import collect_pr
            collect_pr("owner/repo", 42, dataset_dir=tmpdir, github_token="test-token")

        pr_id = "owner__repo__42"
        saved_path = os.path.join(tmpdir, f"{pr_id}.json")
        assert os.path.exists(saved_path)

        with open(saved_path) as f:
            data = json.load(f)

        assert data["pr_id"] == pr_id
        assert data["repo"] == "owner/repo"
        assert data["pr_number"] == 42
        assert fake_diff in data["diff"]
        with open(saved_path) as f:
            assert f.read().endswith("\n")


def test_collector_requires_github_token():
    from eval.collector import collect_pr

    with pytest.raises(ValueError, match="GitHub token is required"):
        collect_pr("owner/repo", 42, github_token="")


def test_collector_validates_repo_and_pr_number():
    from eval.collector import collect_pr

    with pytest.raises(ValueError, match="owner/repo"):
        collect_pr("../owner/repo", 42, github_token="test-token")

    with pytest.raises(ValueError, match="positive"):
        collect_pr("owner/repo", 0, github_token="test-token")
