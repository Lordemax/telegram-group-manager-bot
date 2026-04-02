# Telegram Group Management Bot

Standalone Telegram group admin bot built with `python-telegram-bot` v21 and SQLite via `aiosqlite`.

## Features

- Admin moderation: `/kick`, `/ban`, `/unban`, `/mute`, `/unmute`, `/warn`, `/warnings`, `/clearwarnings`, `/pin`, `/unpin`, `/promote`, `/demote`
- User commands: `/start`, `/help`, `/rules`, `/info`
- Automated moderation: welcome/farewell messages, flood-spam detection, bad-word filtering, service message cleanup, CAPTCHA onboarding, join-rate alerts
- Join gating: require new members to join listed channels before they can speak in the group
- Screening: first-message delay for new joins, duplicate-message detection, and `/screening on|off`
- Monitoring and maintenance: `/modlog`, `/summary`, `/setsummaryhour`, `/health`, `/exportdata`, admin alert routing, raid mode, and link/domain controls
- Group configuration: `/setwelcome`, `/setfarewell`, `/setrules`, `/addfilter`, `/removefilter`, `/setflood`, `/antispam on|off`, `/captcha on|off`, `/raid on|off`, `/screening on|off`, `/setfirstmessagedelay`, `/setduplicatethreshold`, `/setduplicatewindow`, `/links on|off`, `/allowdomain`, `/blockdomain`, `/removedomain`, `/addrequiredchannel`, `/removerequiredchannel`, `/requiredchannels`, `/setalertchat`
- Persistence with a local SQLite database in `artifacts/telegram-bot/data/`

## Setup

1. Create a bot with `@BotFather` and copy the token.
2. Copy `.env.example` to `.env`.
3. Set `TELEGRAM_BOT_TOKEN` in `.env`.
4. Install dependencies and run the bot:

```bash
cd artifacts/telegram-bot
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

## Notes

- `TELEGRAM_BOT_TOKEN` is required or startup will fail immediately.
- Moderation commands are restricted to Telegram group admins.
- Commands target users by reply, known `@username`, or numeric Telegram user ID.
- Warnings auto-ban after the configured limit, which defaults to `3`.
- CAPTCHA challenges expire after `60` seconds by default and remove unverified users.
- `/setsummaryhour 9` schedules a daily summary at 09:00 in `TELEGRAM_BOT_TIMEZONE`.
- `/setalertchat` defaults to the current chat when no chat ID is supplied.
- Required channel checks work best with public channels such as `@channelname`, and the bot must be able to read membership for those channels.
- Screening mode uses the member's stored join time to enforce the first-message delay and audit log duplicate-message blocks.
