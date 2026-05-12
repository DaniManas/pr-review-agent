# Final Report: PR Code Review Agent

## Goal

Build an automated PR review agent that reads GitHub pull request diffs, identifies security and code-quality issues, posts structured GitHub review comments, traces each run, stores operational telemetry, and evaluates model quality against ground truth.

## Architecture

```text
GitHub PR
  -> GitHub webhook
  -> API Gateway
  -> AWS Lambda (FastAPI + Mangum)
  -> LangGraph agent
      -> retrieve_patterns node
      -> review_code node
  -> GitHub review comments
  -> Supabase reviews row
  -> LangSmith trace
```

## Agent Flow

The LangGraph graph has two main nodes.

`retrieve_patterns` receives the PR diff and queries Weaviate for the top similar vulnerability patterns. The knowledge base contains curated security and quality patterns such as hardcoded secrets, SQL injection, command injection, path traversal, insecure deserialization, missing auth checks, and resource leaks.

`review_code` sends the diff plus retrieved patterns to Claude and enforces the structured `PRReview` Pydantic schema. The schema keeps outputs consistent: PR number, comments, issue type, severity, line number, suggestion, overall risk, latency, prompt version, and estimated cost.

If Weaviate retrieval fails, the agent still reviews the PR with no retrieved patterns. RAG improves grounding but is not a hard dependency for the review path.

## Evaluation Method

The evaluation platform uses manually labeled ground truth in `eval/ground_truth.json`. Each entry lists expected issues for a PR. The runner loads the collected diff from `eval/dataset/`, runs the agent, then uses an LLM judge to compare expected issues against actual review comments.

The judge returns:

- true positives: expected issues correctly found
- false positives: extra or unsupported comments
- false negatives: expected issues missed
- recall: how many expected issues were found
- precision: how many reported issues were correct

Streamlit reads saved result files from `eval/results/` and shows overview metrics, per-run details, prompt comparison, cost/latency trends, and live Supabase runs.

## Prompt Versions

`v1` is the original broad review prompt. It is more aggressive and tends to catch more issues, but it also produces more noisy findings.

`v2` is the current production default. It is stricter and evidence-first: it asks the model to review changed lines, avoid speculative findings, and use RAG patterns as guidance rather than proof.

Latest full-dataset comparison:

| Prompt | Avg recall | Avg precision | Avg latency | Avg cost |
|---|---:|---:|---:|---:|
| `v1` | 87.25% | 68.97% | 23.09s | $0.0256 |
| `v2` | 71.91% | 96.43% | 13.03s | $0.0169 |

Decision: use `v2` in production because PR review bots should prioritize trustworthy, low-noise comments for developers. `v1` remains useful for higher-recall security scanning experiments.

## Production Verification

Production is deployed on AWS Lambda through SAM. The live webhook URL is:

```text
https://x0yaugkohi.execute-api.us-east-1.amazonaws.com/Prod/webhook
```

Final smoke test:

| Field | Value |
|---|---|
| PR | `#12` |
| prompt_version | `v2` |
| status | `success` |
| overall_risk | `low` |
| comment_count | `0` |
| latency_ms | `1803` |
| cost_usd | `$0.005697` |
| langsmith_trace_id | `019e1aa4-0976-75f1-9cad-9b8f8a614bb5` |

## Dashboard

The Streamlit dashboard has two complementary data views.

Eval views use local result files and answer model-quality questions: recall, precision, false positives, false negatives, prompt comparison, cost, and latency.

Live Runs reads Supabase production rows and answers operational questions: which PRs were reviewed, whether they succeeded, prompt version used, cost, latency, overall risk, and LangSmith trace ID.

## Hallucination Controls

The project reduces hallucinations through:

- RAG context from curated vulnerability patterns
- diff-only review scope
- explicit prompt instructions
- structured Pydantic output validation
- GitHub line/comment validation
- ground-truth evaluation with recall and precision
- LangSmith tracing for input/output inspection
- `v2` evidence-first prompt behavior

## Known Limitations

- Ground truth labels are manual and take time to expand.
- Eval scoring is offline; it runs when `eval.runner` is executed, not automatically for every production PR.
- LangSmith traces are private unless explicitly shared, so dashboard links show trace IDs rather than public URLs.
- The RAG knowledge base is small and curated manually.
- Prompt comparison results depend on the current labeled dataset size and may change as more PRs are labeled.

## Next Improvements

- Add more labeled PRs to improve eval confidence.
- Automate eval runs in CI or a scheduled job.
- Add a dashboard filter for prompt-version-specific historical runs.
- Expand the Weaviate pattern library with more real-world code review examples.
- Add retry/backoff around provider rate limits and transient Supabase failures.
