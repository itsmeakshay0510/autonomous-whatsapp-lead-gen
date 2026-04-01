"""
PHN Technology - Set Reminder Tool
Schedules follow-up reminders for students.
"""

import logging
from datetime import datetime, timedelta
from database.db import Database

logger = logging.getLogger(__name__)


async def set_reminder(
    phone: str,
    message: str,
    hours_from_now: int = 24
) -> str:
    """
    Schedule a reminder for a student.
    Returns confirmation message.
    """
    remind_at = datetime.utcnow() + timedelta(hours=hours_from_now)
    remind_at_str = remind_at.isoformat()

    db = await Database.get_instance()
    reminder_id = await db.add_reminder(phone, message, remind_at_str)

    logger.info(f"Reminder #{reminder_id} set for {phone} at {remind_at_str}: {message}")

    return (
        f"Reminder scheduled! I'll follow up in {hours_from_now} hours "
        f"with: '{message}'"
    )


async def check_and_send_reminders(send_func):
    """
    Check for due reminders and send them.
    Called periodically by the scheduler.
    """
    db = await Database.get_instance()
    due_reminders = await db.get_due_reminders()

    for reminder in due_reminders:
        try:
            reminder_msg = (
                f"⏰ *Reminder from PHN Technology*\n\n"
                f"{reminder['message']}\n\n"
                f"Is there anything I can help you with? 😊"
            )
            await send_func(reminder["phone"], reminder_msg)
            await db.mark_reminder_sent(reminder["id"])
            logger.info(f"Sent reminder #{reminder['id']} to {reminder['phone']}")
        except Exception as e:
            logger.error(f"Failed to send reminder #{reminder['id']}: {e}")
