from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    CRAWL_TIMEOUT_SECONDS: int = 10
    DEFAULT_MAX_PAGES: int = 50
    GROQ_API_KEY: str = "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"
    REPORTS_DIR: str = "reports"
    CHROMA_DB_PATH: str = "chroma_db"


settings = Settings()
