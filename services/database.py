import sqlite3
import json
import time
from contextlib import contextmanager
from typing import Dict, Any, Optional, List
from config import Config
import asyncio
from concurrent.futures import ThreadPoolExecutor


@contextmanager
def get_db_connection() -> sqlite3.Connection:
    """Context manager for database connections to ensure proper cleanup"""
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Initialize database with proper connection handling"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                history TEXT,
                last_updated REAL,
                mode TEXT
            )
        """
        )
        conn.commit()


def save_conversation(conversation_id: str, data: Dict[str, Any]) -> None:
    """Save conversation using context manager for proper connection handling"""
    with get_db_connection() as conn:
        c = conn.cursor()

        # Serialize history and ensuring it's a JSON string
        history_json = json.dumps(data.get("history", []))

        c.execute(
            """
            INSERT OR REPLACE INTO conversations (id, title, history, last_updated, mode)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                conversation_id,
                data.get("title", "New Chat"),
                history_json,
                data.get("last_updated", time.time()),
                data.get("mode", "general"),
            ),
        )
        conn.commit()


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """Get conversation using context manager for proper connection handling"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
        row = c.fetchone()

    if row:
        return {
            "id": row["id"],
            "title": row["title"],
            "history": json.loads(row["history"]),
            "last_updated": row["last_updated"],
            "mode": row["mode"],
        }
    return None


def delete_conversation(conversation_id: str) -> None:
    """Delete conversation using context manager for proper connection handling"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()


def load_all_conversations() -> Dict[str, Dict[str, Any]]:
    """Load all conversations using context manager for proper connection handling"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id, title, last_updated, mode FROM conversations ORDER BY last_updated DESC"
        )
        rows = c.fetchall()

    conversations = {}
    for row in rows:
        conversations[row["id"]] = {
            "title": row["title"],
            "last_updated": row["last_updated"],
            "mode": row["mode"],
            "history": [],  # Don't load full history for list view to save bandwidth
        }
    return conversations


# Initialize table on import
init_db()


# Async versions for better performance in async applications
async def save_conversation_async(conversation_id: str, data: Dict[str, Any]) -> None:
    """Async version of save_conversation"""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        await loop.run_in_executor(executor, save_conversation, conversation_id, data)


async def get_conversation_async(conversation_id: str) -> Optional[Dict[str, Any]]:
    """Async version of get_conversation"""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        return await loop.run_in_executor(executor, get_conversation, conversation_id)


async def load_all_conversations_async() -> Dict[str, Dict[str, Any]]:
    """Async version of load_all_conversations"""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        return await loop.run_in_executor(executor, load_all_conversations)
