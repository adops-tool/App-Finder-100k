"""Streamlit presentation layer: sidebar controls and result rendering."""

import logging

import pandas as pd
import streamlit as st

from config import (
    COL_ICON,
    DEFAULT_MAX_INSTALLS,
    DEFAULT_MIN_INSTALLS,
    DEFAULT_QUERIES_PER_RUN,
    DEFAULT_RESULTS_LIMIT,
    DEFAULT_SEARCH_DEPTH,
    DISPLAY_COLUMNS,
    MAX_INSTALLS_STEP,
    MIN_INSTALLS_STEP,
    QUERIES_PER_RUN_RANGE,
    RESULTS_LIMIT_RANGE,
    SEARCH_DEPTH_RANGE,
)
from db import clear_seen_apps, seen_apps_count

logger = logging.getLogger(__name__)

# Characters that turn a CSV cell into a formula when the export is opened in
# Excel, LibreOffice or Google Sheets. App titles are untrusted input supplied
# by any Play Store developer, so they are neutralised before export (CWE-1236).
_FORMULA_TRIGGERS = frozenset("=+-@\t\r")


def render_sidebar() -> dict:
    """Render the Streamlit sidebar and return the selected search options.

    Returns:
        dict: A dictionary containing normalized numeric limits and sorting
        preferences selected by the user, plus an ``installs_range_valid`` flag
        reporting whether the requested install window is usable.

    Examples:
        >>> isinstance(render_sidebar(), dict)
        True
    """
    st.sidebar.header("Параметры поиска")

    min_installs = st.sidebar.number_input(
        "Минимум скачиваний",
        min_value=0,
        value=DEFAULT_MIN_INSTALLS,
        step=MIN_INSTALLS_STEP,
    )
    max_installs = st.sidebar.number_input(
        "Максимум скачиваний (0 = без ограничения)",
        min_value=0,
        value=DEFAULT_MAX_INSTALLS,
        step=MAX_INSTALLS_STEP,
    )
    results_limit = st.sidebar.number_input(
        "Количество результатов",
        min_value=RESULTS_LIMIT_RANGE[0],
        max_value=RESULTS_LIMIT_RANGE[1],
        value=DEFAULT_RESULTS_LIMIT,
    )
    search_limit = st.sidebar.slider(
        "Глубина поиска на запрос",
        SEARCH_DEPTH_RANGE[0],
        SEARCH_DEPTH_RANGE[1],
        DEFAULT_SEARCH_DEPTH,
    )
    queries_per_run = st.sidebar.slider(
        "Запросов за запуск",
        QUERIES_PER_RUN_RANGE[0],
        QUERIES_PER_RUN_RANGE[1],
        DEFAULT_QUERIES_PER_RUN,
    )
    sort_by_novelty = st.sidebar.checkbox("Сортировать по неочевидности", value=True)

    # An inverted window can never match a single app; surface it before the
    # user spends a full scrape discovering that.
    installs_range_valid = not max_installs or max_installs >= min_installs
    if not installs_range_valid:
        st.sidebar.error("Максимум скачиваний меньше минимума — такой диапазон пуст.")

    st.sidebar.divider()
    total_seen = seen_apps_count()
    st.sidebar.caption(f"В базе уникальных приложений: **{total_seen}**")
    if st.sidebar.button("Очистить историю"):
        try:
            clear_seen_apps()
        except Exception as exc:
            logger.exception("Failed to clear seen apps history")
            st.sidebar.error(f"Не удалось очистить историю: {exc}")
        else:
            st.rerun()

    return {
        "min_installs": int(min_installs),
        "max_installs": int(max_installs),
        "results_limit": int(results_limit),
        "search_limit": int(search_limit),
        "queries_per_run": int(queries_per_run),
        "sort_by_novelty": bool(sort_by_novelty),
        "installs_range_valid": installs_range_valid,
    }


def render_results(found_apps: list[dict], selected_queries: list[str], results_limit: int) -> None:
    """Render the result table and CSV download controls in Streamlit.

    Args:
        found_apps (list[dict]): Normalized application rows prepared for
            display.
        selected_queries (list[str]): The sampled search phrases used for the
            current run.
        results_limit (int): The maximum number of rows to display and export.

    Returns:
        None: This function writes UI elements directly to the Streamlit page.

    Examples:
        >>> render_results([], ["puzzle"], 10)
    """
    if not found_apps:
        st.warning(
            "Ничего не найдено. Снизьте минимум скачиваний, уберите ограничение "
            "максимума или повторите запуск — Google Play мог временно ограничить запросы."
        )
        return

    top = found_apps[: max(1, results_limit)]
    st.success(f"Запросы: {', '.join(selected_queries)} | Найдено: {len(top)}")

    df = pd.DataFrame(top)
    existing = [column for column in DISPLAY_COLUMNS if column in df.columns]
    st.dataframe(df[existing], width="stretch")

    csv = _build_csv(df)
    st.download_button("Скачать CSV", csv, "results.csv", "text/csv")


def _build_csv(df: pd.DataFrame) -> bytes:
    """Serialize a result frame into a spreadsheet-safe CSV payload.

    Args:
        df (pd.DataFrame): The result rows to export.

    Returns:
        bytes: UTF-8 text with a BOM so Excel detects the encoding of the
        Cyrillic headers, and with formula triggers neutralised.

    Examples:
        >>> _build_csv(pd.DataFrame([{"a": "=1+1"}])).startswith(b"\\xef\\xbb\\xbf")
        True
    """
    export_cols = [c for c in df.columns if not c.startswith("_") and c != COL_ICON]
    sanitized = df[export_cols].copy()
    for column in sanitized.columns:
        sanitized[column] = sanitized[column].map(_neutralize_cell)
    # utf-8-sig keeps Cyrillic headers readable in Excel, which otherwise
    # assumes a legacy code page.
    return sanitized.to_csv(index=False).encode("utf-8-sig")


def _neutralize_cell(value):
    """Prefix a leading formula trigger with an apostrophe.

    Args:
        value (Any): A single cell value from the export frame.

    Returns:
        Any: The original value when it is not a risky string, otherwise the
        value prefixed with ``'`` so spreadsheet applications treat it as text.
        Genuine numbers (including negative ones) are left untouched.

    Examples:
        >>> _neutralize_cell("=HYPERLINK(1)").startswith("'")
        True
        >>> _neutralize_cell("-42")
        '-42'
    """
    if not isinstance(value, str) or not value or value[0] not in _FORMULA_TRIGGERS:
        return value
    try:
        float(value)
    except ValueError:
        return f"'{value}"
    return value
