"""Streamlit front end for the scrapers. Run with: streamlit run scraper_ui.py"""

from core.ao3 import parse_work_id
from core.fanficnet import parse_story_id
from helpers.database_helpers import Database
from helpers.sync import Scrapers, store_story, update_novels
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="Novel Scraper", layout="wide", initial_sidebar_state="expanded")

@st.cache_resource
def get_db() -> Database:
    return Database.from_env()

@st.cache_resource
def get_scrapers() -> Scrapers:
    return Scrapers()

def show_story(story: dict):
    """Preview a scraped story"""
    metadata, chapters = story["metadata"], story["chapters"]
    left, right = st.columns([2, 1])
    with left:
        st.markdown(f"### {metadata['title']}")
        st.markdown(f"**Author: **{metadata['author']}")
        st.markdown(f"**chapters: **{len(chapters)}")
        st.text_area("Description", str(metadata.get("description") or ""), height=150, disabled=True)

    with right:
        if metadata.get("img_url"):
            st.image(metadata["img_url"], width=200)
    if not story.get("complete", True):
        st.warning(
                f"The scrape stopped early: {story.get('error')}"
                )

def scrape_panel(key, label, placeholder, scraper_name, normalise=None):
    target = st.text_input(label, placeholder=placeholder, key=f"{key}_target")
    if st.button("Scrape", type="primary", key=f"{key}_scrape"):
        st.session_state.pop(f"{key}_story", None)
        try:
            wanted = normalise(target) if normalise else target.strip()
            if not wanted:
                raise ValueError("Enter a link first")
            with st.spinner("Scraping..."):
                st.session_state[f"{key}_story"] = get_scrapers().get(scraper_name).story(wanted)
        except Exception as e:
            st.error(str(e))

    story = st.session_state.get(f"{key}_story")
    if story:
        show_story(story)

        if st.button("Save to Database", type="primary", key=f"{key}_save"):
            try:
                result = store_story(get_db(), story)
                st.success(
                        f"Saved '{story['metadata']['title']}': {result.added} chapters added, {result.skipped} skipped."
                        )
                st.session_state.pop(f"{key}_story")
            except Exception as e:
                st.error(f"Could not save: {e}")

def page_novelbin():
    st.subheader("Scrape from NovelBin")
    keyword = st.text_input("Search by title", key="nb_keyword")
    if st.button("Search", key="nb_search") and keyword.strip():
        try:
            st.session_state["nb_results"] = get_scrapers().get("novelbin").search(keyword.strip())
        except Exception as exc:
            st.error(str(exc))
    results = st.session_state.get("nb_results")
    if results:
        pick = st.selectbox("Results", range(len(results)), format_func=lambda i: results[i]["title"])
        if st.button("Use this novel", key="nb_use"):
            st.session_state["nb_target"] = results[pick]["url"]
    elif results == []:
        st.info("No results.")
    scrape_panel("nb", "Novel link", "https://novelping.com/...", "novelbin")


def page_fanfic():
    st.subheader("Scrape from FanFiction.net")
    scrape_panel("ff", "Story link or id", "https://www.fanfiction.net/s/12345/1/", "fanfic_old", parse_story_id)


def page_ao3():
    st.subheader("Scrape from AO3")
    scrape_panel("ao3", "Work link or id", "https://archiveofourown.org/works/12345", "ao3", parse_work_id)


def page_update():
    st.subheader("Update existing novels")
    source = st.radio(
        "Which novels?",
        ["all", "novelbin", "fanfic", "ao3"],
        format_func={"all": "All unfinished", "novelbin": "NovelBin", "fanfic": "FanFiction.net", "ao3": "AO3"}.get,
    )
    if st.button("Find novels to update", key="up_load"):
        st.session_state["up_refs"] = get_db().novels_for_update(source)
    refs = st.session_state.get("up_refs")
    if refs is None:
        return
    st.info(f"{len(refs)} novels can be updated.")
    if refs and st.button("Start update", type="primary", key="up_start"):
        bar, status = st.progress(0.0), st.empty()

        def progress(index, total, ref):
            status.text(f"Updating {index}/{total}: {ref.title}")
            bar.progress(index / total)

        report = update_novels(get_db(), refs, get_scrapers(), progress=progress)
        status.text("Update complete.")
        st.success(f"{report.total_added} new chapters added.")
        for failure in report.failures:
            st.error(f"{failure.ref.title}: {failure.error}")
        st.session_state.pop("up_refs")


def page_metadata():
    st.subheader("Refresh FanFiction.net descriptions and covers")
    rows = get_db().fanfic_novels()
    st.info(f"{len(rows)} novels have a FanFiction.net id.")
    if rows and st.button("Refresh", type="primary", key="md_go"):
        bar = st.progress(0.0)
        scraper = get_scrapers().get("fanfic_old")
        for index, (novel_id, fanfic_id) in enumerate(rows, start=1):
            try:
                meta = scraper.metadata(fanfic_id)
                get_db().refresh_metadata(novel_id, meta["description"], meta.get("img_url"))
            except Exception as exc:
                st.error(f"Novel {novel_id}: {exc}")
            bar.progress(index / len(rows))
        st.success("Done.")


def page_status():
    st.subheader("Database status")
    stats = get_db().stats()
    columns = st.columns(5)
    for column, (label, key) in zip(
        columns,
        [("Novels", "novels"), ("Chapters", "chapters"), ("NovelBin", "novelbin"),
         ("FanFiction.net", "fanficnet"), ("AO3", "ao3")],
    ):
        column.metric(label, f"{stats[key]:,}")


PAGES = {
    "Scrape NovelBin": page_novelbin,
    "Scrape FanFiction.net": page_fanfic,
    "Scrape AO3": page_ao3,
    "Update novels": page_update,
    "Refresh metadata": page_metadata,
    "Database status": page_status,
}

st.title("Novel Scraper")
with st.sidebar:
    choice = st.radio("Action", list(PAGES))

PAGES[choice]()
st.caption(f"Page loaded {datetime.now():%Y-%m-%d %H:%M:%S}")
