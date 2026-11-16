""" Command-line front end."""

import logging
import sys

from helpers.database_helpers import Database
from helpers.sync import Scrapers, StoreResult, UpdateReport, store_story, update_novels 
import argparse

MENU = """
Choose an action:
    1. Scrape from NovelBin
    2. Scrape from Fanfiction.net
    3. Scrape from AO3
    4. Kemono (not implemented yet)
    5. Update Novels
    6. Mark novels as completed
    7. Exit
    0. Fix a novel's last-chapter link
"""

def describe(result: StoreResult, title: str) -> str:
    """One readable line about a stored story."""
    line = f"'{title}': {result.added} chapters added"
    if result.skipped:
        line += f", {result.skipped} already stored"
    if not result.complete:
        line += f". STOPPED EARLY: {result.error}. Run Update to continue."

    return line

def scrape_one(db: Database, scrapers: Scrapers, site: str, target) -> StoreResult:
    name = "fanfic_old" if site == "fanfic" else site
    story = scrapers.get(name).story(target)
    result = store_story(db, story)
    print(describe(result, story["metadata"]["title"]))
    return result

def choose_novelbin_target(scrapers: Scrapers) -> str | None:
    keyword = input("Keyword to search for (or exit): ").strip()
    if not keyword or keyword.lower() == "exit":
        return None
    results = scrapers.get("novelbin").search(keyword)
    if not results:
        print("No results")
        return ""

    for index, item in enumerate(results):
        print(f"{index}. {item['title']}")

    pick = input("Number of the novel(or Enter to cancel): ").strip()
    if not pick.isdigit() or int(pick) >= len(results):
        print("Cancelled.")
        return ""
    return results[int(pick)]["url"]

def scrape_menu(db: Database, scrapers: Scrapers, site: str):
    """Keep scraping from one site until the user types 'back'."""
    while True:
        if site == "novelbin":
            target = choose_novelbin_target(scrapers)
        else:
            target = input("Story id or link ('exit'): ").strip()
            if target.lower() == "exit":
                return
        if target is None:
            return
        if target:
            try:
                scrape_one(db, scrapers, site, target)
            except Exception as e:
                print(f"Could not scrape: {e}")
        if input("Press Enter to scrape another, or type 'back': ").strip().lower() == "back":
            return
def update_menu(db: Database, scrapers: Scrapers):
    choice = input("1. NovelBin\n2. Fanfiction.net\n3. AO3\n4. All unfinished novels\nChoose 1-4: ").strip()
    source = {"1": "novelbin", "2": "fanfic", "3": "ao3", "4": "all"}.get(choice)
    if source is None:
        print("Invalid choice.")

    run_update(db, scrapers, source)

def run_update(db: Database, scrapers: Scrapers, source: str) -> UpdateReport:
    print("3")
    refs = db.novels_for_update(source)
    print("4")
    print(f"{len(refs)} novels to check.")
    report = update_novels(
            db, refs, scrapers, progress=lambda i, n, ref: print(f"[{i}/{n}] {ref.title}")
            )
    print(f"Done: {report.total_added} new chapters.")
    for f in report.failures:
        print(f"   FAILED {f.ref.title}: {f.error}")
    return report
    
def complete_menu(db: Database):
    for novel_id, title in db.unfinished_novels():
        a = input(f"Mark 'title' as completed? (y/n/stop): ").strip().lower()
        if a == "stop":
            return
        if a == "y":
            db.mark_completed(novel_id)
            print(f"'{title}' marked as completed.")

def last_chapter_menu(db: Database):
    for ref in db.novels_for_update("novelbin"):
        if input(f"Change last chapter for '{ref.title}' ({ref.last_chapter_scraped})? (y/n)").strip().lower() == "y":
            new_href= input("New last chapter link: ").strip()
            if new_href:
                db.set_last_chapter(ref.id, new_href)
                print("Updated.")

def interactive(db: Database, scrapers: Scrapers):
    while True:
        print(MENU)
        choice = input("Enter a number: ").strip()
        if choice == "1":
            scrape_menu(db, scrapers, "novelbin")
        elif choice == "2":
            scrape_menu(db, scrapers, "fanfic")
        elif choice == "3":
            scrape_menu(db, scrapers, "ao3")
        elif choice == "4":
            print("Kemono support has not been written yet")
        elif choice == "5":
            update_menu(db, scrapers)
        elif choice == "6":
            complete_menu(db)
        elif choice == "0":
            last_chapter_menu(db)
        elif choice in ("7", "exit", "q"):
            return
        else:
            print("Invalid choice.")

def build_parser():
    parser = argparse.ArgumentParser(description="Scrape novels into the Genesis database.")
    sub = parser.add_subparsers(dest="command")

    scrape = sub.add_parser("scrape", help="scrape one story")
    scrape.add_argument("site", choices=["novelbin", "fanfic", "ao3"])
    scrape.add_argument("target", help="novel URL (novelbin) or id/link (fanfic, ao3)")

    update = sub.add_parser("update", help="fetch new chapters for stored novels")
    update.add_argument("--source", choices=["all", "novelbin", "fanfic", "ao3"], default="all")

    export = sub.add_parser("export", help="write every novel to an EPUB file")
    export.add_argument("--out", default="ebooks")

    search = sub.add_parser("search", help="search NovelBin")
    search.add_argument("keyword")
    return parser


def main(argv: list[str] | None =None, db: Database | None = None,  scrapers: Scrapers | None = None):
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    own_db, own_scrapers = db is None, scrapers is None
    scrapers = scrapers or Scrapers()
    try:
        if args.command == "search":
            for item in scrapers.get("novelbin").search(args.keyword):
                print(f"{item['title']} {item['url']}")
            return 0
        db = db or Database.from_env()
        if args.command == "scrape":
            result = scrape_one(db, scrapers, args.site, args.target)
            return 0 if result.complete else 2
        if args.command == "update":
            return 1 if run_update(db, scrapers, args.source).failures else 0
        if args.command == "export":
            return 0
        interactive(db, scrapers)
        return 0
    except KeyboardInterrupt:
        print("\nStoppeed by user")
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        if own_scrapers or scrapers is not None:
            scrapers.close()
        if own_db or db is not None:
            db.close()

if __name__ == "__main__":
    sys.exit(main())
