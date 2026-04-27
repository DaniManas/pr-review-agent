import time
from typing import Any

from langchain_anthropic import ChatAnthropic
from langsmith import get_current_run_tree

from app.agent.schemas import PRReview
from app.config import settings
from app.services.weaviate import retrieve_similar_patterns


def retrieve_patterns(state: dict[str, Any]) -> dict[str, Any]:
    """Node 1: embed diff, retrieve top-5 similar vulnerability patterns."""
    diff = state["diff"]
    try:
        patterns = retrieve_similar_patterns(diff, k=5)
    except Exception as e:
        # Weaviate unavailable — continue with empty patterns, agent still runs
        patterns = []
        state["weaviate_error"] = str(e)
    return {**state, "patterns": patterns}


def review_code(state: dict[str, Any]) -> dict[str, Any]:
    """Node 2: send diff + patterns to Claude, enforce PRReview schema."""
    diff = state["diff"]
    pr_number = state["pr_number"]
    patterns = state.get("patterns", [])

    patterns_text = "\n".join(
        f"- [{p.get('severity', 'unknown')}] {p.get('name', '')}: {p.get('description', '')}"
        for p in patterns
    ) or "No patterns retrieved."

    prompt = f"""You are an expert code reviewer. Review the following PR diff for security vulnerabilities, logic errors, and code quality issues.

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

    llm = ChatAnthropic(
        model="claude-sonnet-4-6",
        api_key=settings.anthropic_api_key,
    )
    structured_llm = llm.with_structured_output(PRReview)

    start = time.perf_counter()
    review: PRReview = structured_llm.invoke(prompt)
    latency_ms = int((time.perf_counter() - start) * 1000)

    # Capture LangSmith trace ID for observability
    try:
        run_tree = get_current_run_tree()
        langsmith_trace_id = str(run_tree.id) if run_tree else None
    except Exception:
        langsmith_trace_id = None

    # Inject fields not produced by LLM
    review.pr_number = pr_number
    review.prompt_version = settings.prompt_version
    review.latency_ms = latency_ms
    # cost_usd is application telemetry, not something the LLM can report reliably.
    # Keep it unknown until this node reads measured usage metadata from the provider.
    review.cost_usd = None

    return {**state, "review": review, "langsmith_trace_id": langsmith_trace_id}
