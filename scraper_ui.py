"""Streamlit front end for the scrapers. Run with: streamlit run scraper_ui.py"""

from helpers.database_helpers import Database
from helpers.sync import Scrapers
import streamlit as st

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
