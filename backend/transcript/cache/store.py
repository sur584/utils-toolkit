"""SQLite-based cache for transcript results."""
import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# DB path: project_root/backend/transcript/cache/transcripts.db
DB_PATH = Path(__file__).parent / "transcripts.db"


def _get_conn() -> sqlite3.Connection:
    """Get SQLite connection, create table if needed."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            cache_key TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            platform TEXT,
            title TEXT,
            author TEXT,
            transcript TEXT,
            method_used TEXT,
            char_count INTEGER,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            cover TEXT,
            video_url TEXT,
            srt TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON transcripts(expires_at)")
    # Migrate: add columns if missing (existing databases)
    for col, typ in [("cover", "TEXT"), ("video_url", "TEXT"), ("srt", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE transcripts ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    return conn


def cache_key_for_url(url: str) -> str:
    """Generate cache key from URL."""
    return hashlib.sha256(url.encode()).hexdigest()


def get(url: str, ttl: int = 86400) -> Optional[dict]:
    """Get cached result for URL. Returns None if expired or not found."""
    key = cache_key_for_url(url)
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM transcripts WHERE cache_key = ?", (key,)
        ).fetchone()
        if not row:
            return None
        # Check expiry
        if row[9] < time.time():  # expires_at
            conn.execute("DELETE FROM transcripts WHERE cache_key = ?", (key,))
            conn.commit()
            return None
        return {
            "method_used": row[6],
            "transcript": row[5],
            "title": row[3],
            "platform": row[2],
            "author": row[4],
            "char_count": row[7],
            "cover": row[10] or "",
            "video_url": row[11] or "",
            "srt": row[12] or "",
        }
    finally:
        conn.close()


def put(url: str, result: dict, ttl: int = 86400) -> None:
    """Cache a transcript result."""
    key = cache_key_for_url(url)
    now = time.time()
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO transcripts
               (cache_key, url, platform, title, author, transcript, method_used, char_count, created_at, expires_at, cover, video_url, srt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (key, url, result.get("platform"), result.get("title"), result.get("author"),
             result.get("transcript"), result.get("method_used"), result.get("char_count"),
             now, now + ttl, result.get("cover", ""), result.get("video_url", ""), result.get("srt", ""))
        )
        conn.commit()
        logger.info("Cached result for URL: %s", url[:80])
    finally:
        conn.close()


def cleanup() -> int:
    """Delete expired entries. Returns count of deleted rows."""
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "DELETE FROM transcripts WHERE expires_at < ?", (time.time(),)
        )
        conn.commit()
        deleted = cursor.rowcount
        if deleted:
            logger.info("Cleaned up %d expired cache entries", deleted)
        return deleted
    finally:
        conn.close()
