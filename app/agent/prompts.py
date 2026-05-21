from typing import Callable


def format_patterns(patterns: list[dict]) -> str:
    return "\n".join(
        f"- [{p.get('severity', 'unknown')}] {p.get('name', '')}: {p.get('description', '')}"
        for p in patterns
    ) or "No patterns retrieved."


def build_v1_prompt(diff: str, patterns: list[dict]) -> str:
    patterns_text = format_patterns(patterns)
    return f"""You are an expert code reviewer. Review the following PR diff for security vulnerabilities, logic errors, and code quality issues.

Known vulnerability patterns relevant to this diff:
{patterns_text}

PR Diff:
{diff}

Review the diff carefully. For each issue found, specify:
- The line number in the diff where the issue appears
- issue_type: one of 'security', 'logic', 'quality'
- severity: one of 'critical', 'warning', 'info'
- A clear description of the problem
- A concrete suggestion to fix it

If no issues are found, return an empty comments list.
"""


def build_v2_prompt(diff: str, patterns: list[dict]) -> str:
    patterns_text = format_patterns(patterns)
    return f"""You are a strict senior code reviewer. Review only 
    the changed lines in the PR diff and report issues that are 
    directly supported by evidence in the diff.

Use the retrieved vulnerability patterns as guidance, not as proof. A pattern is relevant only when the changed code clearly shows the risky behavior.

Known vulnerability patterns relevant to this diff:
{patterns_text}

PR Diff:
{diff}

Return a structured review with high-signal findings only:
- Prefer security and correctness issues over style preferences.
- Report an issue only when you can point to a specific changed diff line.
- Do not invent missing surrounding code, authentication state, or caller behavior.
- Do not flag broad best-practice suggestions unless the diff contains a concrete failure mode.
- For each comment, include the changed line number, issue_type, severity, clear evidence, and a concrete fix.
- If the changed code is safe or only has speculative concerns, return an empty comments list and overall_risk 'low'.
"""


PROMPT_BUILDERS: dict[str, Callable[[str, list[dict]], str]] = {
    "v1": build_v1_prompt,
    "v2": build_v2_prompt,
}


def build_review_prompt(prompt_version: str, diff: str, patterns: list[dict]) -> str:
    try:
        builder = PROMPT_BUILDERS[prompt_version]
    except KeyError as exc:
        supported = ", ".join(sorted(PROMPT_BUILDERS))
        raise ValueError(f"Unsupported prompt version '{prompt_version}'. Supported versions: {supported}") from exc
    return builder(diff, patterns)
