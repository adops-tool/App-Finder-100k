import sqlite3

import db


def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "finder.db"))
    db.init_db()


def test_seen_history_is_deduplicated(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    db.save_seen_apps(["com.example.one", "com.example.one", "", "com.example.two"])

    assert db.load_seen_apps() == {"com.example.one", "com.example.two"}
    assert db.seen_apps_count() == 2

    db.clear_seen_apps()
    assert db.load_seen_apps() == set()


def test_details_cache_round_trip(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    details = {"com.example.one": {"title": "One"}, "com.example.two": {"title": "Two"}}

    db.set_cached_details_many(details)

    assert db.get_cached_details_many(details) == details
    assert db.get_cached_details("com.example.one") == {"title": "One"}


def test_invalid_cache_payload_is_a_miss(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    with sqlite3.connect(db.DB_PATH) as connection:
        connection.execute(
            "INSERT INTO app_details_cache (app_id, data) VALUES (?, ?)",
            ("com.example.invalid", "[]"),
        )

    assert db.get_cached_details("com.example.invalid") is None


def test_unserializable_cache_entry_does_not_block_other_writes(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    db.set_cached_details_many(
        {
            "com.example.bad": {"value": object()},
            "com.example.good": {"title": "Good"},
        }
    )

    assert db.get_cached_details("com.example.good") == {"title": "Good"}
