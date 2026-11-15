from re import NOFLAG

from core.scraper import NotFound, ScrapeError

from .fanficnet import FanfictionNet
from bs4 import BeautifulSoup


class OldFanFicNet(FanfictionNet):
    def __init__(self, rate_limit: int = 2, old_url: str = "https://www.fanfiction.net", **kwargs):
        """Initialize OldFanFicNet scraper with base URL."""
        super().__init__(rate_limit, base_url=old_url, **kwargs)
        self.old_url = old_url.rstrip("/")

    def metadata(self, story_id: str) -> dict:
        """
        Extract metadata for a story from the old FanfictionNet site.

        Args:
            story_id (str): The story ID on FanfictionNet.

        """
        url = f"{self.old_url}/s/{story_id}/1/"
        reponse = self.retry_fetch(url)
        soup = BeautifulSoup(reponse, self.parser)
        title = soup.find("b", class_="xcontrast_txt")
        author = soup.find("a", class_="xcontrast_txt")
        if title is None or author is None:
            raise ScrapeError("Story page not recognised (it may be removed or blocked).")
        descprition = soup.find("div", class_="xcontrast_txt")
        image = soup.find("img", class_="cimage")
        cover = image.get("src") if image else None

        if cover and cover.startswith("//"):
            cover = "https:" + cover
        elif cover and cover.startswith("/"):
            cover = self.old_url + cover

        return {
                "title": title.get_text(strip=True),
                "author": title.get_text(strip=True),
                "descprition": str(descprition) if descprition is not None else "",
                "img_url": cover
                }


    def chapter(self, story_id: str, chapter_number: int) -> str:
        """
        Fetch a specific chapter of a story from the old FanfictionNet site.

        Args:
            story_id (str): The story ID on FanfictionNet.
            chapter_number (int): The chapter number to fetch.
        Returns:

                                    str: The content of the chapter.

        """
        url = f"{self.old_url}/s/{story_id}/{chapter_number}"
        reponse = self.retry_fetch(url)
        soup = BeautifulSoup(reponse, self.parser)
        content = soup.find(id="storytextp")
        if content is None:
            raise NotFound("Chapter not found")
        return str(content)
