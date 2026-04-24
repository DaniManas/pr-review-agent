import os

# Set all env vars before any app modules are imported.
# conftest.py is loaded by pytest before test modules, so this runs first.
os.environ["ANTHROPIC_API_KEY"] = "x"
os.environ["GITHUB_TOKEN"] = "x"
os.environ["GITHUB_WEBHOOK_SECRET"] = "test-secret"
os.environ["WEAVIATE_URL"] = "x"
os.environ["WEAVIATE_API_KEY"] = "x"
os.environ["SUPABASE_URL"] = "x"
os.environ["SUPABASE_SERVICE_KEY"] = "x"
os.environ["LANGSMITH_API_KEY"] = "x"
os.environ["LANGSMITH_PROJECT"] = "x"
os.environ["PROMPT_VERSION"] = "v1"
