"""Database access for the scraper."""

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import sqlite3
from psycopg2.extensions import connection
import requests


log = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 5 * 1024 * 1024
SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS novel_novel (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL UNIQUE,
        creator TEXT,
        date TEXT,
        status BOOLEAN DEFAULT 0,
        views INTEGER DEFAULT 0,
        description TEXT, 
        last_chapter_scraped TEXT,
        fanfic_id TEXT,
        ao3_id TEXT,
        novel_image TEXT
        );

CREATE TABLE IF NOT EXISTS novel_chapter (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        num INTEGER NOT NULL,
        novel_id INTEGER NOT NULL REFERENCES novel_novel(id),
        content TEXT NOT NULL,
        date TEXT,
        views INTEGER DEFAULT 0
        );
"""

@dataclass 
class NovelRef:
    """A stored novel that may need updating."""
    id: int
    title: str
    fanfic_id: str | None = None
    last_chapter_scraped: str | None = None
    ao3_id: str | None = None

    @property
    def source(self) -> str | None:
        """Which scraper owns this novel."""
        if self.fanfic_id:
            return "fanfic"
        if self.ao3_id:
            return "ao3"
        if self.last_chapter_scraped:
            return "novelbin"
        return None

class Database:
    def __init__(self, connection: connection | sqlite3.Connection, paramstyle: str ="%s", media_dir: str = "./media", http_get=requests.get) -> None:
        self.conn = connection
        self.ph = paramstyle
        self.media_dir = Path(media_dir)
        self._http_get = http_get

    @classmethod
    def from_env(cls, media_dir: str | None = None):
        """Connect using DB_* variables (POSTGRESQL)"""
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass

        media_dir = media_dir or os.getenv("MEDIA_DIR", "./media")
        url = os.getenv("DB_URL", "")
        if url.startswith("sqlite:///"):
            return cls.sqlite(url[len("sqlite:///"):], media_dir)

        import psycopg2

        conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                database=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                port=os.getenv("DB_PORT", "5432")
                ) 
        return cls(conn, "%s, media_dir")

    @classmethod
    def sqlite(cls, path=":memory:", media="./media", **kwargs):
        """A SQLite databse with the two table the scraper uses."""
        conn = sqlite3.connect(path)
        conn.executescript(SQLITE_SCHEMA)
        return cls(conn, "?", media, **kwargs)


    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self):
        self.close()


