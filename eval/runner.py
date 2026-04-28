import json
import os
from datetime import datetime, timezone
from typing import List

from eval.schemas import EvalResult


def run_eval(
    ground_truth_path: str = "eval/ground_truth.json",
    dataset_dir: str = "eval/dataset",
    results_dir: str = "eval/results",
    agent_runner=None,
    judge_fn=None,
    prompt_version: str | None = None,
) -> List[EvalResult]:
    if agent_runner is None:
        from app.agent.graph import agent
        agent_runner = agent
    if judge_fn is None:
        from eval.judge import judge_review
        judge_fn = judge_review
    if prompt_version is None:
        from app.config import settings
        prompt_version = settings.prompt_version

    with open(ground_truth_path) as f:
        ground_truth = json.load(f)

    results: List[EvalResult] = []
    for entry in ground_truth:
        pr_id = entry["pr_id"]
        dataset_path = os.path.join(dataset_dir, f"{pr_id}.json")

        if not os.path.exists(dataset_path):
            print(f"[SKIP] No dataset file for {pr_id}")
            continue

        with open(dataset_path) as f:
            dataset_entry = json.load(f)

        diff = dataset_entry["diff"]
        pr_number = entry["pr_number"]

        state = agent_runner.invoke({"diff": diff, "pr_number": pr_number})
        review = state["review"]
        langsmith_trace_id = state.get("langsmith_trace_id")

        score = judge_fn(review, entry)

        result = EvalResult(
            pr_id=pr_id,
            repo=entry["repo"],
            pr_number=pr_number,
            prompt_version=prompt_version,
            review=review,
            score=score,
            langsmith_trace_id=langsmith_trace_id,
            run_at=datetime.now(timezone.utc).isoformat(),
        )
        results.append(result)
        print(f"[DONE] {pr_id} — recall={score.recall:.2f} precision={score.precision:.2f}")

    os.makedirs(results_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = os.path.join(results_dir, f"{timestamp}_results.json")
    with open(out_path, "w") as f:
        json.dump([r.model_dump() for r in results], f, indent=2)

    print(f"[SAVED] {out_path}")
    return results


if __name__ == "__main__":
    run_eval()
