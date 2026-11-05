import pandas as pd

from config import COL_NOVELTY, COL_REVIEWS, COL_TITLE, KEY_INSTALLS_INT
from ui import _build_csv, _compact_number, _neutralize_cell, parse_custom_queries, sort_result_rows


def test_custom_queries_are_trimmed_deduplicated_and_bounded():
    raw = " Offline   notes, offline notes, habits\nfocus, one, two, three, four"

    assert parse_custom_queries(raw) == [
        "Offline notes",
        "habits",
        "focus",
        "one",
        "two",
        "three",
    ]


def test_csv_export_neutralizes_formula_cells():
    payload = _build_csv(pd.DataFrame([{"name": "=HYPERLINK(1)"}, {"name": "-42"}])).decode(
        "utf-8-sig"
    )

    assert "'=HYPERLINK(1)" in payload
    assert "'-42" in payload


def test_numeric_cells_remain_numeric():
    assert _neutralize_cell(-42) == -42
    assert _neutralize_cell("ordinary text") == "ordinary text"


def test_result_sorting_does_not_mutate_source_order():
    rows = [
        {COL_TITLE: "Low", KEY_INSTALLS_INT: 100, COL_REVIEWS: 1, COL_NOVELTY: 0.2},
        {COL_TITLE: "High", KEY_INSTALLS_INT: 500, COL_REVIEWS: 5, COL_NOVELTY: 0.8},
    ]

    sorted_rows = sort_result_rows(rows, "installs")

    assert sorted_rows[0][COL_TITLE] == "High"
    assert rows[0][COL_TITLE] == "Low"


def test_compact_number_formatting():
    assert _compact_number(999) == "999"
    assert _compact_number(1_500) == "1.5 тыс."
    assert _compact_number(2_000_000) == "2.0 млн"
