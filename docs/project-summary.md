# PR Code Review Agent: Start-to-End Project Summary

This document explains what we built, why we built it, how it works, what changed during the project, and how to use or explain it later.

## 1. What This Project Is

This project is an automated GitHub PR review agent.

When someone opens a pull request, GitHub sends a webhook to our deployed backend. The backend runs a LangGraph agent that reviews the PR diff, finds security or code-quality issues, posts a structured review back to GitHub, records the run in Supabase, and traces the run in LangSmith.

The final production prompt is `v2`.

## 2. Final Status

The project is complete and working end to end.

Working pieces:

- GitHub webhook receives PR events.
- AWS API Gateway routes webhook calls to Lambda.
- Lambda runs the FastAPI app through Mangum.
- LangGraph runs the review flow.
- Weaviate provides RAG context from vulnerability patterns.
- Claude generates structured PR reviews.
- GitHub receives review summaries and inline comments.
- Supabase stores live run history.
- LangSmith records traces.
- Streamlit shows eval results and live production runs.
- `v1` and `v2` prompt comparison works.
- `v2` is deployed as production default.

Final production smoke test:

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

## 3. High-Level Architecture

```text
GitHub Pull Request
  -> GitHub webhook
  -> API Gateway
  -> AWS Lambda
  -> FastAPI app through Mangum
  -> LangGraph agent
      -> retrieve_patterns node
      -> review_code node
  -> GitHub review comments
  -> Supabase reviews table
  -> LangSmith trace
```

## 4. Main Files And What They Do

| File | Purpose |
|---|---|
| `app/main.py` | FastAPI webhook handler. Receives GitHub PR events and runs the agent. |
| `app/agent/graph.py` | Defines the LangGraph workflow. |
| `app/agent/nodes.py` | Agent nodes: retrieve RAG patterns and review code. |
| `app/agent/prompts.py` | Stores `v1` and `v2` prompt templates. |
| `app/agent/schemas.py` | Pydantic schema for structured PR review output. |
| `app/services/weaviate.py` | Connects to Weaviate and retrieves similar vulnerability patterns. |
| `app/services/github.py` | Fetches PR diffs and posts GitHub review comments. |
| `app/services/database.py` | Writes live run rows to Supabase using REST. |
| `app/services/tracing.py` | Configures LangSmith tracing. |
| `data/vulnerability_patterns.yaml` | Curated RAG knowledge base. |
| `scripts/seed_weaviate.py` | Seeds the RAG patterns into Weaviate. |
| `scripts/deploy_from_env.py` | Deploys SAM stack using values from `.env`. |
| `eval/ground_truth.json` | Manual labels used as answer key for evaluation. |
| `eval/dataset/` | Stored GitHub PR diffs for evaluation. |
| `eval/runner.py` | Runs evals and saves result JSON files. |
| `eval/judge.py` | LLM-as-judge comparison between ground truth and agent output. |
| `eval/dashboard.py` | Streamlit dashboard for eval metrics and live Supabase runs. |
| `template.yaml` | AWS SAM deployment template. |
| `docs/final-report.md` | Formal final report. |
| `docs/project-summary.md` | This simplified project summary. |

## 5. LangGraph Flow

The graph has two nodes.

### Node 1: `retrieve_patterns`

Input:

```text
PR diff
```

What it does:

- Sends the diff to Weaviate.
- Retrieves the top 5 similar vulnerability patterns.
- If Weaviate fails, it stores the error and continues with no patterns.

Why this matters:

RAG gives the model relevant security/code-quality patterns so it is less likely to make generic guesses.

### Node 2: `review_code`

Input:

```text
PR diff + retrieved patterns
```

What it does:

- Builds the selected prompt from `app/agent/prompts.py`.
- Sends the prompt to Claude.
- Enforces structured output using the `PRReview` Pydantic schema.
- Adds app-controlled telemetry:
  - `prompt_version`
  - `latency_ms`
  - `cost_usd`
  - `langsmith_trace_id`

Output:

```text
Structured PRReview object
```

## 6. RAG Pipeline

We store common vulnerability and code-quality patterns in Weaviate.

The source knowledge base is:

```text
data/vulnerability_patterns.yaml
```

Examples of stored patterns:

- hardcoded password
- hardcoded API key
- SQL injection
- command injection
- path traversal
- insecure deserialization
- missing auth check
- missing input validation
- resource leak
- sensitive data logged

Seeding command:

```bash
python scripts/seed_weaviate.py
```

At review time, the PR diff is used as a Weaviate `near_text` query. Weaviate returns similar patterns. The model receives those patterns as context, but it still must inspect the actual PR diff before commenting.

Important: RAG does not decide the answer. It only guides the model.

