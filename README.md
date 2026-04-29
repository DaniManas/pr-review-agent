# PR Code Review Agent

PR Code Review Agent — A LangGraph agent that automatically reviews GitHub Pull Request diffs for security issues and code quality problems, posts structured comments, and traces every run in LangSmith.

## Architecture

```
Developer opens PR
  → GitHub sends POST to API Gateway URL
    → AWS Lambda (FastAPI + Mangum) receives webhook
      → LangGraph agent runs:
          1. Embeds diff, retrieves top-5 similar vulnerability patterns from Weaviate Cloud (RAG)
          2. Sends diff + patterns to Claude API, enforces Pydantic PRReview schema on output
      → Posts structured review comments to GitHub PR via GitHub API
      → Writes run record (prompt_version, latency_ms, cost_usd when known) to Supabase PostgreSQL
      → Entire run traced automatically in LangSmith
```

## Tech Stack

| Tool | Purpose |
|---|---|
| LangGraph | Agent orchestration |
| Claude API | LLM backbone |
| Weaviate Cloud | Vector store (RAG) |
| Supabase | PostgreSQL run history |
| LangSmith | Tracing |
| FastAPI + Mangum | Webhook + Lambda adapter |
| AWS SAM | Deployment |

## Current Limits

- Cost is displayed as `N/A` until provider usage metadata is wired into the agent. LangSmith tracing is enabled, but cost calculation is not implemented yet.
- Inline review comments can fall back to a body-only review when GitHub rejects generated line positions.
- The deployed Lambda timeout is 90 seconds.

## Local Development

1. Clone the repo
2. `cd pr-review-agent`
3. `python3.11 -m venv venv && source venv/bin/activate`
4. `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and fill in all values (see `.env.example` walkthrough below)
6. Seed Weaviate: `python scripts/seed_weaviate.py`
7. Start server: `uvicorn app.main:app --reload`
8. Test with sample payload:
   ```bash
   curl -X POST http://localhost:8000/webhook \
     -H "X-GitHub-Event: pull_request" \
     -H "X-Hub-Signature-256: sha256=$(echo -n @sample_payloads/pr_opened.json | openssl dgst -sha256 -hmac $GITHUB_WEBHOOK_SECRET | awk '{print $2}')" \
     -H "Content-Type: application/json" \
     -d @sample_payloads/pr_opened.json
   ```
   > Note: This requires a real GitHub token, Weaviate, Supabase, and Anthropic key in `.env`
9. Run tests: `pytest tests/ -v`

## .env.example Walkthrough

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key (get from console.anthropic.com) |
| `GITHUB_TOKEN` | GitHub personal access token (needs `repo` + `pull_requests:write` scopes) |
| `GITHUB_WEBHOOK_SECRET` | Secret string you set when configuring the GitHub webhook |
| `WEAVIATE_URL` | Weaviate Cloud cluster URL (e.g. https://xxx.weaviate.network) |
| `WEAVIATE_API_KEY` | Weaviate Cloud API key |
| `SUPABASE_URL` | Supabase project URL (from project settings) |
| `SUPABASE_SERVICE_KEY` | Supabase service role key (not anon key — needed for write access) |
| `LANGSMITH_API_KEY` | LangSmith API key (from smith.langchain.com) |
| `LANGSMITH_PROJECT` | LangSmith project name (e.g. `pr-review-agent`) |
| `PROMPT_VERSION` | String tag for the prompt version (e.g. `v1`) |

## Supabase Setup (One-Time)

Run this SQL in the Supabase SQL editor (project dashboard → SQL editor):

```sql
CREATE TABLE reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pr_number INT NOT NULL,
    repo TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    overall_risk TEXT,
    comment_count INT,
    latency_ms INT,
    cost_usd FLOAT,
    status TEXT NOT NULL DEFAULT 'success',
    error_message TEXT,
    langsmith_trace_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Deployment (AWS SAM)

```bash
# First time
sam build
sam deploy --guided

# Subsequent deploys
sam build --use-container
sam deploy --no-confirm-changeset --no-fail-on-empty-changeset
```

After deploy, copy the `WebhookUrl` output and configure it as the GitHub webhook URL for your repo (Settings → Webhooks → Add webhook).

## Example Review Output

```
## PR Review — overall risk: high

**Security [critical]** line 5: Hardcoded password detected
→ Use environment variable instead: `password = os.environ["DB_PASSWORD"]`

**Security [critical]** line 12: SQL injection via f-string
→ Use parameterized queries: `cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))`
```

## Running Tests

```bash
pytest tests/ -v
```

All tests use mocks — no real API keys needed to run the test suite.

## Phase 2 — Evaluation Platform

### Setup

1. Labels are pre-written in `eval/ground_truth.json` (3 PRs: #1, #2, #6 in `DaniManas/pr-review-agent`)
2. Dataset diffs are pre-collected in `eval/dataset/` — to re-collect or add more:
   ```bash
   python -m eval.collector DaniManas/pr-review-agent <pr_number>
   ```
3. Run the eval suite (calls agent + LLM judge on each PR):
   ```bash
   python -m eval.runner
   ```
4. Launch the dashboard:
   ```bash
   streamlit run eval/dashboard.py
   ```

### Eval Structure

| File | Purpose |
|---|---|
| `eval/ground_truth.json` | Manually-labeled answer key — 3 PRs with known vulnerabilities |
| `eval/dataset/` | PR diffs collected via GitHub API |
| `eval/runner.py` | Runs agent on each dataset PR, scores with LLM judge, saves results |
| `eval/judge.py` | LLM-as-judge comparing agent output to ground truth (Claude structured output) |
| `eval/metrics.py` | DeepEval metrics: recall, precision, validity, latency, cost |
| `eval/dashboard.py` | Streamlit dashboard — Overview, Per-Run, Prompt Comparison, Cost/Latency |
| `eval/results/` | Timestamped JSON output from each runner execution |
