"""Export novels from the database to EPUB files"""

import html
import logging
from pathlib import Path
from helpers.database_helpers import Database
from helpers.text import safe_filename, text_to_html, html_to_text

log = logging.getLogger(__name__)

def chapter_html(title: str, content: str) -> str:
    if "window.pubfuturetag" in content:
        content = text_to_html(html_to_text(content))
    return f"<h1>{html.escape(title)}</h>{content}"

def create_epub(title: str, chapters: list, out_dir: str = "ebooks") -> Path:
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_title(title)
    book.set_language("en")

    for index, (chapter_title, content) in enumerate(chapters, start=1):
        item = epub.EpubHtml(title=chapter_title, file_name=f"chap_{index}.xhtml", lang="en")
        item.content = chapter_html(chapter_title, content)
        book.add_item(item)
        book.toc.append(item)
        book.spine.append(item)

    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / safe_filename(title, "epub")
    epub.write_epub(str(path), book, {})
    return path

def export_all(db: Database, out_dir: str = "ebooks") -> list[Path]:
    c = db._run("SELECT id, title FROM novel_novel ORDER BY id")
    novels = c.fetchall()
    c.close()
    written = []

    for novel_id, title in novels:
        c = db._run(
                "SELECT title, content FROM novel_chapter WHERE novel_id = %s ORDER BY num",
                (novel_id,)
                )
        chapters = c.fetchall()
        c.close()
        if not chapters:
            continue
        path = create_epub(title, chapters, out_dir)
        print(f"Created EPUB: {path}")
        written.append(path)
    return written

def main():
    with Database.from_env() as db:
        export_all(db)

if __name__ == "__main__":
    main()
