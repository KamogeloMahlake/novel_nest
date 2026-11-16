"""Database access for the scraper."""

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import sqlite3
from typing import Any
import psycopg2
from psycopg2.extensions import connection, cursor
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
    
    def _run(self, sql: str, params: tuple = ()) -> cursor | sqlite3.Cursor:
        c = self.conn.cursor()
        c.execute(sql.replace("%s", self.ph), params)
        return c

    def _one(self, sql: str, params: tuple = ()) -> tuple[Any, ...] | None:
        c = self._run(sql, params)
        row = c.fetchone()
        c.close()
        return row

    def find_novel_id(self, title: str) -> int | None:
        row = self._one("SELECT id FROM novel_novel WHERE title = %s", (title,))
        return row[0] if row else None

    def add_novel(self, meta: dict, last_chapter_scraped: str | None =None, fanfic_id: str | None =None, ao3_id: str | None = None) -> int:
        existing = self.find_novel_id(meta["title"])
        if existing is not None:
            self._run(
                    "UPDATE novel_novel SET last_chapter_scraped = COALESCE(%s, last_chapter_scraped), "
                    "fanfic_id = COALESCE(%s, fanfic_id), ao3_id = COALESCE(%s, ao3_id) WHERE id = %s",
                    (last_chapter_scraped, fanfic_id, ao3_id, existing),
                    ).close()
            self.conn.commit()
            return existing

        try:
            c = self._run(
                    "INSERT INTO novel_novel (title, creator, date, status, views, description), "
                    "last_chapter_scraped, fanfic_id, ao3_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (
                            meta["title"],
                            meta.get("author") or "Unknown",
                            _now(),
                            False,
                            0,
                            str(meta.get("description") or ""),
                            last_chapter_scraped,
                            fanfic_id,
                            ao3_id,

                            ),
                    )

            novel_id = c.fetchone()[0]
            c.close()
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            existing = self.find_novel_id(meta["title"])
            if existing is not None:
                return existing
            raise

        if meta.get("img_url"):
            self.download_cover(novel_id, meta["img_url"])

        return novel_id
    
    def download_cover(self, novel_id: str | int, url: str) -> bool:
        try:
            response = self._http_get(url, timeout=20)
            response.raise_for_status()

            if not response.headers.get("Content-Type", "").startswith("/image"):
                raise ValueError("Not an image")
            if len(response.content) > MAX_IMAGE_BYTES:
                raise ValueError("image too large")
            folder = self.media_dir / "novel-images"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{novel_id}.jpg").write_bytes(response.content)
            self._run(
                    "UPDATE novel_novel SET novel_image = %s WHERE id = %s",
                    (f"novel_images/{novel_id}.jpg", int(novel_id)),
                    ).close()
            self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            log.warning("Could not save cover for novel %s: %s", novel_id, e)
            return False

    def set_last_chapter(self, novel_id: str | int, href: str) -> None:
        self._run(
                "UPDATE novel_novel SET last_chapter_scraped = %s WHERE id =%s",
                (href, int(novel_id))
                ).close()
        self.conn.commit()

    def refresh_metadata(self, novel_id: int | str, description: str, img_url: str | None = None) -> None:
        self._run(
                "UPDATE novel_novel SET description = %s WHERE id %s",
                (description or "", int(novel_id)) 
                ).close()
        self.conn.commit()
        if img_url:
            self.download_cover(novel_id, img_url)
    
    def fanfic_novels(self) -> list[tuple | Any]:
        c = self._run("SELECT id, fanfic_id FROM novel_novel WHERE fanfic_id IS NOT NULL ORDER BY id")
        rows = c.fetchall()
        c.close()
        return rows

    def mark_completed(self, novel_id: str | int) -> None:
        self._run("UPDATE novel_novel SET status = TRUE WHERE id = %s", (int(novel_id),)).close()
        self.conn.commit()

    def max_chapter_num(self, novel_id: str | int) -> int:
        row = self._one("SELECT MAX(num) FROM novel_chapter WHERE novel_id = %s", (int(novel_id),))
        return row[0] if row and row[0] is not None else 0

    def add_chapter(self, novel_id: str | int, title: str, num: int, content: str, commit: bool = True) -> bool:
        if self._one("SELECT 1 FROM novel_chapter WHERE novel_id = %s AND num = %s", (int(novel_id), int(num))):
            return False
        self._run(
                "INSERT INTO novel_chapter (title, num, novel_id, content, date, views) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (title, int(num), int(novel_id), str(content), _now(), 0)
                ).close()
        if commit:
            self.conn.commit()
        return True

    def add_chapters(self, novel_id: int | str, chapters: list[tuple]) -> int:
        added = 0
        try: 
            for num, title, content in chapters:
                added += self.add_chapter(novel_id, title, num, content, commit=False)
                self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return added

    def novels_for_update(self, source: str = "all") -> list[NovelRef]:
        """Unfinished novels that can be updated from ``source`` """
        c = self._run(
                "SELECT id, title, fanfic_id, last_chapter_scraped, ao3_id FROM novel_novel"
                "WHERE status = FALSE ORDER BY id"
                )
        refs = [NovelRef(*row) for row in c.fetchall()]
        c.close()
        refs = [r for r in refs if r.source]
        return refs if source == "all" else [r for r in refs if r.source == source]

    def unfinished_novels(self) -> list[tuple[int, str]]:
        c = self._run("SELECT id, title, FROM novel_novel WHERE status = FALSE ORDER BY id")
        rows = c.fetchall()
        c.close()
        return rows

    def all_novels(self) -> list[tuple]:
        c = self._run("SELECT id, title, creator, date, status, views FROM novel_novel ORDER BY id")
        rows = c.fetchall()
        c.close()
        return rows

    def all_chapters(self) -> list[tuple]:
        c = self._run(
                "SELECT c.id, c.novel_id, c.title, c.num, c.date, c.views, n.title"
                "FROM novel_chapter c JOIN novel_novel n ON c.novel_id = n.id ORDER BY c.id"
                )
        rows = c.fetchall()
        c.close()
        return rows

    def stats(self) -> dict[str, int]:
        def count(sql: str) -> int:
            return self._one(sql)[0] or 0

        return {
                "novels": count("SELECT COUNT(*) FROM novel_novel"),
                "chapters": count("SELECT COUNT(*) FROM novel_chapter"),
                "fanficnet": count("SELECT COUNT(*) FROM novel_novel WHERE fanfic_id IS NOT NULL"),
                "ao3": count("SELECT COUNT(*) FROM novel_novel WHERE ao3_id IS NOT NULL"),
                "novelbin": count("SELECT COUNT(*) FROM novel_novel WHERE last_chapter_scraped IS NOT NULL AND fanfic_id IS NULL AND ao3_id is NULL")
                }


