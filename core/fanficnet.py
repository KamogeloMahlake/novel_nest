import re

from .scraper import NotFound, ScrapeError, Scraper
from bs4 import BeautifulSoup

MAX_CHAPTERS = 5000
_STORY_URL = re.compile(r"/s/(\d+)")

def parse_story_id(value: int) -> str:
    "Returns the id as text"
    text = str(value).strip()
    if text.isdigit():
        return text

    match = _STORY_URL.search(text)
    if match:
        return match.group(1)
    raise ValueError("Enter a numeric Fanfiction.net story id or a story link.")


class FanfictionNet(Scraper):
    """
    Scraper for FanfictionNet stories.

    Inherits from Scraper and provides methods to fetch story metadata
    and chapter content from fanfiction.net.
    """

    def __init__(self, rate_limit: int = 2, base_url: str = "https://m.fanfiction.net", **kwargs):
        """Initialize FanfictionNet scraper with base URL."""
        super().__init__(rate_limit, **kwargs)
        self.base_url = base_url.rstrip("/")
        self.old_url = "https://www.fanfiction.net"

    def metadata(self, story_id: str ) -> dict:
        """
        Extract metadata for a story from FanfictionNet.

        Args:
            story_id (int): The story ID on FanfictionNet.

        Returns:
            dict: Dictionary containing title, author, description, and image URL.

        Raises:
            ValueError: If the story content cannot be found.
        """
        soup = BeautifulSoup(self.retry_fetch(f"{self.base_url}/s/{story_id}"), self.parser)
    
        content = soup.find(id="content")
        if content is None:
            raise NotFound("Story not found")
        title, author = content.find("b"), content.find("a")
        if title is None or author is None:
            raise ScrapeError("The story has no title or author")

        return {
                "title": title.get_text(strip=True),
                "author": author.get_text(strip=True),
                "description": " ",
                "img_url": None
                }

    def _walk(self, story_id: str, start: int) -> list:
        """Fetches chapters until one does not exist."""
        self.last_error = None
        chapters, number = [], start
        while len(chapters) < MAX_CHAPTERS:
            try:
                content = self.chapter(story_id, number)
            except NotFound:
                break
            except ScrapeError as e:
                self.last_error = str(e)
                break
            chapters.append((str(number), f"Chapter {number}", content))
            number += 1
            self.pause()
        return chapters


    def story(self, story: int) -> dict:
        """
        Fetch an entire story including metadata and all chapters.

        Prompts user for story ID and fetches all available chapters
        with retry logic.

        Returns:
            dict: Dictionary with 'metadata' and 'chapters' keys, or None if user exits.
        """
        story_id = parse_story_id(story)
        metadata = self.metadata(story_id)
        self.pause()
        chapters = self._walk(story_id, 1)
        return {
                "metadata": metadata,
                "chapters": chapters,
                "fanfic_id": story_id,
                "complete": self.last_error is None,
                "error": self.last_error
                }

    def chapter(self, story_id: str, chapter_number: int) -> str:
        """
        Fetch a specific chapter from a story.

        Args:
            story_id (int): The story ID.
            chapter_number (int): The chapter number to fetch.

        Returns:
            str: HTML string containing the chapter content.

        Raises:
            ValueError: If chapter content cannot be found.
        """
        url = f"{self.base_url}/s/{story_id}/{chapter_number}"
        reponse = self.retry_fetch(url)

        soup = BeautifulSoup(reponse, self.parser)
        chapter = soup.find(id="storycontent")
        if chapter is None:
            raise NotFound("Chapter content not found")

        return str(chapter)

    def update(
        self, story: int, last_chapter_number: int
    ) -> tuple[list[tuple], str]:
        """
        Check for and fetch new chapters added to a story since the last scrape.
        """
        story_id = parse_story_id(story)
        return self._walk(story_id, int(last_chapter_number) + 1), story_id
        
