"""
PHN Technology - Database Manager
Handles all SQLite operations: students, conversations, cache, reminders.
"""

import aiosqlite
import os
import asyncio
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "phn_agent.db")


class Database:
    """Async SQLite database manager."""

    _instance: Optional["Database"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self.db_path = DB_PATH
        self._db: Optional[aiosqlite.Connection] = None

    @classmethod
    async def get_instance(cls) -> "Database":
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = Database()
                    await cls._instance._connect()
                    await cls._instance._create_tables()
        return cls._instance

    async def _connect(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        logger.info(f"Database connected at {self.db_path}")

    async def _create_tables(self):
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                name TEXT,
                email TEXT,
                interested_course TEXT,
                status TEXT DEFAULT 'interested',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS response_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_hash TEXT UNIQUE,
                query_text TEXT NOT NULL,
                response_text TEXT NOT NULL,
                embedding BLOB,
                hit_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                message TEXT NOT NULL,
                remind_at TIMESTAMP NOT NULL,
                sent INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_conversations_phone ON conversations(phone);
            CREATE INDEX IF NOT EXISTS idx_students_phone ON students(phone);
            CREATE INDEX IF NOT EXISTS idx_cache_hash ON response_cache(query_hash);
            CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(remind_at, sent);
        """)
        await self._db.commit()
        logger.info("Database tables initialized")

    # ---- Student Operations ----

    async def save_student(self, phone: str, name: str = None, email: str = None,
                           course: str = None, notes: str = None) -> int:
        cursor = await self._db.execute(
            """INSERT INTO students (phone, name, email, interested_course, notes)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT DO NOTHING""",
            (phone, name, email, course, notes)
        )
        # If insert was skipped due to conflict, update instead
        if cursor.rowcount == 0:
            await self._db.execute(
                """UPDATE students SET
                   name = COALESCE(?, name),
                   email = COALESCE(?, email),
                   interested_course = COALESCE(?, interested_course),
                   notes = COALESCE(?, notes),
                   updated_at = CURRENT_TIMESTAMP
                   WHERE phone = ?""",
                (name, email, course, notes, phone)
            )
        await self._db.commit()
        return cursor.lastrowid

    async def get_student(self, phone: str) -> Optional[dict]:
        cursor = await self._db.execute(
            "SELECT * FROM students WHERE phone = ? ORDER BY updated_at DESC LIMIT 1",
            (phone,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None

    # ---- Conversation Operations ----

    async def add_message(self, phone: str, role: str, content: str):
        await self._db.execute(
            "INSERT INTO conversations (phone, role, content) VALUES (?, ?, ?)",
            (phone, role, content)
        )
        await self._db.commit()

    async def get_conversation(self, phone: str, limit: int = 20) -> list[dict]:
        cursor = await self._db.execute(
            """SELECT role, content, timestamp FROM conversations
               WHERE phone = ? ORDER BY timestamp DESC LIMIT ?""",
            (phone, limit)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in reversed(rows)]

    async def clear_conversation(self, phone: str):
        await self._db.execute("DELETE FROM conversations WHERE phone = ?", (phone,))
        await self._db.commit()

    # ---- Cache Operations ----

    async def get_cached_response(self, query_hash: str) -> Optional[str]:
        cursor = await self._db.execute(
            "SELECT response_text FROM response_cache WHERE query_hash = ?",
            (query_hash,)
        )
        row = await cursor.fetchone()
        if row:
            await self._db.execute(
                """UPDATE response_cache SET hit_count = hit_count + 1,
                   last_used = CURRENT_TIMESTAMP WHERE query_hash = ?""",
                (query_hash,)
            )
            await self._db.commit()
            return row["response_text"]
        return None

    async def save_cache_entry(self, query_hash: str, query_text: str,
                                response_text: str, embedding: bytes = None):
        await self._db.execute(
            """INSERT OR REPLACE INTO response_cache
               (query_hash, query_text, response_text, embedding)
               VALUES (?, ?, ?, ?)""",
            (query_hash, query_text, response_text, embedding)
        )
        await self._db.commit()

    async def get_all_cache_embeddings(self) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT query_hash, query_text, response_text, embedding FROM response_cache WHERE embedding IS NOT NULL"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ---- Reminder Operations ----

    async def add_reminder(self, phone: str, message: str, remind_at: str) -> int:
        cursor = await self._db.execute(
            "INSERT INTO reminders (phone, message, remind_at) VALUES (?, ?, ?)",
            (phone, message, remind_at)
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_due_reminders(self) -> list[dict]:
        now = datetime.utcnow().isoformat()
        cursor = await self._db.execute(
            "SELECT * FROM reminders WHERE sent = 0 AND remind_at <= ?",
            (now,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def mark_reminder_sent(self, reminder_id: int):
        await self._db.execute(
            "UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,)
        )
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()
            logger.info("Database connection closed")
