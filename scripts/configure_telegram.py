import asyncio

from app.core.config import get_settings
from app.services.telegram import telegram_api_call


async def main() -> None:
    settings = get_settings()
    if not settings.telegram_enabled:
        raise SystemExit("TELEGRAM_ENABLED=true is required")
    if not settings.telegram_webhook_secret:
        raise SystemExit("TELEGRAM_WEBHOOK_SECRET is required")
    webhook_url = f"{settings.public_base_url.rstrip('/')}/integrations/telegram/webhook"
    identity = await telegram_api_call(settings, "getMe", {})
    result = await telegram_api_call(
        settings,
        "setWebhook",
        {
            "url": webhook_url,
            "secret_token": settings.telegram_webhook_secret,
            "allowed_updates": ["message"],
            "drop_pending_updates": False,
        },
    )
    status = await telegram_api_call(settings, "getWebhookInfo", {})
    print(f"Bot: @{identity['result'].get('username')}")
    print(f"Webhook configured: {result['result']}")
    print(f"Webhook URL: {status['result'].get('url')}")
    if status["result"].get("last_error_message"):
        print(f"Last Telegram error: {status['result']['last_error_message']}")


if __name__ == "__main__":
    asyncio.run(main())
