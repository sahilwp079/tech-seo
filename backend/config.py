from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    CRAWL_TIMEOUT_SECONDS: int = 10
    DEFAULT_MAX_PAGES: int = 50
    GROQ_API_KEY: str = ""
    REPORTS_DIR: str = "reports"
    CHROMA_DB_PATH: str = "chroma_db"


settings = Settings()
