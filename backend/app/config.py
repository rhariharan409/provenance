from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

SESSION_COOKIE_NAME = "provenance_session"
OAUTH_STATE_COOKIE_NAME = "provenance_oauth_state"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    ENV: str = "development"
    DATABASE_URL: str = "postgresql+psycopg://provenance:provenance@localhost:5432/provenance"
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: str = "http://localhost:3000/api/auth/github/callback"
    SESSION_SECRET: str = "change-me-session-secret-at-least-32-chars-key"
    FRONTEND_URL: str = "http://localhost:3000"
    ADMIN_GITHUB_USERNAMES: str = ""

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() == "production"

    @property
    def admin_usernames(self) -> List[str]:
        if not self.ADMIN_GITHUB_USERNAMES:
            return []
        return [u.strip().lower() for u in self.ADMIN_GITHUB_USERNAMES.split(",") if u.strip()]


settings = Settings()
