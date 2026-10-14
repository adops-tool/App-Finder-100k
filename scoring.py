"""Novelty scoring used to surface less obvious apps ahead of popular ones."""

import math

from config import (
    COL_NOVELTY,
    COL_RATING,
    COL_REVIEWS,
    KEY_GENRE,
    KEY_INSTALLS_INT,
    KEY_SCORE,
    NICHE_GENRES,
)

# Install count at which the popularity component is halved.
_INSTALLS_HALFLIFE = 200_000

# Rating volume that counts as fully confirmed. Hoisted out of the scoring loop
# because ``log1p`` of a constant was being recomputed for every single app.
_RATINGS_CONFIDENCE_CAP = math.log1p(50_000)

# Weight applied to genres that are historically less saturated.
_NICHE_GENRE_BONUS = 1.4

# Floor used when an app has too few ratings to trust its average.
_UNCONFIRMED_RATING_FLOOR = 0.3


def novelty_score(genre: str, installs: int, rating: float, ratings_count: int) -> float:
    """Calculate a novelty score for an application discovery result.

    The score favors niche genres, lower install counts, and stronger ratings
    while discounting ratings with little review volume.

    Args:
        genre (str): The application genre label returned by Google Play.
        installs (int): The parsed install count for the application.
        rating (float): The average star rating on a five-point scale.
        ratings_count (int): The number of ratings used to estimate confidence
            in the average score.

    Returns:
        float: A rounded novelty score where larger values indicate more
        unusual and promising results. Inputs are clamped, so unexpected or
        missing metadata yields a low score instead of raising.

    Examples:
        >>> novelty_score("Puzzle", 10000, 4.7, 1200) > 0
        True
        >>> novelty_score("Unknown", 10000, 4.7, 1200) <= novelty_score("Puzzle", 10000, 4.7, 1200)
        True
    """
    genre_bonus = _NICHE_GENRE_BONUS if genre in NICHE_GENRES else 1.0

    installs_component = 1.0 / (1.0 + max(_as_int(installs), 0) / _INSTALLS_HALFLIFE)

    raw_rating = max(0.3, min(1.0, _as_float(rating) / 5.0))
    confidence = min(1.0, math.log1p(max(_as_int(ratings_count), 0)) / _RATINGS_CONFIDENCE_CAP)
    rating_component = raw_rating * confidence + _UNCONFIRMED_RATING_FLOOR * (1.0 - confidence)

    return round(genre_bonus * installs_component * rating_component, 4)


def sort_apps(apps: list[dict], reverse: bool = True) -> list[dict]:
    """Annotate and sort application rows by novelty score.

    Args:
        apps (list[dict]): Application result rows containing the private
            metadata fields required for novelty calculation.
        reverse (bool, optional): Whether to sort from highest novelty score to
            lowest. Defaults to ``True``.

    Returns:
        list[dict]: A new list of application rows, each annotated with its
        ``COL_NOVELTY`` value and ordered by it.

    Examples:
        >>> rows = [{KEY_GENRE: "Puzzle", KEY_INSTALLS_INT: 1000, KEY_SCORE: 4.8, COL_REVIEWS: 12}]
        >>> sort_apps(rows)[0][COL_NOVELTY] > 0
        True
    """
    for row in apps:
        row[COL_NOVELTY] = novelty_score(
            row.get(KEY_GENRE) or "Unknown",
            row.get(KEY_INSTALLS_INT) or 0,
            # Use the raw float when available; the display column is rounded to
            # one decimal, which would otherwise degrade ranking precision.
            row.get(KEY_SCORE, row.get(COL_RATING, 0.0)),
            row.get(COL_REVIEWS) or 0,
        )
    return sorted(apps, key=lambda row: row[COL_NOVELTY], reverse=reverse)


def _as_int(value) -> int:
    """Coerce an arbitrary metadata value into an integer.

    Args:
        value (Any): The value to convert.

    Returns:
        int: The converted integer, or ``0`` when conversion is impossible.

    Examples:
        >>> _as_int("12")
        12
        >>> _as_int(None)
        0
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_float(value) -> float:
    """Coerce an arbitrary metadata value into a float.

    Args:
        value (Any): The value to convert.

    Returns:
        float: The converted float, or ``0.0`` when conversion is impossible.

    Examples:
        >>> _as_float("4.8")
        4.8
        >>> _as_float("n/a")
        0.0
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
