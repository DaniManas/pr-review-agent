import json
import os
from github import Github


def collect_pr(
    repo_name: str,
    pr_number: int,
    dataset_dir: str = "eval/dataset",
    github_token: str | None = None,
) -> str:
    if github_token is None:
        from app.config import settings
        github_token = settings.github_token

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
    out_path = os.path.join(dataset_dir, f"{pr_id}.json")

    with open(out_path, "w") as fh:
        json.dump({"pr_id": pr_id, "repo": repo_name, "pr_number": pr_number, "diff": diff}, fh, indent=2)

    return out_path


if __name__ == "__main__":
    import sys
    repo_arg = sys.argv[1]
    pr_arg = int(sys.argv[2])
    path = collect_pr(repo_arg, pr_arg)
    print(f"Saved: {path}")
