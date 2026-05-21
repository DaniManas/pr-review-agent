#!/usr/bin/env bash
# Validates all required .env vars are set before deploy or seed

ENV_FILE="${1:-.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found. Copy .env.example to .env and fill in values."
  exit 1
fi

source "$ENV_FILE"

REQUIRED=(
  ANTHROPIC_API_KEY
  GITHUB_TOKEN
  GITHUB_WEBHOOK_SECRET
  WEAVIATE_URL
  WEAVIATE_API_KEY
  SUPABASE_URL
  SUPABASE_SERVICE_KEY
  LANGSMITH_API_KEY
  LANGSMITH_PROJECT
  PROMPT_VERSION
)

MISSING=()

for var in "${REQUIRED[@]}"; do
  if [ -z "${!var}" ]; then
    MISSING+=("$var")
  fi
done

if [ ${#MISSING[@]} -eq 0 ]; then
  echo "All required env vars are set."
  exit 0
else
  echo "Missing required env vars:"
  for var in "${MISSING[@]}"; do
    echo "  - $var"
  done
  echo ""
  echo "Fill these in $ENV_FILE and re-run."
  exit 1
fi
