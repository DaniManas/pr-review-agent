import subprocess
import sys
from pathlib import Path


def parse_env(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def main() -> int:
    env = parse_env(".env")
    param_map = {
        "AnthropicApiKey": "ANTHROPIC_API_KEY",
        "GithubToken": "GITHUB_TOKEN",
        "GithubWebhookSecret": "GITHUB_WEBHOOK_SECRET",
        "WeaviateUrl": "WEAVIATE_URL",
        "WeaviateApiKey": "WEAVIATE_API_KEY",
        "SupabaseUrl": "SUPABASE_URL",
        "SupabaseServiceKey": "SUPABASE_SERVICE_KEY",
        "LangsmithApiKey": "LANGSMITH_API_KEY",
        "LangsmithProject": "LANGSMITH_PROJECT",
        "PromptVersion": "PROMPT_VERSION",
        "AnthropicInputCostPer1MTokens": "ANTHROPIC_INPUT_COST_PER_1M_TOKENS",
        "AnthropicOutputCostPer1MTokens": "ANTHROPIC_OUTPUT_COST_PER_1M_TOKENS",
    }
    defaults = {
        "LangsmithProject": "pr-review-agent",
        "PromptVersion": "v1",
        "AnthropicInputCostPer1MTokens": "3.00",
        "AnthropicOutputCostPer1MTokens": "15.00",
    }

    missing: list[str] = []
    overrides: list[str] = []
    for param, env_key in param_map.items():
        value = env.get(env_key) or defaults.get(param)
        if not value:
            missing.append(env_key)
            continue
        overrides.append(f"{param}={value}")

    if missing:
        print("Missing required .env values: " + ", ".join(missing), file=sys.stderr)
        return 2

    cmd = [
        "sam",
        "deploy",
        "--template-file",
        ".aws-sam/build/template.yaml",
        "--stack-name",
        "pr-review-agent",
        "--region",
        "us-east-1",
        "--capabilities",
        "CAPABILITY_IAM",
        "--resolve-s3",
        "--no-confirm-changeset",
        "--no-fail-on-empty-changeset",
        "--parameter-overrides",
        *overrides,
    ]
    print("Deploying pr-review-agent with parameters loaded from .env.")
    print("Secret values are passed directly to SAM and are not printed by this script.")
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
