# Novel web scraper

Scrapes novels and fan fiction from **NovelBin/NovelPing**, **FanFiction.net** and **AO3** into the
`novel_novel` and `novel_chapter` tables of the Genesis Django site, keeps them up to date, and can
export every novel as an EPUB.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in the database settings
```

To try the scraper without PostgreSQL, set `DB_URL=sqlite:///scraper.db` in `.env`; it creates the
two tables itself.


## Use

```bash
python main.py                                   # interactive menu
python main.py scrape novelbin https://novelping.com/some-novel
python main.py scrape fanfic https://www.fanfiction.net/s/12345/1/   # a link or just the id
python main.py scrape ao3 https://archiveofourown.org/works/123456
python main.py update --source all               # all | novelbin | fanfic | ao3
python main.py export --out ebooks               # EPUB per novel
python main.py search "keyword"
python main.py ui                      # scrape/update from a web page
```

Exit codes: `0` ok, `1` error or a failed novel during update, `2` a scrape stopped early (network
trouble; run `update` to continue), `130` Ctrl+C.

## How it behaves

- Requests have a timeout and up to 3 attempts with back-off; a 429 waits for `Retry-After`.
- A 404 means "no such page / end of story". Network failures are **not** treated as the end: the scrape
  is reported incomplete and the saved resume point is accurate.
- Re-scraping or updating never duplicates chapters (matched by novel + chapter number).
- Cover images must be real images under 5 MB; a failed cover never stops a scrape.

## Layout

```
main.py, scraper_ui.py
core/       one scraper per site + text helpers
helpers/    Database (PostgreSQL or SQLite)
services/   ebook.py

```

