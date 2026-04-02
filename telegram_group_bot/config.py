from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


DEFAULT_WELCOME = "Welcome, {user}, to {group}!"
DEFAULT_FAREWELL = "Goodbye, {user}."
DEFAULT_RULES = "Be respectful. No spam. Follow Telegram's terms."


@dataclass(slots=True)
class Settings:
    token: str
    data_dir: Path
    database_path: Path
    export_dir: Path
    timezone: ZoneInfo
    default_mute_minutes: int = 15
    spam_window_seconds: int = 10
    spam_mute_minutes: int = 10
    warn_limit: int = 3
    captcha_timeout_seconds: int = 60
    join_rate_window_seconds: int = 60
    summary_history_hours: int = 24
    log_level: str = "INFO"


def load_settings() -> Settings:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN environment variable.")

    root_dir = Path(__file__).resolve().parents[1]
    data_dir = Path(os.getenv("TELEGRAM_BOT_DATA_DIR", root_dir / "data")).resolve()
    database_path = Path(
        os.getenv("TELEGRAM_BOT_DB_PATH", data_dir / "telegram_group_bot.sqlite3")
    ).resolve()
    export_dir = Path(os.getenv("TELEGRAM_BOT_EXPORT_DIR", data_dir / "exports")).resolve()
    tz_name = os.getenv("TELEGRAM_BOT_TIMEZONE", "Africa/Lagos")

    data_dir.mkdir(parents=True, exist_ok=True)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        token=token,
        data_dir=data_dir,
        database_path=database_path,
        export_dir=export_dir,
        timezone=ZoneInfo(tz_name),
        default_mute_minutes=max(int(os.getenv("DEFAULT_MUTE_MINUTES", "15")), 1),
        spam_window_seconds=max(int(os.getenv("SPAM_WINDOW_SECONDS", "10")), 3),
        spam_mute_minutes=max(int(os.getenv("SPAM_MUTE_MINUTES", "10")), 1),
        warn_limit=max(int(os.getenv("WARN_LIMIT", "3")), 1),
        captcha_timeout_seconds=max(int(os.getenv("CAPTCHA_TIMEOUT_SECONDS", "60")), 10),
        join_rate_window_seconds=max(int(os.getenv("JOIN_RATE_WINDOW_SECONDS", "60")), 10),
        summary_history_hours=max(int(os.getenv("SUMMARY_HISTORY_HOURS", "24")), 1),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
