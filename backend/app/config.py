"""Settings loaded from the repo-root .env file. Keys are never hardcoded."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "backend" / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    upstox_api_key: str = ""
    upstox_api_secret: str = ""
    upstox_redirect_uri: str = "http://127.0.0.1:8000/auth/upstox/callback"
    # Optional: paste a token here instead of using the "Login with Upstox" button.
    upstox_access_token: str = ""
    fred_api_key: str = ""

    database_url: str = f"sqlite:///{DATA_DIR / 'portal.db'}"
    frontend_origin: str = "http://localhost:3000"

    # Background jobs (data downloads, live feed). Tests turn this off.
    run_jobs: bool = True
    # Max instruments subscribed on the live feed (Upstox per-connection limit for LTPC mode).
    live_max_instruments: int = 5000

    def key_status(self) -> dict[str, bool]:
        """Which keys are configured (values are never exposed)."""
        return {
            "upstox_api_key": bool(self.upstox_api_key),
            "upstox_api_secret": bool(self.upstox_api_secret),
            "fred_api_key": bool(self.fred_api_key),
        }


settings = Settings()
