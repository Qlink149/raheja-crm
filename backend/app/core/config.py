import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent.parent
load_dotenv(ROOT_DIR / '.env')

class Settings:
    PROJECT_NAME: str = "Rustomjee Sales Intelligence API"
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
