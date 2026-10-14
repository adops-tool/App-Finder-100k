"""Central configuration: storage paths, tunables and keyword pools.

Every magic number that more than one module needs lives here so behaviour can
be tuned from a single place instead of being duplicated across the pipeline.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
# Resolve paths relative to this file so the database location never depends on
# the working directory Streamlit happened to be launched from.
BASE_DIR = Path(__file__).resolve().parent

DB_PATH = str(BASE_DIR / "seen_apps.db")

# Seconds SQLite waits for a locked database before raising. Detail rows are
# cached from a thread pool, so writers must tolerate each other.
DB_BUSY_TIMEOUT = 15.0

# ---------------------------------------------------------------------------
# Search strategy
# ---------------------------------------------------------------------------
SEARCH_LOCALES: tuple[tuple[str, str], ...] = (
    ("ru", "ru"),
    ("en", "us"),
    ("en", "gb"),
    ("de", "de"),
    ("fr", "fr"),
    ("uk", "ua"),
    ("pl", "pl"),
    ("tr", "tr"),
)

# How many locales a single run samples from the pool above.
MAX_LOCALES_PER_RUN = 4

GAME_KEYWORDS: tuple[str, ...] = (
    "action", "adventure", "arcade", "puzzle", "racing",
    "role playing", "simulation", "sports", "strategy", "trivia",
    "word", "horror", "survival", "shooter", "tower defense",
    "roguelike", "dungeon", "visual novel", "platformer", "escape room",
    "chess", "mahjong", "card game", "board game", "fighting",
    "idle game", "clicker", "match 3", "runner", "driving",
    "open world", "crafting", "building", "farming", "city builder",
    "quiz", "crossword", "sudoku", "solitaire", "slots",
    "music game", "rhythm", "dance", "karaoke",
)

NICHE_KEYWORDS: tuple[str, ...] = (
    "turn based tactics", "soulslike", "deckbuilder", "tactical rpg",
    "incremental game", "metroidvania", "immersive sim",
    "survival horror indie", "point and click adventure", "narrative puzzle",
    "asymmetric multiplayer", "hidden gems", "minimalist puzzle",
    "retro pixel rpg", "party game local", "walking simulator",
    "interactive fiction", "text adventure", "rogue lite",
    "auto battler", "autochess", "moba", "battle royale",
    "extraction shooter", "base building", "colony sim",
    "4x strategy", "grand strategy", "wargame", "hex tactics",
)

UTILITY_KEYWORDS: tuple[str, ...] = (
    "productivity", "notes", "todo list", "habit tracker",
    "meditation", "sleep sounds", "focus timer", "pomodoro",
    "language learning", "flashcards", "drawing", "pixel art editor",
    "music maker", "beat maker", "dj app", "guitar tuner",
    "astronomy", "star map", "weather", "fitness tracker",
    "workout", "yoga", "running tracker", "cycling",
    "recipe", "cooking", "nutrition", "calorie counter",
    "finance tracker", "budget", "expense tracker",
    "photo editor", "video editor", "collage maker",
    "barcode scanner", "qr code", "file manager", "calculator",
)

# Duplicates are intentional: they weight the sampling towards less saturated
# niches. The tuple keeps the pool immutable at runtime.
ALL_KEYWORDS: tuple[str, ...] = NICHE_KEYWORDS * 3 + GAME_KEYWORDS * 2 + UTILITY_KEYWORDS

NICHE_GENRES: frozenset[str] = frozenset({
    "Word", "Trivia", "Music", "Board", "Card", "Educational",
    "Adventure", "Simulation", "Strategy", "Role Playing",
    "Puzzle", "Racing", "Sports", "Casual",
})

# ---------------------------------------------------------------------------
# Default run parameters
# ---------------------------------------------------------------------------
DEFAULT_MIN_INSTALLS = 10_000
DEFAULT_MAX_INSTALLS = 0
DEFAULT_RESULTS_LIMIT = 30
DEFAULT_SEARCH_DEPTH = 140
DEFAULT_QUERIES_PER_RUN = 6

# Concurrency limits. Search and detail lookups are tuned separately because
# search responses are much heavier on the upstream API.
DEFAULT_WORKERS = 20
DEFAULT_SEARCH_WORKERS = 8

# Candidate apps inspected per requested result. Oversampling gives the novelty
# ranking a meaningful pool to sort instead of ranking whatever arrives first.
DETAILS_OVERSAMPLE = 8

# ---------------------------------------------------------------------------
# Sidebar widget bounds
# ---------------------------------------------------------------------------
RESULTS_LIMIT_RANGE: tuple[int, int] = (1, 200)
SEARCH_DEPTH_RANGE: tuple[int, int] = (30, 400)
QUERIES_PER_RUN_RANGE: tuple[int, int] = (2, 20)
MIN_INSTALLS_STEP = 10_000
MAX_INSTALLS_STEP = 100_000

# ---------------------------------------------------------------------------
# Result table contract
# ---------------------------------------------------------------------------
# Canonical column names shared by the scraper (writer), scoring (annotator)
# and the UI (renderer). Keeping them in one place stops a typo from silently
# dropping a column from the grid or the CSV export.
COL_TITLE = "Название"
COL_INSTALLS = "Скачивания"
COL_RATING = "Рейтинг"
COL_GENRE = "Жанр"
COL_REVIEWS = "Отзывы"
COL_UPDATED = "Обновлено"
COL_ADS = "Реклама"
COL_IAP = "Донат"
COL_ICON = "Иконка"
COL_LINK = "Ссылка"
COL_NOVELTY = "Неочевидность"

# Internal fields used for filtering and sorting; never displayed or exported.
KEY_INSTALLS_INT = "_installs_int"
KEY_SCORE = "_score"
KEY_GENRE = "_genre"

# Column order for the on-screen grid. Columns absent from a run (for example
# the novelty score when sorting is disabled) are skipped by the renderer.
DISPLAY_COLUMNS: tuple[str, ...] = (
    COL_TITLE, COL_INSTALLS, COL_RATING, COL_GENRE, COL_REVIEWS,
    COL_ADS, COL_IAP, COL_UPDATED, COL_NOVELTY, COL_LINK,
)

# ---------------------------------------------------------------------------
# Cache TTLs (seconds)
# ---------------------------------------------------------------------------
CACHE_TTL_SEARCH = 60 * 60 * 6
CACHE_TTL_DETAILS = 60 * 60 * 12
