# Setup Guide

This guide walks you through running the PR Code Review Agent on your own GitHub repo from scratch.

## What You Need

Before starting, create free accounts on these services:

| Service | What For | Free Tier |
|---|---|---|
| [Anthropic](https://console.anthropic.com) | Claude API (the LLM) | Pay-per-use, ~$0.02–0.05 per review |
| [GitHub](https://github.com) | Webhook + PR access | Free |
| [Weaviate Cloud](https://console.weaviate.cloud) | Vector store for RAG | Free sandbox |
| [Supabase](https://supabase.com) | PostgreSQL run history | Free tier |
| [LangSmith](https://smith.langchain.com) | Tracing | Free tier |
| [AWS](https://aws.amazon.com) | Lambda hosting | Free tier covers typical usage |

---

## Step 1 — Clone and install

```bash
git clone https://github.com/DaniManas/pr-review-agent.git
cd pr-review-agent
python3.11 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
```

---

## Step 2 — Get your API keys

### Anthropic
1. Go to [console.anthropic.com](https://console.anthropic.com)
2. API Keys → Create Key
3. Copy `ANTHROPIC_API_KEY`

### GitHub
1. Go to GitHub → Settings → Developer Settings → Personal Access Tokens → Tokens (classic)
2. Generate new token with scopes: `repo`, `pull_requests` (write)
3. Copy `GITHUB_TOKEN`
4. Pick any random string for `GITHUB_WEBHOOK_SECRET` — you will use this again in Step 5

```bash
# Example — generate a random secret
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Weaviate Cloud
1. Go to [console.weaviate.cloud](https://console.weaviate.cloud)
2. Create cluster → Free sandbox
3. Once created, copy the **REST Endpoint** (looks like `https://xxx.c0.us-west3.gcp.weaviate.cloud`)
4. Go to cluster → API Keys → copy the key
5. These are `WEAVIATE_URL` and `WEAVIATE_API_KEY`

### Supabase
1. Go to [supabase.com](https://supabase.com) → New project
2. Settings → API → copy **Project URL** and **service_role** key (not anon key)
3. These are `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`
4. Go to SQL Editor and run this to create the reviews table:

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

### LangSmith
1. Go to [smith.langchain.com](https://smith.langchain.com)
2. Settings → API Keys → Create
3. Copy `LANGSMITH_API_KEY`
4. Create a project named `pr-review-agent` (or any name you like)

---

## Step 3 — Configure your .env

```bash
cp .env.example .env
```

Open `.env` and fill in all values:

```
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
GITHUB_WEBHOOK_SECRET=<your random secret from Step 2>
WEAVIATE_URL=https://xxx.c0.us-west3.gcp.weaviate.cloud
WEAVIATE_API_KEY=...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=pr-review-agent
PROMPT_VERSION=v2
```

Validate that nothing is missing:

```bash
bash scripts/validate_env.sh
```

---

## Step 4 — Seed Weaviate

This loads 25 vulnerability patterns into the vector store so the agent has RAG context:

```bash
python scripts/seed_weaviate.py
```

You should see:

```
Created collection: VulnerabilityPattern
Inserted 25 new patterns (0 already existed)
```

---

## Step 5 — Deploy to AWS Lambda

Install the AWS SAM CLI if you don't have it:
- [SAM install guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)

Also configure AWS credentials:

```bash
aws configure
```

Then deploy:

```bash
sam build
sam deploy --guided
```

When prompted, enter all parameter values from your `.env`. On first run, SAM will save these to `samconfig.toml` for future deploys.

After deploy completes, copy the `WebhookUrl` output — it looks like:

```
https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/Prod/webhook
```

---

## Step 6 — Configure GitHub webhook

1. Go to your GitHub repo → Settings → Webhooks → Add webhook
2. **Payload URL**: paste the `WebhookUrl` from Step 5
3. **Content type**: `application/json`
4. **Secret**: the same `GITHUB_WEBHOOK_SECRET` you set in `.env`
5. **Which events**: select **Pull requests** only
6. Click Add webhook

---

## Step 7 — Test it

Open a pull request on your repo. Within seconds the agent should:

1. Post a **PR Review Summary** comment with overall risk, issue count, cost, and latency
2. Post **inline comments** on specific lines with issue type, severity, and suggestions
3. Write a row to your Supabase `reviews` table
4. Create a trace in your LangSmith project

---

## Local Testing (no AWS needed)

Start the server locally:

```bash
uvicorn app.main:app --reload
```

Send a test payload:

```bash
curl -X POST http://localhost:8000/webhook \
  -H "X-GitHub-Event: pull_request" \
  -H "Content-Type: application/json" \
  -d @sample_payloads/pr_opened.json
```

> Note: local test requires real API keys. The sample payload points to a real PR, so the agent will attempt a real review.

Run the test suite (no real keys needed):

```bash
pytest tests/ -v
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| No review posted after PR opened | Webhook not configured or wrong secret | Check GitHub webhook delivery logs (Settings → Webhooks → Recent Deliveries) |
| `weaviate_error` in LangSmith | Weaviate cluster paused or wrong URL | Resume cluster at console.weaviate.cloud, re-run seed script |
| Supabase insert fails | Table not created or wrong key | Run the SQL from Step 2, confirm you used service_role key not anon key |
| Lambda timeout | Diff too large or Claude slow | Increase timeout in `template.yaml` (max 900s for Lambda) |
| `patterns: []` in trace | Weaviate credentials not updated in Lambda | Redeploy with `sam deploy` after updating `.env` |

---

## Updating the deployment

After any code change:

```bash
sam build
sam deploy
```

After changing only environment variables (no code change), you can update Lambda directly:

```bash
aws lambda update-function-configuration \
  --function-name pr-review-agent-PRReviewFunction \
  --environment "Variables={WEAVIATE_URL=...,WEAVIATE_API_KEY=...}"
```
