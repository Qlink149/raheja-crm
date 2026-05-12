"""Upload raw CSV bytes to Cloudinary (resource_type=raw)."""
import io
import re
import logging
from typing import Any, Dict, Optional

from starlette.concurrency import run_in_threadpool

from app.core.config import settings

logger = logging.getLogger(__name__)


def _batch_slug(name: str, max_len: int = 64) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "batch").strip())
    s = s.strip("_") or "batch"
    return s[:max_len]


async def upload_lead_csv_raw(
    content: bytes, *, batch_label: str, upload_id: str
) -> Dict[str, Any]:
    """
    Returns Cloudinary upload result (includes secure_url, public_id, etc.).
    Raises on missing config or upload failure.
    """
    if not (settings.CLOUDINARY_URL or "").strip():
        raise RuntimeError("CLOUDINARY_URL is not configured")

    import os
    import cloudinary
    import cloudinary.uploader

    if not os.environ.get("CLOUDINARY_URL") and settings.CLOUDINARY_URL:
        os.environ["CLOUDINARY_URL"] = settings.CLOUDINARY_URL
    cloudinary.config(secure=True)

    public_id = f"leads/{_batch_slug(batch_label)}_{upload_id}.csv"

    def _upload() -> Dict[str, Any]:
        return cloudinary.uploader.upload(
            io.BytesIO(content),
            resource_type="raw",
            public_id=public_id,
            invalidate=True,
        )

    return await run_in_threadpool(_upload)
