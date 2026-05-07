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
        result = judge_review(review, ground_truth_entry)

    assert isinstance(result, JudgeScore)
    assert result.recall == 0.5
    assert result.precision == 1.0
    assert "SQL injection" in result.false_negatives[0]


def test_judge_scores_clean_ground_truth_without_llm_call():
    review = PRReview(
        pr_number=9,
        comments=[
            ReviewComment(
                line_number=45,
                issue_type="logic",
                severity="warning",
                description="Empty cart behavior may surprise callers.",
                suggestion="Document the behavior.",
            )
        ],
        overall_risk="low",
        prompt_version="v1",
        latency_ms=100,
        cost_usd=None,
    )
    ground_truth_entry = {
        "pr_id": "owner__repo__9",
        "repo": "owner/repo",
        "pr_number": 9,
        "expected_issues": [],
        "overall_risk": "low",
    }

    with patch("eval.judge.ChatAnthropic") as mock_llm:
        from eval.judge import judge_review
        result = judge_review(review, ground_truth_entry)

    mock_llm.assert_not_called()
    assert result.true_positives == []
    assert len(result.false_positives) == 1
    assert result.false_negatives == []
    assert result.recall == 1.0
    assert result.precision == 0.0


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
    assert latency.score == pytest.approx(800 / 2000, abs=1e-3)
    assert latency.is_successful()

    cost = CostMetric(threshold_usd=0.01)
    cost.measure(result)
    assert cost.score == pytest.approx(0.002 / 0.01, abs=1e-3)
    assert cost.is_successful()


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

    with patch("eval.runner.agent") as mock_agent, \
         patch("eval.runner.judge_review", return_value=fake_score):
        mock_agent.invoke.return_value = {"review": fake_review, "langsmith_trace_id": "trace-abc"}

        from eval.runner import run_eval
        results = run_eval(
            ground_truth_path=str(gt_path),
            dataset_dir=str(dataset_dir),
            results_dir=str(results_dir),
        )

    assert len(results) == 1
    assert results[0].pr_id == "owner__repo__1"
    assert results[0].score.recall == 0.5
    invoke_kwargs = mock_agent.invoke.call_args.kwargs
    assert invoke_kwargs["config"]["run_name"] == "eval_review_owner__repo__1"
    assert invoke_kwargs["config"]["metadata"] == {
        "pr_id": "owner__repo__1",
        "repo": "owner/repo",
        "pr_number": 1,
        "prompt_version": "v1",
    }
    saved_files = list(results_dir.glob("*.json"))
    assert len(saved_files) == 1


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
            collect_pr("owner/repo", 42, dataset_dir=tmpdir)

        pr_id = "owner__repo__42"
        saved_path = os.path.join(tmpdir, f"{pr_id}.json")
        assert os.path.exists(saved_path)

        with open(saved_path) as f:
            data = json.load(f)

        assert data["pr_id"] == pr_id
        assert data["repo"] == "owner/repo"
        assert data["pr_number"] == 42
        assert fake_diff in data["diff"]


def test_dashboard_loads_result_file_metadata(tmp_path):
    old_result = EvalResult(
        pr_id="owner__repo__1",
        repo="owner/repo",
        pr_number=1,
        prompt_version="v1",
        review=_sample_review(),
        score=_sample_score(),
        langsmith_trace_id=None,
        run_at="2026-05-02T22:00:00Z",
    )
    new_result = EvalResult(
        pr_id="owner__repo__2",
        repo="owner/repo",
        pr_number=2,
        prompt_version="v1",
        review=_sample_review(),
        score=_sample_score(),
        langsmith_trace_id=None,
        run_at="2026-05-02T23:00:00Z",
    )
    (tmp_path / "20260502T220000_results.json").write_text(json.dumps([old_result.model_dump()]))
    (tmp_path / "20260502T230000_results.json").write_text(json.dumps([new_result.model_dump()]))

    from eval.dashboard import load_all_results

    df = load_all_results(str(tmp_path))

    assert set(df["result_file"]) == {
        "20260502T220000_results.json",
        "20260502T230000_results.json",
    }
    assert set(df["run_id"]) == {
        "20260502T220000",
        "20260502T230000",
    }


def test_dashboard_latest_results_keep_only_newest_result_file(tmp_path):
    old_result = EvalResult(
        pr_id="owner__repo__1",
        repo="owner/repo",
        pr_number=1,
        prompt_version="v1",
        review=_sample_review(),
        score=_sample_score(),
        langsmith_trace_id=None,
        run_at="2026-05-02T22:00:00Z",
    )
    new_results = [
        EvalResult(
            pr_id="owner__repo__1",
            repo="owner/repo",
            pr_number=1,
            prompt_version="v1",
            review=_sample_review(),
            score=_sample_score(),
            langsmith_trace_id=None,
            run_at="2026-05-02T23:00:00Z",
        ),
        EvalResult(
            pr_id="owner__repo__2",
            repo="owner/repo",
            pr_number=2,
            prompt_version="v1",
            review=_sample_review(),
            score=_sample_score(),
            langsmith_trace_id=None,
            run_at="2026-05-02T23:01:00Z",
        ),
    ]
    (tmp_path / "20260502T220000_results.json").write_text(json.dumps([old_result.model_dump()]))
    (tmp_path / "20260502T230000_results.json").write_text(
        json.dumps([result.model_dump() for result in new_results])
    )

    from eval.dashboard import filter_latest_run, load_all_results

    df = load_all_results(str(tmp_path))
    latest = filter_latest_run(df)

    assert len(latest) == 2
    assert latest["result_file"].nunique() == 1
    assert latest["result_file"].iloc[0] == "20260502T230000_results.json"


def test_dashboard_formats_missing_cost_as_unavailable():
    from eval.dashboard import format_cost

    assert format_cost(None) == "N/A"


def test_dashboard_loads_issue_lists_for_per_run_detail(tmp_path):
    result = EvalResult(
        pr_id="owner__repo__1",
        repo="owner/repo",
        pr_number=1,
        prompt_version="v1",
        review=_sample_review(),
        score=_sample_score(),
        langsmith_trace_id=None,
        run_at="2026-05-02T23:00:00Z",
    )
    path = tmp_path / "20260502T230000_results.json"
    path.write_text(json.dumps([result.model_dump()]))

    from eval.dashboard import get_issue_lists_for_row, load_all_results

    df = load_all_results(str(tmp_path))
    issues = get_issue_lists_for_row(df.iloc[0])

    assert issues["true_positives"] == ["Hardcoded secret on line 3"]
    assert issues["false_positives"] == []
    assert issues["false_negatives"] == ["SQL injection on line 12"]


def test_dashboard_sorts_weakest_prs_by_lowest_scores():
    import pandas as pd

    df = pd.DataFrame([
        {"pr_id": "good", "pr_number": 1, "recall": 0.9, "precision": 0.9, "comment_count": 3},
        {"pr_id": "low_precision", "pr_number": 2, "recall": 0.9, "precision": 0.2, "comment_count": 8},
        {"pr_id": "low_recall", "pr_number": 3, "recall": 0.1, "precision": 0.8, "comment_count": 4},
    ])

    from eval.dashboard import weakest_prs

    weak = weakest_prs(df, limit=2)

    assert weak["pr_id"].tolist() == ["low_recall", "low_precision"]
