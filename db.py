"""SQLite persistence for de-duplication state and the app-details cache.

The module exposes two concerns:

* ``seen_apps`` — durable history used to avoid re-reviewing the same app.
* ``app_details_cache`` — a TTL-bounded cache that keeps the scraper off the
  network for apps it has already inspected.

Cache helpers never raise: a cold, locked or corrupt cache must degrade into an
extra network call, not into a failed run.
"""

import json
import logging
import sqlite3
from collections.abc import Iterable, Sequence
from contextlib import contextmanager

from config import CACHE_TTL_DETAILS, DB_BUSY_TIMEOUT, DB_PATH

logger = logging.getLogger(__name__)

# SQLite caps the number of bound parameters per statement; batching keeps the
# cache lookup well below that ceiling regardless of the sample size.
_SQL_CHUNK_SIZE = 400

_TTL_MODIFIER = f"+{int(CACHE_TTL_DETAILS)} seconds"


@contextmanager
def _conn():
    """Yield a SQLite connection and commit changes on success.

    The connection is tuned for concurrent access: WAL lets readers proceed
    while a writer holds the lock, and ``busy_timeout`` makes contending
    writers wait instead of failing immediately with ``database is locked``.

    Yields:
        sqlite3.Connection: An open SQLite connection for the application
        database defined by ``DB_PATH``.

    Raises:
        sqlite3.Error: Propagates any database error raised while using the
            yielded connection or committing the transaction. The pending
            transaction is rolled back before the connection is closed.

    Examples:
        >>> with _conn() as connection:
        ...     isinstance(connection, sqlite3.Connection)
        True
    """
    con = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    """Create the application tables and drop expired cache rows.

    This function initializes the persistent storage used for tracking seen
    applications and caching fetched Google Play metadata. It also prunes
    cache entries that can no longer be served, which keeps the database file
    from growing without bound across long-lived deployments.

    Returns:
        None: This function updates the database schema in place.

    Raises:
        sqlite3.Error: Raised if SQLite cannot create or access the required
            tables.

    Examples:
        >>> init_db()
    """
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS seen_apps (
                app_id TEXT PRIMARY KEY,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS app_details_cache (
                app_id   TEXT PRIMARY KEY,
                data     TEXT NOT NULL,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute(
            """
            DELETE FROM app_details_cache
            WHERE datetime(cached_at, ?) <= datetime('now')
            """,
            (_TTL_MODIFIER,),
        )


def load_seen_apps() -> set[str]:
    """Load all previously seen application identifiers from the database.

    Returns:
        set[str]: A set of Google Play application IDs that have already been
        shown to the user.

    Raises:
        sqlite3.Error: Raised if the query against the ``seen_apps`` table
            fails.

    Examples:
        >>> isinstance(load_seen_apps(), set)
        True
    """
    with _conn() as con:
        # Stream the cursor instead of materialising every row twice; the
        # history table grows with every run.
        return {row[0] for row in con.execute("SELECT app_id FROM seen_apps")}


def save_seen_apps(app_ids: Iterable[str]) -> None:
    """Persist a collection of application IDs as already seen.

    Args:
        app_ids (Iterable[str]): Google Play application IDs to insert into the
            ``seen_apps`` table. Existing IDs are ignored.

    Returns:
        None: This function saves state in the database and does not return a
        value.

    Raises:
        sqlite3.Error: Raised if SQLite cannot insert the provided IDs.

    Examples:
        >>> save_seen_apps({"com.example.app"})
    """
    # Deduplicate first so a repeated ID cannot inflate the write batch.
    unique_ids = [app_id for app_id in dict.fromkeys(app_ids) if app_id]
    if not unique_ids:
        return
    with _conn() as con:
        con.executemany(
            "INSERT OR IGNORE INTO seen_apps (app_id) VALUES (?)",
            [(app_id,) for app_id in unique_ids],
        )


def clear_seen_apps() -> None:
    """Remove every stored application ID from the seen history.

    Returns:
        None: This function deletes rows from the ``seen_apps`` table in place.

    Raises:
        sqlite3.Error: Raised if SQLite cannot delete the stored history.

    Examples:
        >>> clear_seen_apps()
    """
    with _conn() as con:
        con.execute("DELETE FROM seen_apps")


def get_cached_details(app_id: str) -> dict | None:
    """Return cached Google Play metadata for an application when available.

    Args:
        app_id (str): The Google Play application ID whose cached details
            should be retrieved.

    Returns:
        dict | None: The cached application metadata as a dictionary when an
        unexpired entry exists, otherwise ``None``.

    Examples:
        >>> get_cached_details("com.example.app") is None
        True
    """
    return get_cached_details_many([app_id]).get(app_id)


def get_cached_details_many(app_ids: Iterable[str]) -> dict[str, dict]:
    """Return every unexpired cached payload for a batch of application IDs.

    Reading a whole batch in a single statement replaces the per-app query the
    fetch pipeline used to issue, removing hundreds of connection handshakes
    per run.

    Args:
        app_ids (Iterable[str]): Google Play application IDs to look up.
            Duplicates and empty values are ignored.

    Returns:
        dict[str, dict]: A mapping of application ID to cached metadata. IDs
        that are missing, expired or unreadable are simply absent. The cache is
        best effort: any database failure yields an empty mapping instead of
        propagating.

    Examples:
        >>> get_cached_details_many([]) == {}
        True
    """
    unique_ids = [app_id for app_id in dict.fromkeys(app_ids) if app_id]
    if not unique_ids:
        return {}

    cached: dict[str, dict] = {}
    for start in range(0, len(unique_ids), _SQL_CHUNK_SIZE):
        chunk: Sequence[str] = unique_ids[start:start + _SQL_CHUNK_SIZE]
        # Only the placeholder count is interpolated — every value is bound as a
        # parameter, so no caller-supplied string ever reaches the SQL text.
        placeholders = ",".join("?" * len(chunk))
        query = (
            "SELECT app_id, data FROM app_details_cache "  # noqa: S608
            f"WHERE app_id IN ({placeholders}) "
            "AND datetime(cached_at, ?) > datetime('now')"
        )
        try:
            with _conn() as con:
                rows = con.execute(query, (*chunk, _TTL_MODIFIER)).fetchall()
        except sqlite3.Error as exc:
            logger.warning("Details cache read failed (%s); refetching instead", exc)
            return cached

        for app_id, payload in rows:
            try:
                cached[app_id] = json.loads(payload)
            except (TypeError, json.JSONDecodeError):
                # A corrupt row must not take down the run; treat it as a miss.
                logger.warning("Discarding unreadable cache entry for %s", app_id)

    return cached


def set_cached_details(app_id: str, data: dict) -> None:
    """Store Google Play metadata for an application in the cache table.

    Args:
        app_id (str): The Google Play application ID used as the cache key.
        data (dict): The application details returned by the scraper library.

    Returns:
        None: This function writes the cached payload to the database.

    Raises:
        Nothing is raised on purpose. Serialization or storage problems are
        logged and swallowed so a failed cache write cannot discard details the
        caller already paid a network request for.

    Examples:
        >>> set_cached_details("com.example.app", {"title": "Example"})
    """
    if not app_id or not data:
        return

    try:
        payload = json.dumps(data, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        logger.warning("Cannot serialize details for %s: %s", app_id, exc)
        return

    try:
        with _conn() as con:
            con.execute(
                "INSERT OR REPLACE INTO app_details_cache (app_id, data) VALUES (?, ?)",
                (app_id, payload),
            )
    except sqlite3.Error as exc:
        logger.warning("Cannot cache details for %s: %s", app_id, exc)


def seen_apps_count() -> int:
    """Count how many unique application IDs are stored as seen.

    Returns:
        int: The number of rows currently stored in the ``seen_apps`` table.
        Returns ``0`` when the table cannot be read.

    Examples:
        >>> isinstance(seen_apps_count(), int)
        True
    """
    try:
        with _conn() as con:
            return int(con.execute("SELECT COUNT(*) FROM seen_apps").fetchone()[0])
    except sqlite3.Error as exc:
        logger.warning("Cannot count seen apps: %s", exc)
        return 0
