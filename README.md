# Telegram Group Management Bot

A full-featured Telegram group management bot built with **python-telegram-bot v21** (async).

## Features

### Admin Commands (group admins only)
| Command | Description |
|---|---|
| `/ban @user [reason]` | Permanently ban a user |
| `/unban @user` | Unban a user |
| `/kick @user` | Kick a user (ban + immediate unban) |
| `/mute @user [duration]` | Mute a user. Duration: `10m`, `2h`, `1d` |
| `/unmute @user` | Unmute a user |
| `/warn @user [reason]` | Issue a warning (auto-bans at limit) |
| `/warnings [@user]` | Show warning count |
| `/clearwarnings @user` | Reset warnings |
| `/pin` | Pin the replied-to message |
| `/unpin` | Unpin current message |
| `/promote @user` | Make user an admin |
| `/demote @user` | Remove admin rights |

### User Commands (everyone)
| Command | Description |
|---|---|
| `/start` | Introduction |
| `/help` | Full command list |
| `/rules` | Show group rules |
| `/info [@user]` | Show user info & warnings |

### Config Commands (admins)
| Command | Description |
|---|---|
| `/setwelcome <msg>` | Set custom welcome message |
| `/setfarewell <msg>` | Set custom farewell message |
| `/setrules <text>` | Set group rules |
| `/addfilter <word>` | Add word to bad-word filter |
| `/removefilter <word>` | Remove word from filter |
| `/listfilters` | List filtered words |
| `/setflood <n>` | Set flood limit (messages per 5s) |
| `/antispam on\|off` | Toggle anti-spam module |
| `/captcha on\|off` | Toggle join CAPTCHA |

### Automated Features
- **Welcome/farewell messages** with `{first_name}`, `{username}`, `{group_name}` placeholders
- **Anti-spam / flood detection** — auto-mutes + warns heavy spammers
- **Bad-word filter** — deletes messages and warns users
- **Join CAPTCHA** — inline button challenge, auto-kicks if not clicked within 60s
- **Auto-ban** when warning threshold is reached (default 3)

---

## Setup

### 1. Create a bot on Telegram
1. Open [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the **Bot Token** you receive

### 2. Add the token as a secret
In Replit, go to **Secrets** (the lock icon) and add:
```
TELEGRAM_BOT_TOKEN = <your token here>
```

### 3. Start the bot
Click **Run** in Replit. The workflow `Telegram Bot` will execute `python run.py`.

### 4. Add the bot to your group
1. Add the bot to your Telegram group
2. Grant it **Admin** rights (at minimum: delete messages, ban users, restrict members, pin messages)
3. The bot will start responding to commands immediately

---

## Data Storage
All data (warnings, config, bad-word lists) is stored in a local SQLite database file `bot_data.db` in the project directory. No external database required.

## Architecture
```
artifacts/telegram-bot/
├── run.py              # Entry point
├── requirements.txt    # Python dependencies
├── bot/
│   ├── config.py       # Config & env vars
│   ├── database.py     # SQLite helpers (aiosqlite)
│   ├── helpers.py      # Permission checks, arg parsing
│   ├── main.py         # Application setup & handler registration
│   ├── moderation.py   # Admin moderation commands
│   ├── user_commands.py # Public user commands
│   ├── welcome.py      # Welcome/farewell & CAPTCHA
│   ├── antispam.py     # Flood control & bad-word filter
│   └── config_commands.py # Per-group config commands
```
