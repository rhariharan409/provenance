from pathlib import Path
from typing import List, Optional
from pydantic import model_validator
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

    # Section 2 settings
    GITHUB_API_TOKEN: Optional[str] = None
    GITHUB_APP_ID: Optional[str] = None
    GITHUB_APP_SLUG: Optional[str] = None
    GITHUB_APP_PRIVATE_KEY_PATH: str = "./secrets/github-app.pem"
    REPO_STORAGE_PATH: str = "./data/repos"
    MAX_REPO_SIZE_MB: int = 500
    MAX_COMMITS: int = 20000
    MAX_PULL_REQUESTS: int = 300
    CLONE_TIMEOUT_SECONDS: int = 600
    MAX_PROJECTS_PER_USER: int = 20

    # Section 3 settings
    SCORE_WEIGHT_SURVIVAL: float = 0.40
    SCORE_WEIGHT_EFFECTIVE_CHANGE: float = 0.25
    SCORE_WEIGHT_OWNERSHIP: float = 0.15
    SCORE_WEIGHT_COLLABORATION: float = 0.20
    MAX_BLAME_FILES: int = 1500
    MAX_FILE_SIZE_KB: int = 400
    ANALYSIS_TIMEOUT_SECONDS: int = 900
    BULK_COMMIT_LINE_CAP: int = 1500

    # Section 4 settings
    PASSPORT_SIGNING_SECRET: Optional[str] = None
    PUBLIC_BASE_URL: str = "http://localhost:3000"
    MAX_DISPUTE_TEXT: int = 1000
    MAX_OPEN_DISPUTES_PER_USER: int = 5

    @model_validator(mode="after")
    def validate_and_normalize_weights(self):
        w_surv = self.SCORE_WEIGHT_SURVIVAL
        w_eff = self.SCORE_WEIGHT_EFFECTIVE_CHANGE
        w_own = self.SCORE_WEIGHT_OWNERSHIP
        w_collab = self.SCORE_WEIGHT_COLLABORATION
        if any(w < 0 for w in [w_surv, w_eff, w_own, w_collab]):
            raise ValueError("Score weights must be non-negative")
        total = w_surv + w_eff + w_own + w_collab
        if total > 0:
            self.SCORE_WEIGHT_SURVIVAL = round(w_surv / total, 6)
            self.SCORE_WEIGHT_EFFECTIVE_CHANGE = round(w_eff / total, 6)
            self.SCORE_WEIGHT_OWNERSHIP = round(w_own / total, 6)
            self.SCORE_WEIGHT_COLLABORATION = round(w_collab / total, 6)
        return self

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() == "production"

    @property
    def admin_usernames(self) -> List[str]:
        if not self.ADMIN_GITHUB_USERNAMES:
            return []
        return [u.strip().lower() for u in self.ADMIN_GITHUB_USERNAMES.split(",") if u.strip()]


settings = Settings()
