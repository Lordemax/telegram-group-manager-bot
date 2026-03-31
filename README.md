# Telegram Group Manager Bot

  A full-featured Telegram group management bot built with Python (python-telegram-bot v21) and an accompanying React admin dashboard.

  ## Features

  - **Moderation**: ban, unban, kick, mute, unmute, warn, warnings, clearwarnings, pin, unpin, promote, demote
  - **Anti-spam**: flood detection with auto-mute, configurable bad-word filter
  - **Welcome/Farewell**: customizable messages with placeholders, CAPTCHA verification (60s auto-kick)
  - **Per-group config**: welcome/farewell templates, rules, warn limit, flood count, antispam toggle, CAPTCHA toggle
  - **Inline queries**: search for help, commands, and bot info from any chat
  - **Multi-language**: English and Spanish (i18n module)
  - **Admin Dashboard**: React web UI to view and configure groups, warnings, and bad-word filters

  ## Stack

  - **Bot**: Python 3.11, python-telegram-bot v21 (async, long-polling), aiosqlite
  - **Dashboard**: React 19 + Vite + TanStack Query + Tailwind CSS + Wouter
  - **API**: Express 5 (TypeScript) serving `/api/bot/*` — reads bot's SQLite DB via better-sqlite3
  - **Storage**: SQLite (`bot_data.db`) for group config, warnings, bad words, user info

  ## Setup

  1. Create a bot via [@BotFather](https://t.me/BotFather) and get a token
  2. Set `TELEGRAM_BOT_TOKEN` as an environment secret
  3. Run: `cd artifacts/telegram-bot && python run.py`

  ## Bot Commands

  | Command | Description |
  |---|---|
  | `/ban` | Ban a user |
  | `/kick` | Kick a user |
  | `/mute [duration]` | Mute (e.g. `10m`, `1h`, `2d`) |
  | `/warn [reason]` | Issue a warning |
  | `/warnings` | View warnings |
  | `/clearwarnings` | Clear warnings |
  | `/setwelcome` | Set welcome message |
  | `/setrules` | Set group rules |
  | `/antispam on|off` | Toggle anti-spam |
  | `/captcha on|off` | Toggle CAPTCHA |

  ## License

  MIT
  