import json
import os
import re
import sys
from github import Github, GithubException

REPO_NAME_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*/"
    r"[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*"
)


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
    max_files: int = 300,
    max_diff_bytes: int = 1_000_000,
    overwrite: bool = False,
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
    try:
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        files = list(pr.get_files())
    except GithubException as e:
        raise RuntimeError(f"Failed to collect GitHub PR {repo_name}#{pr_number}: {e.status}") from e

    diff_parts = []
    total_bytes = 0
    for file_count, f in enumerate(files, start=1):
        if file_count > max_files:
            break
        if f.patch:
            part = f"--- {f.filename}\n{f.patch}"
            part_bytes = len(part.encode("utf-8"))
            if total_bytes + part_bytes > max_diff_bytes:
                remaining = max_diff_bytes - total_bytes
                if remaining > 0:
                    diff_parts.append(part.encode("utf-8")[:remaining].decode("utf-8", errors="ignore"))
                break
            diff_parts.append(part)
            total_bytes += part_bytes
    diff = "\n".join(diff_parts)

    pr_id = f"{repo_name.replace('/', '__')}__{pr_number}"
    os.makedirs(dataset_dir, exist_ok=True)
    out_path = _safe_output_path(dataset_dir, f"{pr_id}.json")
    if os.path.exists(out_path) and not overwrite:
        raise FileExistsError(f"Dataset already exists: {out_path}")

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
