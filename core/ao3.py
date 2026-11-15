import re

from helpers.text import clean_html

from .scraper import ScrapeError, Scraper
from bs4 import BeautifulSoup

_WORK_URL = re.compile(r"/works/(\d+)")
_CHAPTER_ID = re.compile(r"^chapter-(\d+)$")

def parse_work_id(value: int | str) -> str:
    text = str(value).strip()
    if text.isdigit():
        return text
    match = _WORK_URL.search(text)
    if match:
        return match.group(1)

    raise ValueError("Enter a numeric AO3 work id or a link")


class AO3(Scraper):
    """
    Scraper for Archive of Our Own (AO3) stories.

    Inherits from Scraper and provides methods to fetch story metadata
    and chapter content from archiveofourown.org.
    """

    def __init__(self, rate_limit: int = 2, base_url: str = "https://archiveofourown.org", **kwargs):
        """Initialize AO3 scraper with base URL."""
        super().__init__(rate_limit, **kwargs)
        self.base_url = base_url.rstrip("/")

    def _work_page(self, work_id: str) -> BeautifulSoup:
        url = f"{self.base_url}/works/{work_id}?view_adult=true&view_full_work=true"
        return BeautifulSoup(self.retry_fetch(url), self.parser)

    @staticmethod
    def _metadata_from(soup: BeautifulSoup) -> dict:
        title = soup.find("h2", class_="title heading")
        if title is None:
            raise ScrapeError("Work not found, restricted or blocked by site.")
        author  = soup.find("a", rel="author")
        summary = soup.select_one("div.summary.module")
        return {
                "title": title.get_text(strip=True),
                "author": author.get_text(strip=True) if author else "Anonymous",
                "description": str(summary)if summary is not None else "",
                "img_url": None
                }
        

    def metadata(self, work_id: int | str) -> dict:
        """
        Extract metadata for a story from AO3.

        Args:
            story_id (str): The story ID on AO3.
        """
        return self._metadata_from(self._work_page(parse_work_id(work_id)))

    @staticmethod
    def chapters_from(soup: BeautifulSoup) -> list:
        blocks = [
                (int(m.group(1)), div)
                for div in soup.find_all("div", id=_CHAPTER_ID)
                if (m := _CHAPTER_ID.match(div["id"]))
                ]

        if not blocks:
            single = soup.find(id="chapters")
            if single is None:
                return []
            return [(1, "Chapter 1", clean_html(single))]

        chapters = []
        for position, (_, div) in enumerate(sorted(blocks, key=lambda b: b[0]), start=1):
            title = div.find("h3", class_="title")
            text = div.find("div", class_="userstuff")
            if text is None:
                continue
            chapters.append(
                    (str(position), title.get_text(strip=True) if title else f"Chapter {position}", clean_html(text))
                    )
        return chapters

    
    def story(self, work: str | int ) -> dict:
        """
        Fetch an entire story including metadata and all chapters.
        """
        work_id = parse_work_id(work)
        soup = self._work_page(work_id)
        metadata = self._metadata_from(soup)
        chapters = self.chapters_from(soup)
        self.last_error = None
        
        return {
                "metadata": metadata, 
                "chapters": chapters, 
                "ao3_id": work_id,
                "complete": True,
                "error": None
                }


    def update(self, work: int | str, last_chapter_number: int) -> tuple[list, str]:
        """
        Fetch new chapters from a story starting after the last scraped chapter.
        """
        work_id = parse_work_id(work)
        soup = self._work_page(work_id)

        new = [
                (n, t, c) for n, t, c in self.chapters_from(soup) if int(n) > int(last_chapter_number)
                ]
        return new, work_id

