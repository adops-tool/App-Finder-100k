"""Streamlit entrypoint and orchestration for the Google Play random finder."""

import logging

import streamlit as st

from db import init_db, load_seen_apps, save_seen_apps
from scraper import collect_candidates, fetch_details_batch
from scoring import sort_apps
from ui import render_results, render_sidebar

logger = logging.getLogger(__name__)

# Session keys for the last successful run. Streamlit reruns the whole script on
# every interaction — including the click on the download button — so results
# have to outlive the run that produced them.
_RESULTS_KEY = "finder_results"
_QUERIES_KEY = "finder_queries"


@st.cache_resource(show_spinner=False)
def _bootstrap() -> None:
    """Prepare storage once per Streamlit process instead of once per rerun.

    Returns:
        None: Schema creation and cache pruning happen as a side effect.

    Examples:
        >>> _bootstrap()
    """
    init_db()


def _run_discovery(params: dict) -> tuple[list[dict], list[str]]:
    """Execute one discovery pass with the parameters chosen in the sidebar.

    Args:
        params (dict): Normalized options returned by :func:`ui.render_sidebar`.

    Returns:
        tuple[list[dict], list[str]]: The normalized result rows and the search
        keywords that produced them. Rows are only annotated with a novelty
        score when ``params["sort_by_novelty"]`` is set.
    """
    seen = load_seen_apps()

    candidates, selected_queries = collect_candidates(
        queries_per_run=params["queries_per_run"],
        search_limit=params["search_limit"],
        seen_apps=seen,
    )

    found = fetch_details_batch(
        app_ids=candidates,
        min_installs=params["min_installs"],
        max_installs=params["max_installs"],
        results_limit=params["results_limit"],
    )

    if params["sort_by_novelty"]:
        found = sort_apps(found)

    try:
        save_seen_apps({row["appId"] for row in found})
    except Exception as exc:
        # The scrape is already paid for: losing de-duplication history is
        # recoverable on the next run, throwing the results away is not.
        logger.warning("Cannot persist seen apps: %s", exc)
        st.warning("Не удалось сохранить историю — результаты показаны без сохранения.")

    return found, selected_queries


st.set_page_config(page_title="GP Random Finder", page_icon=None)
_bootstrap()

st.title("Google Play Random Finder")

params = render_sidebar()

if st.button("Найти", type="primary"):
    if not params["installs_range_valid"]:
        st.error("Максимум скачиваний не может быть меньше минимума — исправьте диапазон.")
    else:
        with st.spinner("Анализ Google Play..."):
            try:
                found, selected_queries = _run_discovery(params)
            except Exception as exc:
                logger.exception("Discovery run failed")
                st.error(f"Не удалось выполнить поиск: {exc}")
            else:
                st.session_state[_RESULTS_KEY] = found
                st.session_state[_QUERIES_KEY] = selected_queries

if _RESULTS_KEY in st.session_state:
    render_results(
        st.session_state[_RESULTS_KEY],
        st.session_state.get(_QUERIES_KEY, []),
        params["results_limit"],
    )
else:
    st.info("Задайте параметры слева и нажмите «Найти».")

st.divider()
st.caption("Данные Google Play (google-play-scraper)")
