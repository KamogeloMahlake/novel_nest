from helpers.text import text_to_html
from .scraper import Scraper
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin, urlparse

class NovelBin(Scraper):
    """
    Scraper for NovelBin-style sites (default host: novelping.com).

    Inherits from Scraper and provides methods to search, fetch metadata,
    and scrape chapter content from novelbin.me.
    """

    def __init__(self, rate_limit=2, base_url="https://novelping.com"):
        """Initialize NovelBin scraper with base URL."""
        super().__init__(rate_limit)
        self.base_url = base_url.rstrip("/")

    def normalize_url(self, url):
        """Make a stored or scraped link usable"""

        if not url:
            return ""

        absolute = urljoin(self.base_url + "/", url)
        return absolute

    def search(self, keyword):
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

    def metadata(self, url):
        """
        Extract metadata for a novel from NovelBin.

        Args:
            url (str): The novel URL on NovelBin.

        Returns:
            tuple: A tuple containing (metadata dict, next_chapter element).
        """
        reponse = self.retry_fetch(url)
        soup = BeautifulSoup(reponse, self.parser)

        title = soup.find("h3", class_="title").getText()
        try:
            img = soup.find("img", class_="lazy")["data-src"]
        except Exception:
            img = None
        desc = soup.find("div", class_="desc-text")

        try:
            author = (
                soup.find("ul", class_="info info-meta")
                .getText()
                .split(" ")[0]
                .split("\n")[3]
            )
        except Exception:
            author = "Unknown"

        next_chapter = soup.find(title="READ NOW", href=True)
        return {
            "title": title,
            "author": author,
            "img_url": img,
            "description": str(desc),
        }, next_chapter['href']

    def story(self, url=None):
        """
        Fetch an entire novel including metadata and all chapters.

        Prompts user for search keyword and fetches all available chapters.

        Returns:
            dict: Dictionary with 'metadata' and 'chapters' keys, or None if user exits.
        """
        if url is None:
            keyword = input(
                "Enter a keyword to search for novels (or type 'exit' to quit): "
            )
            if keyword.lower() == "exit":
                return None
            metadata, self.chapter_url = self.metadata(self.search(keyword))

        else:
            metadata, self.chapter_url = self.metadata(url)
        self.last_chapter_scraped = None

        self.chapter_num = 0
        chapters = []
        sleep(self.rate_limit)
        
        while True:
            try:
                with ThreadPoolExecutor() as executor:
                    future = executor.submit(self.chapter)
                    title, content = future.result()
                    print(f"Fetched chapter {self.chapter_num}: {title}")
                    chapters.append((str(self.chapter_num), title, content))
                    print(f"Fetching chapter from {self.chapter_url}")
                    sleep(self.rate_limit)


            except Exception as e:
                print(f"{e}")
                break
        print("Scraping completed.")
        print(f"{self.last_chapter_scraped} was the last chapter found.")
        self.close()
        return {
            "metadata": metadata,
            "chapters": chapters,
            "last_chapter_scraped": self.last_chapter_scraped,
        }

    def chapter(self):
        """
        Fetch a specific chapter from a novel.

        Args:
            url (str): The chapter URL.
            chapter_num (int): The current chapter number.

        Returns:
            tuple: A tuple containing (next_chapter element, chapter_num, title, content).
        """
        try:
            page = self.retry_fetch(self.chapter_url)
        except Exception:
            raise ValueError("Chapter not found")
        soup = BeautifulSoup(page, "html.parser")
        content = soup.find("div", id="chr-content").get_text(separator="\n")

        try:
            title = soup.find("span", class_="chr-text").getText(strip=True)
        except TypeError:
            title = soup.find("h2").getText(strip=True)

        self.chapter_num += 1
        self.last_chapter_scraped = self.chapter_url
        self.chapter_url = soup.find_all("a", class_="js-chapter-nav")[1]['href']

        return title, str(self.text_to_html(content))

    def text_to_html(self, text):
        """
        Convert plain text to HTML paragraphs.

        Args:
            text (str): Plain text with newline separators.

        Returns:
            str: HTML string with text wrapped in <p> tags.
        """
        array = text.split("\n")
        html = [f"<p>{s}</p>" for s in array]
        return "".join(html)

    def update(self, last_chapter_url, last_chapter_number):
        """
        Check for and fetch new chapters added to a novel since the last scrape.

        Args:
            last_chapter_url (str): The URL of the last chapter scraped.
            last_chapter_number (int): The last chapter number that was scraped.
        Returns:
            tuple: A tuple containing (list of new chapters, last_chapter_scraped element).
        """
        self.chapter_url = last_chapter_url
        self.chapter_num = last_chapter_number
        self.last_chapter_scraped = None
        
        try:
            page = self.retry_fetch(self.chapter_url)
        except Exception:
            return [], last_chapter_url
        
        soup = BeautifulSoup(page, "html.parser")
        self.chapter_url = soup.find_all("a", class_="js-chapter-nav")[1]['href']
        new_chapters = []

        sleep(self.rate_limit)

        while True:
            try:
                with ThreadPoolExecutor() as executor:
                    future = executor.submit(self.chapter)

                    title, content = future.result()
                    print(f"Fetched new chapter {self.chapter_num}: {title}")
                    sleep(self.rate_limit)
                    new_chapters.append((str(self.chapter_num), title, content))
            
            except Exception as e:
                print(f"{e}")
                break
        self.close()
        return new_chapters, self.last_chapter_scraped if self.last_chapter_scraped else self.chapter_url
