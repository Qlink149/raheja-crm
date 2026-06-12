from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from openai import APIStatusError, AsyncOpenAI, RateLimitError

from ..core.config import settings

logger = logging.getLogger(__name__)

_groq_clients: Dict[int, AsyncOpenAI] = {}
_openai_client: Optional[AsyncOpenAI] = None
_groq_key_index: int = 0
_groq_index_lock = asyncio.Lock()

_MISSING_LLM_MSG = (
    "AI insights require an LLM API key. "
    "Configure GROQ_API_KEY_1 (or OPENAI_API_KEY) in the backend .env file."
)


def missing_llm_message() -> str:
    return _MISSING_LLM_MSG


def _get_groq_client(key_index: int, api_key: str) -> AsyncOpenAI:
    if key_index not in _groq_clients:
        _groq_clients[key_index] = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.GROQ_BASE_URL,
        )
    return _groq_clients[key_index]


def _get_openai_client() -> Optional[AsyncOpenAI]:
    global _openai_client
    if _openai_client is None:
        if not settings.OPENAI_API_KEY:
            return None
        _openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def _is_rate_limit_error(exc: Exception) -> bool:
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIStatusError) and exc.status_code == 429:
        return True
    return False


async def chat_completion(
    *,
    messages: List[Dict[str, Any]],
    temperature: float,
    max_tokens: int,
    response_format: Optional[Dict[str, str]] = None,
) -> Any:
    """Groq primary (multi-key rotation on rate limit) with OpenAI fallback."""
    global _groq_key_index
    groq_keys = settings.groq_api_keys
    create_kwargs: Dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        create_kwargs["response_format"] = response_format

    last_rate_limit: Optional[Exception] = None
    groq_non_rate_error: Optional[Exception] = None

    if groq_keys:
        async with _groq_index_lock:
            start_index = _groq_key_index

        for offset in range(len(groq_keys)):
            idx = (start_index + offset) % len(groq_keys)
            api_key = groq_keys[idx]
            client = _get_groq_client(idx, api_key)
            try:
                resp = await client.chat.completions.create(
                    model=settings.GROQ_MODEL,
                    **create_kwargs,
                )
                async with _groq_index_lock:
                    _groq_key_index = idx
                logger.info(
                    "LLM chat completion via Groq (key slot %d, model=%s)",
                    idx + 1,
                    settings.GROQ_MODEL,
                )
                return resp
            except Exception as e:
                if _is_rate_limit_error(e):
                    logger.warning(
                        "Groq key slot %d rate limited, rotating to next key: %s",
                        idx + 1,
                        e,
                    )
                    last_rate_limit = e
                    continue
                logger.warning(
                    "Groq key slot %d failed (non-rate-limit), will try OpenAI fallback: %s",
                    idx + 1,
                    e,
                )
                groq_non_rate_error = e
                break

    openai_client = _get_openai_client()
    if openai_client:
        try:
            resp = await openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                **create_kwargs,
            )
            logger.info(
                "LLM chat completion via OpenAI fallback (model=%s)",
                settings.OPENAI_MODEL,
            )
            return resp
        except Exception as e:
            if groq_non_rate_error is not None:
                raise groq_non_rate_error from e
            if last_rate_limit is not None:
                raise last_rate_limit from e
            raise

    if groq_non_rate_error is not None:
        raise groq_non_rate_error
    if last_rate_limit is not None:
        raise last_rate_limit
    raise RuntimeError(_MISSING_LLM_MSG)
