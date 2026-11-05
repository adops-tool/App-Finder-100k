"""Streamlit presentation layer: search controls, result exploration and export."""

import logging
import re

import pandas as pd
import streamlit as st

from config import (
    COL_ICON,
    COL_INSTALLS,
    COL_LINK,
    COL_NOVELTY,
    COL_RATING,
    COL_REVIEWS,
    COL_TITLE,
    DEFAULT_MAX_INSTALLS,
    DEFAULT_MIN_INSTALLS,
    DEFAULT_QUERIES_PER_RUN,
    DEFAULT_RESULTS_LIMIT,
    DEFAULT_SEARCH_DEPTH,
    DISPLAY_COLUMNS,
    KEY_INSTALLS_INT,
    KEY_SCORE,
    MAX_INSTALLS_STEP,
    MIN_INSTALLS_STEP,
    QUERIES_PER_RUN_RANGE,
    RESULTS_LIMIT_RANGE,
    SEARCH_DEPTH_RANGE,
)
from db import clear_seen_apps, seen_apps_count

logger = logging.getLogger(__name__)

# App titles are untrusted input supplied by Play Store developers. Prefix every
# formula-capable string before CSV export to prevent spreadsheet code execution.
_FORMULA_TRIGGERS = frozenset("=+-@\t\r\n")
_MAX_CUSTOM_QUERIES = 6
_MAX_CUSTOM_QUERY_LENGTH = 80

_SORT_OPTIONS = {
    "novelty": "Неочевидность",
    "installs": "Скачивания",
    "rating": "Рейтинг",
    "reviews": "Количество оценок",
    "title": "Название",
}


def render_sidebar() -> dict:
    """Render search controls and return normalized discovery options."""
    st.sidebar.header("Параметры поиска")

    custom_query_text = st.sidebar.text_area(
        "Свои запросы (необязательно)",
        placeholder="Например: offline notes, puzzle for kids",
        help="Разделяйте запросы запятыми или новой строкой. До 6 запросов.",
        max_chars=600,
    )
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
        help="Больше результатов из каждого поискового запроса, но дольше запуск.",
    )
    queries_per_run = st.sidebar.slider(
        "Запросов за запуск",
        QUERIES_PER_RUN_RANGE[0],
        QUERIES_PER_RUN_RANGE[1],
        DEFAULT_QUERIES_PER_RUN,
    )
    sort_by_novelty = st.sidebar.checkbox(
        "Ранжировать по неочевидности",
        value=True,
        help="Учитывает жанр, популярность, рейтинг и количество оценок.",
    )

    installs_range_valid = not max_installs or max_installs >= min_installs
    if not installs_range_valid:
        st.sidebar.error("Максимум скачиваний меньше минимума — такой диапазон пуст.")

    st.sidebar.divider()
    total_seen = seen_apps_count()
    st.sidebar.metric("Приложений в истории", f"{total_seen:,}".replace(",", " "))
    with st.sidebar.expander("Управление историей"):
        st.caption(
            "Очистка не удаляет кэш метаданных, но приложения снова смогут попасть в выдачу."
        )
        confirm_clear = st.checkbox("Подтверждаю очистку", key="confirm_history_clear")
        if st.button(
            "Очистить историю",
            disabled=not confirm_clear,
            width="stretch",
        ):
            try:
                clear_seen_apps()
            except Exception:
                logger.exception("Failed to clear seen apps history")
                st.error("Не удалось очистить историю. Попробуйте ещё раз.")
            else:
                st.session_state["confirm_history_clear"] = False
                st.rerun()

    return {
        "min_installs": int(min_installs),
        "max_installs": int(max_installs),
        "results_limit": int(results_limit),
        "search_limit": int(search_limit),
        "queries_per_run": int(queries_per_run),
        "custom_queries": parse_custom_queries(custom_query_text),
        "sort_by_novelty": bool(sort_by_novelty),
        "installs_range_valid": installs_range_valid,
    }


def parse_custom_queries(raw_value: str) -> list[str]:
    """Parse, deduplicate and bound optional user-provided search phrases."""
    if not isinstance(raw_value, str):
        return []

    queries: list[str] = []
    seen: set[str] = set()
    for value in re.split(r"[,\n]", raw_value):
        query = " ".join(value.split())[:_MAX_CUSTOM_QUERY_LENGTH].strip()
        normalized = query.casefold()
        if not query or normalized in seen:
            continue
        seen.add(normalized)
        queries.append(query)
        if len(queries) == _MAX_CUSTOM_QUERIES:
            break
    return queries


