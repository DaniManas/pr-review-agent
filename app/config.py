from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    anthropic_api_key: str
    github_token: str
    github_webhook_secret: str
    weaviate_url: str
    weaviate_api_key: str
    supabase_url: str
    supabase_service_key: str
    langsmith_api_key: str
    langsmith_project: str
    prompt_version: str

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
