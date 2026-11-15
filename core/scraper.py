"""

Web scraper module for extracting novel content from various sources.

This module provides classes for scraping novels from different websites,
including FanfictionNet and NovelBin. It handles fetching, parsing, and
organizing chapter content into structured formats.
"""
import logging
import requests
import time

log = logging.getLogger(__name__)

class ScrapeError(Exception):
    """A page could not be fetched or understood"""
    
class NotFound(ScrapeError):
    """The page does not exist."""

class _RateLimited(Exception):
    def __init__(self, retry_after) -> None:
        super().__init__("rate limited")
        self.retry_after = retry_after

def make_session():
    """A cloudscraper session if available, else requests"""
    try:
        import cloudscraper
        return cloudscraper.create_scraper()
    except ImportError:
        return requests.Session()

class Scraper:
    """
    Base scraper class for fetching and parsing web content.

    Attributes:
        rate_limit (int): Delay in seconds between requests to avoid rate limiting.
        session: anything eith ``get(url, timeout=...)``
        retries: total attempts per URL
        timeout: seconds before a request is given up
        sleep
    """

    def __init__(self, rate_limit: int =2, session: requests.Session | None =None, retries: int =3, timeout: int =30, sleep=time.sleep):
        """Initialize the base scraper with default settings."""
        self.rate_limit = rate_limit
        self.parser = "html.parser"
        self.retries = max(1, retries)
        self.timeout = timeout
        self._sleep = sleep
        self.session = session if session is not None else make_session()
        self.last_error = None

    def fetch(self, url) -> bytes:
        """
        Fetch content from a given URL.

        Args:
            url (str): The URL to fetch.

        Returns:
            bytes: The response content.

        Raises:
            HTTPError: If the request returns an error status code.
        """
        response = self.session.get(url, timeout=self.timeout)
        try:
            if response.status_code in (404, 410):
                raise NotFound(f"Not Found: {url}")
            if response.status_code == 429:
                header = response.headers.get("Retry-After", "")
                raise _RateLimited(int(header) if header.isdigit() else None)
            response.raise_for_status()
            return response.content
        finally:
            response.close()

    def retry_fetch(self, url: str) -> bytes:
        """
        Fetch content from a URL with retry logic.

        Args:
            url (str): The URL to fetch.

        Returns:
            bytes: The response content.

        Raises:
            Exception: If all retry attempts fail.
        """
        failure = None

        for attempt in range(1, self.retries + 1):
            wait = min(attempt ** 2, 30)
            try:
                return self.fetch(url)
            except NotFound:
                raise 
            except _RateLimited as rate:
                failure = rate
                wait = min(rate.retry_after or 10 * attempt, 60)
            except requests.RequestException as e:
                failure = e
            if attempt < self.retries:
                log.warning("Attempt %d%d failed for %s: %s", attempt, self.retries, url, failure)
                self._sleep(wait)
        raise ScrapeError(f"Could not fetch {url} after {self.retries} attempts: {failure}")


    def close(self):
        """Close the scraper session."""
        self.session.close()

    def pause(self):
        """Wait between two requests so site is not hammered."""
        if self.rate_limit:
            self._sleep(self.rate_limit)

    def __enter__(self):
        return self

    def __exit__(self):
        return self.close()
