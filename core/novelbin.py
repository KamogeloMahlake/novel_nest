from helpers.text import text_to_html
from .scraper import ScrapeError, Scraper
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin

MAX_CHAPTERS = 20000

class NovelBin(Scraper):
    """
    Scraper for NovelBin-style sites (default host: novelping.com).

    Inherits from Scraper and provides methods to search, fetch metadata,
    and scrape chapter content from novelbin.me.
    """

    def __init__(self, rate_limit: int =2, base_url: str ="https://novelping.com"):
        """Initialize NovelBin scraper with base URL."""
        super().__init__(rate_limit)
        self.base_url = base_url.rstrip("/")

    def normalize_url(self, url: str):
        """Make a stored or scraped link usable"""

        if not url:
            return ""

        absolute: str = urljoin(self.base_url + "/", url)
        return absolute

    def search(self, keyword: str) -> list[dict]:
        """
        Search for novels by keyword on NovelBin.

        Args:
            keyword (str): The search keyword.

        Returns:
            str: The URL of the selected novel.
        """
        
        page = self.retry_fetch(f"{self.base_url}/search?keyword={quote_plus(keyword)}")
        soup = BeautifulSoup(page, self.parser)
        results = []

        for heading in soup.find_all("h3", class_="novel-title"):
            link = heading.find("a", href=True)
            if link:
                results.append(
                        {"title": link.get_text(strip=True), "url": self.normalize_url(link["href"])}
                        )

        return results

    def metadata(self, url: str) -> tuple[dict, str]:
        """
        Extract metadata for a novel from NovelBin.

        Args:
            url (str): The novel URL on NovelBin.

        Returns:
            tuple: A tuple containing (metadata dict, next_chapter element).
        """
        soup = BeautifulSoup(self.retry_fetch(self.normalize_url(url)), self.parser)
        
        title = soup.find("h3", class_="title")
        if title is None:
            raise ScrapeError("This does not look like a novel page (no title found).")

        image = soup.find("img", class_="lazy")
        description = soup.find("div", class_="desc-text")
        info = soup.find("ul", class_="info info-meta")
        author = "Unknown"
        if info is not None:
            lines = [line.strip() for line in info.get_text("\n").split("\n") if line.strip()]
            if len(lines) >= 2:
                author = lines[1]

        read_now = soup.find(title="READ NOW", href=True)
        if read_now is None:
            raise ScrapeError("No 'Read Now' link found, so the first chapter is unknown.")
        return {
                "title": title.get_text(strip=True),
                "author": author,
                "img_url": self.normalize_url(image.get("data-src")) if image and image.get("data-src") else None,
                "description": str(description) if description is not None else "",
                }, self.normalize_url(read_now["href"])

    @staticmethod
    def _next_url(soup: BeautifulSoup) -> str | None:
        """The link to the next chapter or None on the last chapter."""
        links = soup.find_all("a", class_="js-chapter-nav")
        for link in reversed(links[1:]):
            href = (link.get("href") or "").strip()
            if href and not href.startswith(("#", "javascript")) and "disabled" not in (link.get("class") or []):
                return href
        return None


    def story(self, url: str) -> dict:
        """
        Fetch an entire novel including metadata and all chapters.
        """
        metadata, first_url = self.metadata(url)
        self.pause()
        chapters, last_url = self._walk(first_url, 1)
        return {
                "metadata": metadata,
                "chapters": chapters,
                "last_chapter_scraped": last_url if chapters else None,
                "complete": self.last_error is None,
                "error": self.last_error
                }

    def chapter(self, url: str, number: int | None = None) -> tuple[str, str, str | None]:
        """
        Fetch a specific chapter from a novel.
        """
        soup = BeautifulSoup(self.retry_fetch(url), self.parser)
        body = soup.find("div", id="chr-content")
        if body is None:
            raise ScrapeError(f"Chapter text not at {url}")
        title_tag = soup.find("span", class_="chr-text") or soup.find("h2")
        title = title_tag.get_text(strip=True) if title_tag else f"Chapter {number or ''}"
        next_href = self._next_url(soup)
        return title, text_to_html(body.get_text(separator="\n")), (self.normalize_url(next_href) if next_href else None)

    def _walk(self, url: str, number: int, last_url: str | None = None) -> tuple[list, str | None]:
        """Follow nexts links from ``start_url``; return (chapters, last_url)"""
        self.last_error = None
        chapters, seen = [], set()
        while url and url not in seen and len(chapters) < MAX_CHAPTERS:
            seen.add(url)
            try:
                title, content, next_url = self.chapter(url, number)
            except ScrapeError as e:
                self.last_error = str(e)
                break
            chapters.append((str(number), title, content))
            last_url = url
            number += 1
            url = next_url
            if url:
                self.pause()
        return chapters, last_url
        

    def update(self, last_chapter_url: str, last_chapter_number: int) -> tuple[list, str | None]:
        """
        Check for and fetch new chapters added to a novel since the last scrape.

        Args:
            last_chapter_url (str): The URL of the last chapter scraped.
            last_chapter_number (int): The last chapter number that was scraped.
        Returns:
            tuple: A tuple containing (list of new chapters, last_chapter_scraped element).
        """
        last_url = self.normalize_url(last_chapter_url)
        soup = BeautifulSoup(self.retry_fetch(last_url), self.parser)
        next_href = self._next_url(soup)
        if not next_href:
            self.last_error = None
            return [], last_chapter_url
        self.pause()

        chapters, new_last = self._walk(self.normalize_url(next_href), last_chapter_number + 1, last_url)
        return chapters, new_last