## 7. Prompt Versions

We added real prompt versioning in:

```text
app/agent/prompts.py
```

### `v1`

The original broad prompt.

Behavior:

- More aggressive.
- Finds more issues.
- Can produce more noisy or speculative comments.
- Higher recall.
- Lower precision.

### `v2`

The final production prompt.

Behavior:

- Stricter and evidence-first.
- Reviews changed lines only.
- Uses RAG patterns as guidance, not proof.
- Avoids speculative comments.
- Fewer false positives.
- Higher precision.
- Lower cost and latency.

Final decision:

```text
Production default = v2
```

Configured in:

- `.env`
- `.env.example`
- `template.yaml`

## 8. Prompt Comparison Results

We ran full evals for both prompts.

Commands used:

```bash
PROMPT_VERSION=v1 python -m eval.runner --delay-seconds 20
PROMPT_VERSION=v2 python -m eval.runner --delay-seconds 20
```

Result files:

```text
v1: eval/results/20260512T044124_results.json
v2: eval/results/20260512T044636_results.json
```

Latest comparison:

| Prompt | Avg recall | Avg precision | Avg latency | Avg cost |
|---|---:|---:|---:|---:|
| `v1` | 87.25% | 68.97% | 23.09s | $0.0256 |
| `v2` | 71.91% | 96.43% | 13.03s | $0.0169 |

Interpretation:

- `v1` catches more real issues, so recall is higher.
- `v2` produces cleaner comments, so precision is higher.
- `v2` writes fewer comments, so it is cheaper and faster.

Simple definitions:

```text
Recall = of all real issues, how many did we catch?
Precision = of all reported issues, how many were correct?
```

## 9. Evaluation Platform

Evaluation is separate from live GitHub PR review.

Live PR review answers:

```text
Did the agent review this PR and store the production run?
```

Eval answers:

```text
How good was the model compared to ground truth?
```

Eval files:

- `eval/ground_truth.json`: manual answer key.
- `eval/dataset/`: saved PR diffs.
- `eval/runner.py`: runs the agent on saved diffs.
- `eval/judge.py`: compares model output against ground truth.
- `eval/results/`: saved eval result files.
- `eval/dashboard.py`: Streamlit dashboard.

Run full eval:

```bash
python -m eval.runner --delay-seconds 20
```

Run one PR:

```bash
python -m eval.runner DaniManas__pr-review-agent__10
```

Run dashboard:

```bash
python -m streamlit run eval/dashboard.py
```

## 10. Streamlit Dashboard

The dashboard has two categories of views.

### Eval Views

These read local files from:

```text
eval/results/
```

Views:

- Overview Scores
- Per-Run Detail
- Prompt Version Comparison
- Cost & Latency Trends

### Live Runs

This reads production rows directly from Supabase.

It shows:

- PR number
- repo
- status
- prompt version
- overall risk
- comment count
- latency
- cost
- LangSmith trace ID
- error message

## 11. Dashboard Scope Filters

The dashboard has scope options.

### Latest Run

Shows only the newest eval result file.

Useful when:

```text
You just ran one eval and only want to inspect that run.
```

### Latest Per PR

Shows the newest result for each PR.

Useful when:

```text
You want a clean current snapshot of every evaluated PR.
```

### All Historical Runs

Shows all saved eval rows.

Useful when:

```text
You want to compare versions or see how results changed over time.
```

Important dashboard fix:

- Prompt Version Comparison uses all eval runs.
- Cost & Latency Trends uses all eval runs.

This is needed so `v1` and `v2` both appear in those graphs.

## 12. Supabase

Supabase stores production run rows in the `reviews` table.

Main columns:

- `pr_number`
- `repo`
- `prompt_version`
- `overall_risk`
- `comment_count`
- `latency_ms`
- `cost_usd`
- `status`
- `error_message`
- `langsmith_trace_id`
- `created_at`

Important issue we hit:

Supabase was paused, so PR `#10` did not insert into Supabase. The GitHub review still worked, but the database write failed with HTTP `521`.

After unpausing Supabase, PR `#11` inserted successfully.

Final verification PR `#12` also inserted successfully with `prompt_version=v2`.

## 13. LangSmith

LangSmith records traces for review runs and eval runs.

The dashboard shows trace IDs, not public links.

Why:

```text
LangSmith traces are private unless explicitly shared.
```

To find a trace:

- Open LangSmith.
- Open project `pr-review-agent`.
- Search by:
  - trace ID
  - `pr_number`
  - `pr_id`
  - unique code text from the PR

Example final trace ID:

```text
019e1aa4-0976-75f1-9cad-9b8f8a614bb5
```

## 14. Cost Tracking

Cost is estimated from Anthropic token usage metadata.

