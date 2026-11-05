import scraper
from config import COL_ICON, COL_INSTALLS, COL_RATING, COL_REVIEWS, COL_TITLE


def test_parse_installs_supports_localized_separators():
    assert scraper._parse_installs("100,000+") == 100_000
    assert scraper._parse_installs("10\u202f000+") == 10_000
    assert scraper._parse_installs(-10) == 0
    assert scraper._parse_installs(True) == 0
    assert scraper._parse_installs("1.5M") == 0


def test_normalize_row_handles_untrusted_metadata():
    row = scraper._normalize_row(
        "com.example.app",
        {
            "title": "  Example  ",
            "score": "not-a-number",
            "ratings": "invalid",
            "icon": "javascript:alert(1)",
        },
        12_500,
    )

    assert row[COL_TITLE] == "Example"
    assert row[COL_INSTALLS] == "12 500"
    assert row[COL_RATING] == "0.0"
    assert row[COL_REVIEWS] == 0
    assert row[COL_ICON] == ""


def test_collect_candidates_prioritizes_custom_queries(monkeypatch):
    monkeypatch.setattr(scraper, "MAX_LOCALES_PER_RUN", 1)
    monkeypatch.setattr(scraper, "_fetch_search", lambda *args: [])
    monkeypatch.setattr(scraper.random, "sample", lambda values, k: list(values)[:k])

    _, queries = scraper.collect_candidates(2, 20, set(), ["offline notes", "habits"])

    assert queries == ["offline notes", "habits"]


def test_fetch_details_uses_cache_and_batches_new_writes(monkeypatch):
    cached = {
        "cached": {
            "title": "Cached",
            "minInstalls": 20_000,
            "score": 4.5,
            "ratings": 100,
        }
    }
    fetched = {
        "fetched": {
            "title": "Fetched",
            "minInstalls": 30_000,
            "score": 4.7,
            "ratings": 200,
        }
    }
    writes = []
    monkeypatch.setattr(scraper.random, "sample", lambda values, k: list(values)[:k])
    monkeypatch.setattr(scraper, "get_cached_details_many", lambda ids: cached)
    monkeypatch.setattr(scraper, "_fetch_details", lambda app_id: fetched[app_id])
    monkeypatch.setattr(scraper, "set_cached_details_many", writes.append)

    rows = scraper.fetch_details_batch(["cached", "fetched"], 10_000, 0, 1)

    assert len(rows) == 2
    assert writes == [fetched]


def test_fetch_details_enforces_install_range(monkeypatch):
    details = {"app": {"title": "App", "minInstalls": 5_000}}
    monkeypatch.setattr(scraper.random, "sample", lambda values, k: list(values)[:k])
    monkeypatch.setattr(scraper, "get_cached_details_many", lambda ids: details)

    assert scraper.fetch_details_batch(["app"], 10_000, 0, 1) == []
    assert scraper.fetch_details_batch(["app"], 0, 1_000, 1) == []
