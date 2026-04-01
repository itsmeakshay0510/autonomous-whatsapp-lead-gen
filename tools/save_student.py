"""
PHN Technology - Save Student Tool
Captures and persists student registration interest.
"""

import logging
from database.db import Database

logger = logging.getLogger(__name__)


async def save_student_info(
    phone: str,
    name: str = None,
    email: str = None,
    course: str = None,
    notes: str = None
) -> str:
    """
    Save student information to the database.
    Returns confirmation message.
    """
    db = await Database.get_instance()
    await db.save_student(
        phone=phone,
        name=name,
        email=email,
        course=course,
        notes=notes
    )

    details = []
    if name:
        details.append(f"Name: {name}")
    if email:
        details.append(f"Email: {email}")
    if course:
        details.append(f"Interested Course: {course}")

    detail_str = ", ".join(details) if details else "Contact info"
    logger.info(f"Saved student info for {phone}: {detail_str}")

    return f"Student information saved successfully: {detail_str}. A counselor will follow up within 24 hours."