Configured pricing:

```text
ANTHROPIC_INPUT_COST_PER_1M_TOKENS=3.00
ANTHROPIC_OUTPUT_COST_PER_1M_TOKENS=15.00
```

Why `v2` costs less:

- It is stricter.
- It reports fewer comments.
- Fewer comments means fewer output tokens.
- Output tokens are expensive.

Older rows may show `N/A` or null because cost tracking was added later.

## 15. Deployment

Deployment uses AWS SAM.

Main files:

- `template.yaml`
- `scripts/deploy_from_env.py`
- `.env`

Build:

```bash
sam build
```

Deploy:

```bash
python scripts/deploy_from_env.py
```

The deploy script reads secrets and config from `.env` and passes them to SAM without printing secret values.

Live webhook URL:

```text
https://x0yaugkohi.execute-api.us-east-1.amazonaws.com/Prod/webhook
```

We verified the deployed Lambda environment:

```text
PROMPT_VERSION=v2
```

## 16. Important Fixes We Made

### Fixed Lambda packaging

Initial SAM builds failed because eval/dashboard dependencies like pandas, pyarrow, and Streamlit were being packaged into Lambda.

Fix:

- `requirements.txt` now contains Lambda runtime dependencies.
- `requirements-dev.txt` contains local eval/dashboard/test dependencies.
- `.samignore` and `.dockerignore` prevent local artifacts from entering the package.

### Removed heavy Supabase SDK from Lambda

The Supabase SDK pulled heavy dependencies through its storage package.

Fix:

```text
app/services/database.py now writes to Supabase using REST through httpx.
```

### Fixed dashboard cost handling

The dashboard previously crashed when `cost_usd` was null.

Fix:

```text
format_cost() displays N/A for missing cost.
```

### Fixed prompt comparison graph

Prompt comparison originally only showed `v2` when the sidebar scope was Latest Per PR.

Fix:

```text
Prompt Version Comparison always uses all eval result files.
```

### Fixed cost/latency graph scope

Cost & Latency also only showed `v2`.

Fix:

```text
Cost & Latency Trends now uses all eval result files.
```

### Added eval runner delay

Anthropic rate limits caused eval runs to fail.

Fix:

```bash
python -m eval.runner --delay-seconds 20
```

The runner also saves partial results if a later PR fails.

## 17. Hallucination Reduction

We reduce hallucinations through:

- RAG context from curated Weaviate patterns.
- Diff-only review input.
- Structured output schema.
- GitHub line/comment validation.
- Ground-truth eval with recall and precision.
- LLM judge comparison.
- LangSmith tracing.
- `v2` evidence-first prompt.

The most important improvement is `v2`, because it tells the model not to invent missing context and not to treat retrieved patterns as proof.

## 18. Final GitHub PR Tests

### PR `#10`

Purpose:

```text
Buggy PR to test issue detection.
```

Result:

- GitHub review worked.
- Eval result was strong.
- Supabase insert failed because Supabase was paused.
- PR was closed and branch deleted.

### PR `#11`

Purpose:

```text
Clean PR to verify Supabase after unpausing.
```

Result:

- GitHub review worked.
- Supabase row inserted successfully.
- PR was closed and branch deleted.

### PR `#12`

Purpose:

```text
Final production verification after deploying v2.
```

Result:

- GitHub review showed `Prompt Version: v2`.
- Supabase row showed `prompt_version=v2`.
- Overall risk was low.
- Cost and latency were recorded.
- PR was closed and branch deleted.

## 19. Current Commands To Remember

Run tests:

```bash
pytest tests/ eval/tests/ -q
```

Run Streamlit:

```bash
python -m streamlit run eval/dashboard.py
```

Run full v1/v2 comparison:

```bash
PROMPT_VERSION=v1 python -m eval.runner --delay-seconds 20
PROMPT_VERSION=v2 python -m eval.runner --delay-seconds 20
```

Deploy:

```bash
sam build
python scripts/deploy_from_env.py
```

Collect a PR diff for eval:

```bash
python -m eval.collector DaniManas/pr-review-agent <pr_number>
```

Run eval for one PR:

```bash
python -m eval.runner DaniManas__pr-review-agent__10
```

## 20. What Is Left

The implementation is complete.

Only optional future work remains:

- Add more manually labeled PRs.
- Automate eval runs in CI.
- Expand the Weaviate knowledge base.
- Add retry/backoff around Anthropic and Supabase transient failures.
- Improve dashboard filtering and export options.
- Add public/shared LangSmith trace links if needed for demos.

For presentation, the remaining manual task is to take screenshots:

- GitHub PR review
- Supabase row
- Streamlit Live Runs
- Streamlit Prompt Version Comparison
- LangSmith trace
