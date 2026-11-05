import math

from config import COL_NOVELTY, COL_RATING, COL_REVIEWS, KEY_INSTALLS_INT
from scoring import novelty_score, sort_apps


def test_novelty_rewards_confirmed_quality_and_niche_genres():
    niche = novelty_score("Puzzle", 10_000, 4.8, 2_000)
    mainstream = novelty_score("Unknown", 10_000, 4.8, 2_000)
    popular = novelty_score("Puzzle", 2_000_000, 4.8, 2_000)

    assert niche > mainstream
    assert niche > popular
    assert 0 < niche <= 1.4


def test_novelty_handles_invalid_numeric_metadata():
    assert math.isfinite(novelty_score("Puzzle", "invalid", math.nan, math.inf))
    assert novelty_score("Puzzle", -100, -5, -20) >= 0


def test_sort_apps_returns_annotated_copy():
    rows = [
        {
            COL_RATING: "4.8",
            COL_REVIEWS: 1_000,
            KEY_INSTALLS_INT: 10_000,
            "_genre": "Puzzle",
        }
    ]

    result = sort_apps(rows)

    assert result[0][COL_NOVELTY] > 0
    assert COL_NOVELTY not in rows[0]
