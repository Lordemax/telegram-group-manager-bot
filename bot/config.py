import os

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN environment variable is not set. "
        "Please add it in the Secrets / Environment Variables tab."
    )

import pathlib as _pathlib
_DEFAULT_DB = str(_pathlib.Path(__file__).parent.parent / "bot_data.db")
DB_PATH = os.environ.get("DB_PATH", _DEFAULT_DB)

DEFAULT_WARN_LIMIT = 3
DEFAULT_FLOOD_COUNT = 5
DEFAULT_FLOOD_WINDOW = 5
CAPTCHA_TIMEOUT = 60
