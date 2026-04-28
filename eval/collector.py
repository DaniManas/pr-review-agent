import json
import os
import re
import sys
from github import Github

REPO_NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def _safe_output_path(dataset_dir: str, filename: str) -> str:
    base_dir = os.path.abspath(dataset_dir)
    out_path = os.path.abspath(os.path.join(base_dir, filename))
    if os.path.commonpath([base_dir, out_path]) != base_dir:
        raise ValueError("Dataset output path escapes dataset_dir")
    return out_path


def collect_pr(
    repo_name: str,
    pr_number: int,
    dataset_dir: str = "eval/dataset",
    github_token: str | None = None,
) -> str:
    if not REPO_NAME_PATTERN.fullmatch(repo_name):
        raise ValueError("Repository name must use owner/repo format")
    if pr_number <= 0:
        raise ValueError("PR number must be positive")

    if github_token is None:
        from app.config import settings
        github_token = settings.github_token
    if not github_token or not github_token.strip():
        raise ValueError("GitHub token is required")
    github_token = github_token.strip()

    g = Github(github_token)
    repo = g.get_repo(repo_name)
    pr = repo.get_pull(pr_number)

    diff_parts = []
    for f in pr.get_files():
        if f.patch:
            diff_parts.append(f"--- {f.filename}\n{f.patch}")
    diff = "\n".join(diff_parts)

    pr_id = f"{repo_name.replace('/', '__')}__{pr_number}"
    os.makedirs(dataset_dir, exist_ok=True)
    out_path = _safe_output_path(dataset_dir, f"{pr_id}.json")

    with open(out_path, "w") as fh:
        json.dump({"pr_id": pr_id, "repo": repo_name, "pr_number": pr_number, "diff": diff}, fh, indent=2)
        fh.write("\n")

    return out_path


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python -m eval.collector <repo> <pr_number>")
    repo_arg = sys.argv[1]
    try:
        pr_arg = int(sys.argv[2])
    except ValueError:
        sys.exit("PR number must be an integer")
    path = collect_pr(repo_arg, pr_arg)
    print(f"Saved: {path}")
