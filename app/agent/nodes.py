import time
from typing import Any

from langchain_anthropic import ChatAnthropic
from langsmith import get_current_run_tree

from app.agent.prompts import build_review_prompt
from app.agent.schemas import PRReview
from app.config import settings
from app.services.weaviate import retrieve_similar_patterns


def estimate_cost_usd(usage_metadata: dict[str, Any] | None) -> float | None:
    if not usage_metadata:
        return None

    input_tokens = usage_metadata.get("input_tokens")
    output_tokens = usage_metadata.get("output_tokens")
    if input_tokens is None or output_tokens is None:
        return None

    input_cost = (input_tokens / 1_000_000) * settings.anthropic_input_cost_per_1m_tokens
    output_cost = (output_tokens / 1_000_000) * settings.anthropic_output_cost_per_1m_tokens
    return round(input_cost + output_cost, 6)


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
    prompt = build_review_prompt(settings.prompt_version, diff, patterns)

    llm = ChatAnthropic(
        model="claude-sonnet-4-6",
        api_key=settings.anthropic_api_key,
    )
    structured_llm = llm.with_structured_output(PRReview, include_raw=True)

    start = time.perf_counter()
    llm_result = structured_llm.invoke(prompt)
    latency_ms = int((time.perf_counter() - start) * 1000)
    if llm_result.get("parsing_error"):
        raise llm_result["parsing_error"]
    review: PRReview = llm_result["parsed"]
    raw_response = llm_result.get("raw")
    usage_metadata = getattr(raw_response, "usage_metadata", None)

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
    review.cost_usd = estimate_cost_usd(usage_metadata)

    return {**state, "review": review, "langsmith_trace_id": langsmith_trace_id}
