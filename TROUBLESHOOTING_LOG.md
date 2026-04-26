# PR Review Agent Troubleshooting Log

## 2026-04-26

### What Was Fixed

- Removed real-looking values from `.env.example`; real secrets belong only in local `.env` and deployed Lambda environment variables.
- Updated deployed Lambda configuration during debugging:
  - Fixed malformed `ANTHROPIC_API_KEY`.
  - Fixed truncated `WEAVIATE_URL`.
  - Replaced old Supabase key with the working `sb_secret_...` secret key.
  - Increased Lambda timeout to 90 seconds.
- Updated Supabase permissions:
  - Enabled RLS on `public.reviews`.
  - Granted `service_role` usage on `public`.
  - Granted `service_role` `select`, `insert`, and `update` on `public.reviews`.

### Verified Working Path

- GitHub webhook reaches Lambda.
- Anthropic key works.
- Weaviate URL/API key works.
- GitHub token can post PR reviews.
- Supabase accepts successful `reviews` rows.
- PR #2 received agent review comments.
- Supabase row for PR #2 was inserted with `status = success`.

### Remaining Hardening

- GitHub can time out waiting for synchronous webhook processing. The durable fix is implemented in code by making the public webhook return quickly and invoking the review job asynchronously inside Lambda.
- Keep `template.yaml` as the source of truth for timeout and Lambda permissions.
- Do not commit `.env`, `.aws-sam`, `samconfig.toml`, Python caches, or local build artifacts.

## 2026-04-26 Hardening Update

- Removed tracked generated/local files:
  - Python `__pycache__` / `.pyc` files
  - `buggy_code.py`
  - `samconfig.toml`
- Replaced the Supabase Python SDK writer with a direct Supabase REST insert using `httpx`.
  - This removed the `supabase -> storage3 -> pyiceberg -> pyroaring` dependency chain that blocked `sam build`.
- Updated `template.yaml`:
  - Lambda timeout is now `90` seconds.
  - Lambda architecture is `x86_64`.
  - Lambda role can invoke the deployed function asynchronously.
- Updated `/webhook` flow:
  - GitHub webhook request validates and returns quickly.
  - Deployed Lambda invokes itself asynchronously for the review job.
  - Local/dev mode still runs inline when `AWS_LAMBDA_FUNCTION_NAME` is absent.
- Verification after deploy:
  - `pytest`: 13 tests passed.
  - `sam build`: succeeded.
  - `sam deploy`: succeeded.
  - GitHub webhook redelivery returned `200 OK`.
  - Async review job inserted a Supabase success row at `2026-04-26T21:20:29Z`.

### Current Status

Phase 1 demo path is hardened and working:

1. GitHub webhook returns `200 OK`.
2. Lambda queues review work asynchronously.
3. Agent posts a GitHub PR review.
4. Supabase stores a successful run row.
5. LangSmith traces the agent/model calls.
