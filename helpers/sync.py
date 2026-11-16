"""Scraping workflows shared by the command line and Streamlit pages"""

import logging
from dataclasses import dataclass, field
from core.ao3 import AO3
from core.fanficnet import FanfictionNet
from core.novelbin import NovelBin
from core.old_fanficnet import OldFanFicNet
from core.scraper import ScrapeError
from helpers.database_helpers import Database, NovelRef


log = logging.getLogger(__name__)

class Scrapers:
    """Created each sites scraper the first time it is needed, and closes them together."""
    def __init__(self, **options) -> None:
        self._options = options
        self._made: dict[str, NovelBin | FanfictionNet | OldFanFicNet | AO3] = {}

    def get(self, name: str) -> NovelBin | FanfictionNet | OldFanFicNet | AO3:
        if name not in self._made:
            s = {
                    "novelbin": NovelBin,
                    "fanfic": FanfictionNet,
                    "fanfic_old": OldFanFicNet,
                    "ao3": AO3
                    }
            self._made[name] = s[name](**self._options)

        return self._made[name]

    def close(self):
        for scraper in self._made.values():
            scraper.close()
        self._made.clear()

    def __enter__(self):
        return self

    def __exit__(self):
        self.close()

@dataclass
class StoreResult:
    novel_id: int
    added: int
    skipped: int
    complete: bool  = True
    error: str | None = None

def store_story(db: Database, story: dict) -> StoreResult:
    """Save a scraped story to the database"""
    novel_id = db.add_novel(
            story["metadata"],
            story.get("last_chapter_scraped"),
            story.get("fanfic_id"),
            story.get("ao3_id")
            )

    chapters = story["chapters"]
    added = db.add_chapters(novel_id, chapters)

    return StoreResult(
            novel_id=novel_id,
            added=added,
            skipped=len(chapters) - added,
            complete=story.get("complete", True),
            error=story.get("error")
            )

def update_novel(db: Database, ref: NovelRef, scrapers: Scrapers) -> int:
    start = db.max_chapter_num(ref.id)
    if ref.source == "fanfic":
        chapters, _ = scrapers.get("fanfic").update(ref.fanfic_id, start)
        last = None

    elif ref.source == "ao3":
        chapters, _ = scrapers.get("ao3").update(ref.ao3_id, start)
        last = None

    elif ref.source == "novelbin":
        chapters, last  = scrapers.get("novelbin").update(ref.last_chapter_scraped, start)
    else:
        raise ScrapeError("No source information stored for this novel.")
    added = db.add_chapters(ref.id, chapters)
    if chapters and last:
        db.set_last_chapter(ref.id, last)
    return added

@dataclass 
class Outcome:
    ref: NovelRef
    added: int = 0
    error: str | None = None

@dataclass
class UpdateReport:
    outcomes: list[Outcome] = field(default_factory=list)

    @property
    def total_added(self) -> int:
        return sum(o.added for o in self.outcomes)

    @property
    def failures(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.error]


def update_novels(db: Database, refs: list[NovelRef], scrapers: Scrapers, progress = None):
    """Update many novels. ``progress(index, total, ref)`` is called before each novel (used by the UI)"""
    report = UpdateReport()
    for index, ref in enumerate(refs, start=1):
        if progress:
            progress(index, len(refs), ref)

        try:
            report.outcomes.append(Outcome(ref, added=update_novel(db, ref, scrapers)))

        except Exception as e:
            log.warning("Update failed for %s: %s", ref.title, e)
            report.outcomes.append(Outcome(ref, error=str(e)))
    return report
