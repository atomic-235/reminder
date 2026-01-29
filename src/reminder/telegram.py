"""Telegram bot integration for sending reminders."""

from typing import Any

import httpx

from .logging import logger


class TelegramBot:
    """Simple Telegram bot client for sending messages."""

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        logger.debug(f"TelegramBot initialized with chat_id: {chat_id}")

    async def send_message(self, text: str) -> dict[str, Any]:
        """Send a message to the configured chat."""
        logger.debug(f"Sending message: {text[:50]}...")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                    },
                )
                logger.debug(f"Response status: {response.status_code}")
                logger.debug(f"Response body: {response.text}")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise

    async def test_connection(self) -> bool:
        """Test if the bot credentials are valid."""
        logger.debug("Testing Telegram connection")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/getMe")
                logger.debug(f"test_connection status: {response.status_code}")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"test_connection failed: {e}")
            return False
