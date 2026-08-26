import asyncio
import logging

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


async def telegram_api_call(settings: Settings, method: str, payload: dict) -> dict:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError:
        raise RuntimeError(f"Telegram {method} HTTP request failed") from None
    if not data.get("ok"):
        raise RuntimeError(data.get("description", f"Telegram {method} failed"))
    return data


async def send_telegram_message(settings: Settings, chat_id: str, text: str) -> bool:
    if not settings.telegram_bot_token:
        return False
    chunks = [text[index : index + 4000] for index in range(0, len(text), 4000)] or ["(빈 응답)"]
    for chunk in chunks:
        for attempt in range(3):
            try:
                await telegram_api_call(
                    settings,
                    "sendMessage",
                    {"chat_id": chat_id, "text": chunk},
                )
                break
            except Exception:
                if attempt == 2:
                    logger.exception("Telegram result notification failed after retries")
                    return False
                await asyncio.sleep(2**attempt)
    return True
