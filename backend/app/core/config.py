import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent.parent
load_dotenv(ROOT_DIR / '.env')

class Settings:
    PROJECT_NAME: str = "Rustomjee Sales Intelligence API"
    SECRET_KEY: str = os.environ.get(
        "SECRET_KEY", "rustomjee-secret-key-change-in-production"
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(
        os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7")
    )
    MONGO_URL: str = os.environ.get('MONGO_URL', '')
    DB_NAME: str = os.environ.get('DB_NAME', 'rustomjee_db')
    OPENAI_API_KEY: str = os.environ.get('OPENAI_API_KEY') or os.environ.get('EMERGENT_LLM_KEY', '')
    FUTWORK_WEBHOOK_SECRET: str = os.environ.get("FUTWORK_WEBHOOK_SECRET", "").strip()
    FUTWORK_API_KEY: str = os.environ.get("FUTWORK_API_KEY", "").strip()
    FUTWORK_AGENT_ID: str = os.environ.get("FUTWORK_AGENT_ID", "").strip()
    FUTWORK_CAMPAIGN_ID: str = os.environ.get("FUTWORK_CAMPAIGN_ID", "").strip()
    # Optional caps for Campaign Information card (read-only in API)
    FUTWORK_MAX_ATTEMPTS: str = os.environ.get("FUTWORK_MAX_ATTEMPTS", "").strip()
    FUTWORK_CALL_RATE_LIMIT: str = os.environ.get("FUTWORK_CALL_RATE_LIMIT", "").strip()

    # CSV upload guardrails
    LEAD_UPLOAD_MAX_BYTES: int = int(
        os.environ.get("LEAD_UPLOAD_MAX_BYTES", str(10 * 1024 * 1024))  # 10 MiB
    )

    # Cloudinary for CSV storage
    CLOUDINARY_URL: str = os.environ.get("CLOUDINARY_URL", "").strip()

    # WhatsApp (Gupshup) — optional; reminders no-op when unset
    GUPSHUP_TOKEN: str = os.environ.get("GUPSHUP_TOKEN", "").strip()
    GUPSHUP_API_KEY: str = os.environ.get("GUPSHUP_API_KEY", "").strip()
    GUPSHUP_APP_ID: str = os.environ.get("GUPSHUP_APP_ID", "").strip()
    GUPSHUP_SOURCE_PHONE: str = os.environ.get("GUPSHUP_SOURCE_PHONE", "").strip()
    GUPSHUP_BASE_URL: str = "https://api.gupshup.io"

    ROOT_DIR: Path = ROOT_DIR

    @staticmethod
    def _optional_int(raw: str):
        if not raw:
            return None
        try:
            return int(raw.strip())
        except ValueError:
            return None

    @property
    def futwork_max_attempts(self):
        return Settings._optional_int(self.FUTWORK_MAX_ATTEMPTS)

    @property
    def futwork_call_rate_limit(self):
        return Settings._optional_int(self.FUTWORK_CALL_RATE_LIMIT)

settings = Settings()