def sort_result_rows(apps: list[dict], sort_by: str) -> list[dict]:
    """Return a sorted copy without changing cached discovery results."""
    sort_keys = {
        "novelty": lambda row: row.get(COL_NOVELTY, 0),
        "installs": lambda row: row.get(KEY_INSTALLS_INT, 0),
        "rating": lambda row: row.get(KEY_SCORE, 0),
        "reviews": lambda row: row.get(COL_REVIEWS, 0),
    }
    if sort_by == "title":
        return sorted(apps, key=lambda row: str(row.get(COL_TITLE, "")).casefold())
    if sort_by not in sort_keys:
        return list(apps)
    return sorted(apps, key=sort_keys[sort_by], reverse=True)


def render_results(found_apps: list[dict], selected_queries: list[str], results_limit: int) -> None:
    """Render summary metrics, a sortable application grid and CSV export."""
    if not found_apps:
        st.warning(
            "Ничего не найдено. Измените диапазон скачиваний или повторите запуск — "
            "Google Play мог временно ограничить запросы."
        )
        return

    available_sorts = [
        key
        for key in _SORT_OPTIONS
        if key != "novelty" or any(COL_NOVELTY in row for row in found_apps)
    ]
    sort_by = st.selectbox(
        "Сортировка результатов",
        options=available_sorts,
        format_func=_SORT_OPTIONS.__getitem__,
        index=0,
    )
    ordered = sort_result_rows(found_apps, sort_by)
    top = ordered[: max(1, results_limit)]

    _render_summary(top, selected_queries)
    if selected_queries:
        with st.expander("Запросы этого поиска"):
            st.write(", ".join(selected_queries))

    frame = pd.DataFrame(top)
    display = frame.copy()
    display[COL_INSTALLS] = display[KEY_INSTALLS_INT]
    display[COL_RATING] = display[KEY_SCORE]
    existing = [column for column in DISPLAY_COLUMNS if column in display.columns]

    column_config = {
        COL_ICON: st.column_config.ImageColumn("Иконка", width="small"),
        COL_INSTALLS: st.column_config.NumberColumn("Скачивания", format="compact"),
        COL_RATING: st.column_config.NumberColumn("Рейтинг", format="%.2f ★"),
        COL_REVIEWS: st.column_config.NumberColumn("Оценки", format="compact"),
        COL_LINK: st.column_config.LinkColumn("Google Play", display_text="Открыть ↗"),
    }
    if COL_NOVELTY in display.columns:
        column_config[COL_NOVELTY] = st.column_config.NumberColumn(
            "Неочевидность",
            format="%.4f",
            help="Выше — перспективнее с точки зрения ниши, рейтинга и популярности.",
        )

    st.dataframe(
        display[existing],
        width="stretch",
        hide_index=True,
        row_height=64,
        column_config=column_config,
    )
    st.download_button(
        "Скачать CSV",
        _build_csv(frame),
        f"google-play-apps-{pd.Timestamp.now():%Y%m%d-%H%M%S}.csv",
        "text/csv",
        width="stretch",
    )


def _render_summary(apps: list[dict], selected_queries: list[str]) -> None:
    """Render a compact overview of the currently displayed result set."""
    total_installs = sum(row.get(KEY_INSTALLS_INT, 0) for row in apps)
    rated = [float(row.get(KEY_SCORE, 0)) for row in apps if row.get(KEY_SCORE, 0)]
    average_rating = sum(rated) / len(rated) if rated else 0.0

    result_column, installs_column, rating_column, queries_column = st.columns(4)
    result_column.metric("Найдено", len(apps))
    installs_column.metric("Суммарно скачиваний", _compact_number(total_installs))
    rating_column.metric("Средний рейтинг", f"{average_rating:.2f}" if rated else "—")
    queries_column.metric("Запросов", len(selected_queries))


def _compact_number(value: int) -> str:
    """Format a non-negative count using a compact Russian-friendly suffix."""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f} млрд"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} млн"
    if value >= 1_000:
        return f"{value / 1_000:.1f} тыс."
    return str(value)


def _build_csv(df: pd.DataFrame) -> bytes:
    """Serialize results as UTF-8 CSV with spreadsheet formulas neutralized."""
    export_cols = [c for c in df.columns if not c.startswith("_") and c != COL_ICON]
    sanitized = df[export_cols].copy()
    for column in sanitized.columns:
        sanitized[column] = sanitized[column].map(_neutralize_cell)
    return sanitized.to_csv(index=False).encode("utf-8-sig")


def _neutralize_cell(value):
    """Prefix formula-capable strings so spreadsheet applications treat them as text."""
    if not isinstance(value, str) or not value or value[0] not in _FORMULA_TRIGGERS:
        return value
    return f"'{value}"
