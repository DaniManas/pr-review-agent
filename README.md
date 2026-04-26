# PR Code Review Agent

PR Code Review Agent — A LangGraph agent that automatically reviews GitHub Pull Request diffs for security issues and code quality problems, posts structured comments, and traces every run in LangSmith.

## Architecture

```
Developer opens PR
  → GitHub sends POST to API Gateway URL
    → AWS Lambda (FastAPI + Mangum) verifies webhook and queues review work
      → Lambda asynchronously invokes itself for the review job
      → LangGraph agent runs:
          1. Embeds diff, retrieves top-5 similar vulnerability patterns from Weaviate Cloud (RAG)
          2. Sends diff + patterns to Claude API, enforces Pydantic PRReview schema on output
      → Posts structured review comments to GitHub PR via GitHub API
      → Writes run record (prompt_version, latency_ms, cost_usd) to Supabase PostgreSQL
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
   BODY="$(cat sample_payloads/pr_opened.json)"
   SIG="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$GITHUB_WEBHOOK_SECRET" | awk '{print $2}')"

   curl -X POST http://localhost:8000/webhook \
     -H "X-GitHub-Event: pull_request" \
     -H "X-Hub-Signature-256: $SIG" \
     -H "Content-Type: application/json" \
     -d "$BODY"
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
create table if not exists public.reviews (
    id uuid primary key default gen_random_uuid(),
    pr_number int not null,
    repo text not null,
    prompt_version text not null,
    overall_risk text,
    comment_count int,
    latency_ms int,
    cost_usd float,
    status text not null default 'success',
    error_message text,
    langsmith_trace_id text,
    created_at timestamptz default now()
);

alter table public.reviews enable row level security;

grant usage on schema public to service_role;
grant select, insert, update on table public.reviews to service_role;
```

Use a Supabase secret/service-role key for `SUPABASE_SERVICE_KEY`; do not use the publishable/anon key.

## Deployment (AWS SAM)

```bash
# First time
sam build
sam deploy --guided

# Subsequent deploys
sam build && sam deploy
```

After deploy, copy the `WebhookUrl` output and configure it as the GitHub webhook URL for your repo (Settings → Webhooks → Add webhook).

## Working Demo Flow

The Phase 1 demo path is:

```
GitHub PR opened or synchronized
  → webhook reaches Lambda
  → Lambda validates the signature and queues review work
  → agent fetches the PR diff, retrieves patterns from Weaviate, and calls Claude
  → review is posted back to GitHub
  → run metadata is stored in Supabase reviews
  → LangSmith captures the agent/model trace
```

To verify a deployed run, check:

- GitHub PR review comments on the test PR
- Supabase `public.reviews` rows ordered by `created_at desc`
- LangSmith project `pr-review-agent`
- CloudWatch logs for the Lambda function

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
