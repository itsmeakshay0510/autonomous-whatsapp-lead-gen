"""
PHN Technology - WhatsApp Message Sender
Sends replies via Meta Graph API with retry logic.
"""

import logging
import asyncio
from typing import Optional
import httpx
from config import get_settings

logger = logging.getLogger(__name__)


class WhatsAppSender:
    """Sends messages to users via WhatsApp Business API."""

    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "Authorization": f"Bearer {self.settings.whatsapp_access_token}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def send_text(self, to_phone: str, text: str, max_retries: int = 3) -> bool:
        """
        Send a text message to a WhatsApp number.

        Args:
            to_phone: Recipient phone number (with country code, no +)
            text: Message text
            max_retries: Number of retry attempts

        Returns:
            True if sent successfully
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {"body": text},
        }

        return await self._send_with_retry(payload, max_retries)

    async def send_reply(self, to_phone: str, text: str, message_id: str = None, max_retries: int = 3) -> bool:
        """
        Send a reply message (quotes the original message).
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {"body": text},
        }

        # Add context for reply threading
        if message_id:
            payload["context"] = {"message_id": message_id}

        return await self._send_with_retry(payload, max_retries)

    async def send_buttons(
        self,
        to_phone: str,
        body_text: str,
        buttons: list[dict],
        header: str = None,
        footer: str = None,
    ) -> bool:
        """
        Send an interactive button message (max 3 buttons).

        Args:
            buttons: List of {"id": "btn1", "title": "Button Label"}
        """
        interactive = {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
                    for b in buttons[:3]
                ]
            },
        }

        if header:
            interactive["header"] = {"type": "text", "text": header}
        if footer:
            interactive["footer"] = {"text": footer}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "interactive",
            "interactive": interactive,
        }

        return await self._send_with_retry(payload)

    async def send_cta_url(
        self,
        to_phone: str,
        body_text: str,
        button_text: str,
        url: str,
        header: str = None,
        footer: str = None,
    ) -> bool:
        """Send an interactive CTA URL button."""
        interactive = {
            "type": "cta_url",
            "body": {"text": body_text},
            "action": {
                "name": "cta_url",
                "parameters": {
                    "display_text": button_text[:20],
                    "url": url
                }
            }
        }
        if header:
            interactive["header"] = {"type": "text", "text": header[:60]}
        if footer:
            interactive["footer"] = {"text": footer[:60]}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "interactive",
            "interactive": interactive,
        }
        return await self._send_with_retry(payload)

    async def mark_as_read(self, message_id: str):
        """Mark a message as read (blue ticks)."""
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        client = await self._get_client()
        try:
            await client.post(self.settings.whatsapp_api_url, json=payload)
        except Exception as e:
            logger.debug(f"Failed to mark as read: {e}")

    async def _send_with_retry(self, payload: dict, max_retries: int = 3) -> bool:
        """Send a message with exponential backoff retry."""
        client = await self._get_client()

        for attempt in range(max_retries):
            try:
                response = await client.post(
                    self.settings.whatsapp_api_url, json=payload
                )

                if response.status_code == 200:
                    data = response.json()
                    msg_id = data.get("messages", [{}])[0].get("id", "unknown")
                    logger.info(
                        f"Message sent to {payload['to']}: {msg_id}"
                    )
                    return True

                elif response.status_code == 429:
                    # Rate limited — wait and retry
                    wait = 2 ** attempt
                    logger.warning(f"Rate limited, retrying in {wait}s...")
                    await asyncio.sleep(wait)

                else:
                    error_data = response.json()
                    logger.error(
                        f"WhatsApp API error {response.status_code}: {error_data}"
                    )
                    # Don't retry client errors (except 429)
                    if 400 <= response.status_code < 500:
                        return False

            except httpx.TimeoutException:
                logger.warning(f"Timeout sending message (attempt {attempt + 1})")
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        logger.error(f"Failed to send message after {max_retries} attempts")
        return False

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
