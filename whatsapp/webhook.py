"""
PHN Technology - WhatsApp Webhook Handler
Handles incoming webhooks from Meta WhatsApp Business API.
"""

import hashlib
import hmac
import logging
from fastapi import APIRouter, Request, Response, BackgroundTasks, HTTPException
from config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["whatsapp"])

# This will be set by main.py during startup
_message_handler = None


def set_message_handler(handler):
    """Set the async message handler function."""
    global _message_handler
    _message_handler = handler


@router.get("")
async def verify_webhook(request: Request):
    """
    WhatsApp webhook verification endpoint.
    Meta sends a GET request with hub.mode, hub.verify_token, and hub.challenge.
    """
    settings = get_settings()
    params = request.query_params

    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        logger.info("Webhook verified successfully!")
        return Response(content=challenge, media_type="text/plain")

    logger.warning(f"Webhook verification failed: mode={mode}, token={token}")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handle incoming WhatsApp messages.
    Responds with 200 immediately and processes in background.
    """
    try:
        body = await request.json()
    except Exception:
        logger.error("Failed to parse webhook body")
        return {"status": "error"}

    # Validate this is a WhatsApp message notification
    entry = body.get("entry", [])
    if not entry:
        return {"status": "ok"}

    for e in entry:
        changes = e.get("changes", [])
        for change in changes:
            value = change.get("value", {})

            # Skip status updates (delivered, read, etc.)
            if "statuses" in value:
                continue

            messages = value.get("messages", [])
            metadata = value.get("metadata", {})

            for msg in messages:
                # Extract message info
                sender_phone = msg.get("from", "")
                msg_type = msg.get("type", "")
                msg_id = msg.get("id", "")

                # Extract text content
                text = ""
                if msg_type == "text":
                    text = msg.get("text", {}).get("body", "")
                elif msg_type == "interactive":
                    # Button or list reply
                    interactive = msg.get("interactive", {})
                    if "button_reply" in interactive:
                        text = interactive["button_reply"].get("title", "")
                    elif "list_reply" in interactive:
                        text = interactive["list_reply"].get("title", "")
                elif msg_type == "button":
                    text = msg.get("button", {}).get("text", "")
                else:
                    # For now, we only handle text messages
                    text = f"[{msg_type} message received - I can only process text messages at the moment]"

                if text and sender_phone and _message_handler:
                    logger.info(f"Message from {sender_phone}: {text[:100]}")
                    # Process in background to respond to webhook immediately
                    background_tasks.add_task(
                        _message_handler, sender_phone, text, msg_id
                    )

    # Always respond 200 quickly to avoid webhook retries
    return {"status": "ok"}


def verify_signature(request_body: bytes, signature: str, app_secret: str) -> bool:
    """
    Verify the X-Hub-Signature-256 header.
    Use this in production for security.
    """
    if not signature or not app_secret:
        return True  # Skip validation if not configured

    expected = hmac.new(
        app_secret.encode(), request_body, hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(f"sha256={expected}", signature)
