from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from app.core.config import Settings
from app.services.telegram import send_telegram_message, telegram_api_call


@pytest.mark.asyncio
async def test_telegram_api_call_posts_to_bot_endpoint():
    settings = Settings(ai_provider="mock", telegram_bot_token="bot-token")
    response = Mock()
    response.json.return_value = {"ok": True, "result": {"username": "company_bot"}}
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    client.post.return_value = response

    with patch("app.services.telegram.httpx.AsyncClient", return_value=client):
        result = await telegram_api_call(settings, "getMe", {})

    response.raise_for_status.assert_called_once()
    client.post.assert_awaited_once_with(
        "https://api.telegram.org/botbot-token/getMe",
        json={},
    )
    assert result["result"]["username"] == "company_bot"


@pytest.mark.asyncio
async def test_long_telegram_result_is_split_into_safe_chunks():
    settings = Settings(ai_provider="mock", telegram_bot_token="bot-token")

    with patch(
        "app.services.telegram.telegram_api_call", new=AsyncMock(return_value={"ok": True})
    ) as api_call:
        delivered = await send_telegram_message(settings, "123", "x" * 8001)

    assert delivered is True
    assert api_call.await_count == 3
    assert [len(call.args[2]["text"]) for call in api_call.await_args_list] == [4000, 4000, 1]


@pytest.mark.asyncio
async def test_telegram_delivery_error_is_reported_without_failing_task_flow():
    settings = Settings(ai_provider="mock", telegram_bot_token="bot-token")

    with (
        patch(
            "app.services.telegram.telegram_api_call",
            new=AsyncMock(side_effect=ConnectionError),
        ) as api_call,
        patch("app.services.telegram.asyncio.sleep", new=AsyncMock()) as sleep,
    ):
        delivered = await send_telegram_message(settings, "123", "result")

    assert delivered is False
    assert api_call.await_count == 3
    assert sleep.await_count == 2


@pytest.mark.asyncio
async def test_transient_telegram_error_retries_only_failed_chunk():
    settings = Settings(ai_provider="mock", telegram_bot_token="bot-token")
    api_call = AsyncMock(side_effect=[ConnectionError, {"ok": True}])

    with (
        patch("app.services.telegram.telegram_api_call", new=api_call),
        patch("app.services.telegram.asyncio.sleep", new=AsyncMock()) as sleep,
    ):
        delivered = await send_telegram_message(settings, "123", "result")

    assert delivered is True
    assert api_call.await_count == 2
    sleep.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_telegram_http_error_does_not_expose_bot_token():
    token = "super-secret-bot-token"
    settings = Settings(ai_provider="mock", telegram_bot_token=token)
    request = httpx.Request("POST", f"https://api.telegram.org/bot{token}/sendMessage")
    response = httpx.Response(401, request=request)
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    client.post.side_effect = httpx.HTTPStatusError(
        "unauthorized",
        request=request,
        response=response,
    )

    with patch("app.services.telegram.httpx.AsyncClient", return_value=client):
        with pytest.raises(RuntimeError) as caught:
            await telegram_api_call(settings, "sendMessage", {"chat_id": "123", "text": "x"})

    assert token not in str(caught.value)
    assert str(caught.value) == "Telegram sendMessage HTTP request failed"
