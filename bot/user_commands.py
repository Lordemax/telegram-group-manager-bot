"""Public user commands: /start, /help, /rules, /info."""
from telegram import Update
from telegram.ext import ContextTypes

from bot.database import (
    get_group_config,
    get_warnings,
    get_user_first_seen,
    track_user,
)
from bot.helpers import resolve_target_user


HELP_TEXT = """
<b>📋 Available Commands</b>

<b>Everyone:</b>
/start — Introduction
/help — This help message
/rules — Show group rules
/info [@user] — Show user info

<b>Admins only:</b>
/ban [@user] [reason] — Ban a user
/unban [@user] — Unban a user
/kick [@user] — Kick a user
/mute [@user] [duration] — Mute a user (e.g. 10m, 2h, 1d)
/unmute [@user] — Unmute a user
/warn [@user] [reason] — Warn a user
/warnings [@user] — Show warnings
/clearwarnings [@user] — Clear warnings
/pin — Pin replied message
/unpin — Unpin current message
/promote [@user] — Make user an admin
/demote [@user] — Remove admin rights

<b>Group configuration (admins):</b>
/setwelcome [message] — Set welcome message
/setfarewell [message] — Set farewell message
/setrules [text] — Set group rules
/addfilter [word] — Add a word to the bad-word filter
/removefilter [word] — Remove a word from the filter
/setflood [count] — Set flood threshold (messages per 5s)
/antispam on|off — Toggle anti-spam
/captcha on|off — Toggle join CAPTCHA

<b>Placeholders for welcome/farewell:</b>
{first_name}, {username}, {group_name}
"""


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        "👋 <b>Hello! I'm a full-featured group management bot.</b>\n\n"
        "Add me to a group, make me an admin, and I'll help you keep things organised.\n\n"
        "Use /help to see all available commands."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(HELP_TEXT)


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = await get_group_config(update.effective_chat.id)
    rules = cfg.get("rules", "No rules have been set yet.")
    await update.message.reply_html(f"📜 <b>Group Rules:</b>\n\n{rules}")


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    user_id, _ = await resolve_target_user(update, context)
    if not user_id:
        user_id = update.effective_user.id

    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        user = chat_member.user
    except Exception:
        await update.message.reply_text("Could not fetch user info.")
        return

    await track_user(chat_id, user.id)
    first_seen = await get_user_first_seen(chat_id, user.id)
    warns = await get_warnings(chat_id, user.id)

    name = user.full_name or "Unknown"
    username = f"@{user.username}" if user.username else "No username"
    status = chat_member.status

    text = (
        f"👤 <b>User Info</b>\n"
        f"<b>Name:</b> {name}\n"
        f"<b>Username:</b> {username}\n"
        f"<b>ID:</b> <code>{user.id}</code>\n"
        f"<b>Status:</b> {status}\n"
        f"<b>Warnings:</b> {len(warns)}\n"
        f"<b>First seen:</b> {first_seen[:10] if first_seen else 'Unknown'}"
    )
    await update.message.reply_html(text)
