"""Text and HTML helpers"""

from bs4 import BeautifulSoup
import html
import re

UNWANTED_TAGS = ("script", "style", "iframe", "noscript", "ins")

def text_to_html(text):
    """Plain text to escaped ``<p>``"""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "".join(f"<p>{html.escape(line.strip())}</p>" for line in lines if line.strip())


def html_to_text(content):
    soup = BeautifulSoup(content or "", "html.parser")
    paragraps = soup.find_all("p")
    if paragraps:
        return "\n".join(p.get_text() for p in paragraps)
    return soup.get_text(separator="\n")

def clean_html(node):
    """Returns HTML string as a string with scripts, styles and frames removed."""

    if node is None:
        return ""

    soup = BeautifulSoup(str(node), "html.parser")
    for tag in soup.find_all(UNWANTED_TAGS):
        tag.decompose()
    return str(soup)

def safe_filename(title, extension, fallback="novel"):
    name = re.sub(r'[\x00-\x1f"\\/:*?<>|]', "", title or "")
    name = re.sub(r"\s+", " ", name).strip(" .")[:100] or fallback
    return f"{name}.{extension}"
