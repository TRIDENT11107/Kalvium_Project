from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr, model_validator
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parents[2]
class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")
    database_url: str = "postgresql+psycopg://lesson:lesson@localhost:5432/lesson_studio"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = Field(min_length=32)
    jwt_expire_minutes: int = 720
    cors_origins: str = "http://localhost:5173"
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = "openai/gpt-oss-120b"
    groq_timeout: int = 120
    groq_max_retries: int = 2
    groq_max_completion_tokens: int = 2500
    groq_qc_max_completion_tokens: int = 1400
    tavily_api_key: str = ""
    google_books_api_key: str = ""
    youtube_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@example.com"
    frontend_url: str = "http://localhost:5173"
    @model_validator(mode="after")
    def reject_placeholder_secret(self):
        if "REPLACE_WITH" in self.jwt_secret or self.jwt_secret == "change-me-before-deploy":
            raise ValueError("Set JWT_SECRET to a unique random value before starting the API")
        return self
settings=Settings()
