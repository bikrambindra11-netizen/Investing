"""Settings loaded from the repo-root .env file. Keys are never hardcoded."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    upstox_api_key: str = ""
    upstox_api_secret: str = ""
    upstox_redirect_uri: str = "http://127.0.0.1:8000/auth/upstox/callback"
    upstox_access_token: str = ""
    fred_api_key: str = ""

    database_url: str = f"sqlite:///{ROOT / 'backend' / 'data' / 'portal.db'}"
    frontend_origin: str = "http://localhost:3000"

    def key_status(self) -> dict[str, bool]:
        """Which keys are configured (values are never exposed)."""
        return {
            "upstox_api_key": bool(self.upstox_api_key),
            "upstox_access_token": bool(self.upstox_access_token),
            "fred_api_key": bool(self.fred_api_key),
        }


settings = Settings()
