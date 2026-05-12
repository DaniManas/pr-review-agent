import json
import os
import time
import argparse
from datetime import datetime, timezone
from typing import List

from app.agent.graph import agent
from app.config import settings
from app.services.tracing import configure_langsmith_tracing
from eval.judge import judge_review
from eval.schemas import EvalResult


def _review_run_config(entry: dict) -> dict:
    return {
        "run_name": f"eval_review_{entry['pr_id']}",
        "metadata": {
            "pr_id": entry["pr_id"],
            "repo": entry["repo"],
            "pr_number": entry["pr_number"],
            "prompt_version": settings.prompt_version,
        },
    }


def run_eval(
    ground_truth_path: str = "eval/ground_truth.json",
    dataset_dir: str = "eval/dataset",
    results_dir: str = "eval/results",
    pr_ids: set[str] | None = None,
    delay_seconds: float = 0,
) -> List[EvalResult]:
    configure_langsmith_tracing()

    with open(ground_truth_path) as f:
        ground_truth = json.load(f)

    results: List[EvalResult] = []
    selected_entries = [
        entry for entry in ground_truth
        if not pr_ids or entry["pr_id"] in pr_ids
    ]
    try:
        for index, entry in enumerate(selected_entries):
            if index and delay_seconds > 0:
                print(f"[WAIT] Sleeping {delay_seconds:.1f}s before next PR")
                time.sleep(delay_seconds)

            result = run_eval_entry(entry, dataset_dir)
            if result:
                results.append(result)
    finally:
        if results:
            save_results(results, results_dir)

    return results


def run_eval_entry(entry: dict, dataset_dir: str) -> EvalResult | None:
    pr_id = entry["pr_id"]
    dataset_path = os.path.join(dataset_dir, f"{pr_id}.json")

    if not os.path.exists(dataset_path):
        print(f"[SKIP] No dataset file for {pr_id}")
        return None

    with open(dataset_path) as f:
        dataset_entry = json.load(f)

    diff = dataset_entry["diff"]
    pr_number = entry["pr_number"]

    state = agent.invoke(
        {"diff": diff, "pr_number": pr_number},
        config=_review_run_config(entry),
    )
    review = state["review"]
    langsmith_trace_id = state.get("langsmith_trace_id")

    score = judge_review(review, entry)

    result = EvalResult(
        pr_id=pr_id,
        repo=entry["repo"],
        pr_number=pr_number,
        prompt_version=settings.prompt_version,
        review=review,
        score=score,
        langsmith_trace_id=langsmith_trace_id,
        run_at=datetime.now(timezone.utc).isoformat(),
    )
    print(f"[DONE] {pr_id} — recall={score.recall:.2f} precision={score.precision:.2f}")
    return result


def save_results(results: List[EvalResult], results_dir: str) -> str:
    os.makedirs(results_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = os.path.join(results_dir, f"{timestamp}_results.json")
    with open(out_path, "w") as f:
        json.dump([r.model_dump() for r in results], f, indent=2)

    print(f"[SAVED] {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run PR review evals.")
    parser.add_argument("pr_ids", nargs="*", help="Optional PR IDs such as DaniManas__pr-review-agent__10")
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=float(os.getenv("EVAL_DELAY_SECONDS", "0")),
        help="Seconds to wait between PRs to avoid model rate limits.",
    )
    args = parser.parse_args()

    selected_pr_ids = set(args.pr_ids) or None
    run_eval(pr_ids=selected_pr_ids, delay_seconds=args.delay_seconds)
