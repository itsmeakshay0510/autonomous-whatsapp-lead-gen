"""
PHN Technology - Conversation Memory Store
Manages per-user conversation history with automatic truncation.
"""

import logging
from typing import Optional
from database.db import Database
from config import get_settings

logger = logging.getLogger(__name__)


class ConversationStore:
    """Manages conversation history per phone number."""

    def __init__(self):
        self.settings = get_settings()

    async def add_turn(self, phone: str, role: str, content: str):
        """Add a message to conversation history."""
        db = await Database.get_instance()
        await db.add_message(phone, role, content)

    async def get_history(self, phone: str) -> list[dict]:
        """Get conversation history formatted for LLM context."""
        db = await Database.get_instance()
        messages = await db.get_conversation(
            phone, limit=self.settings.max_conversation_turns
        )
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
        ]

    async def get_history_text(self, phone: str) -> str:
        """Get conversation history as formatted text string."""
        history = await self.get_history(phone)
        if not history:
            return ""

        lines = []
        for msg in history:
            role_label = "Student" if msg["role"] == "user" else "PHN Assistant"
            lines.append(f"{role_label}: {msg['content']}")

        return "\n".join(lines)

    async def clear(self, phone: str):
        """Clear conversation history for a phone number."""
        db = await Database.get_instance()
        await db.clear_conversation(phone)
        logger.info(f"Cleared conversation for {phone}")

    async def get_student_context(self, phone: str) -> Optional[dict]:
        """Get any saved student info for additional context."""
        db = await Database.get_instance()
        return await db.get_student(phone)
