"""Public user commands: /start, /help, /info.

Rules:
- In groups: /info is available to all members (shows own info); admins can target others.
  /start and /help show a brief "add me to a group" prompt in private.
- In private chat: ONLY /info works for regular users, showing their OWN details.
  /start and /help reply with a pointer to add the bot to a group.
"""
from telegram import Update, Chat
from telegram.ext import ContextTypes

from bot.database import (
    get_group_config,
    get_warnings,
    get_user_first_seen,
    track_user,
)
from bot.helpers import is_admin, resolve_target_user


PRIVATE_INTRO = (
    "👋 <b>Group Manager Bot</b>\n\n"
    "I'm a group management bot — add me to a Telegram group and make me an admin "
    "to start managing it.\n\n"
    "<b>What I do in groups:</b>\n"
    "• Welcome and farewell messages\n"
    "• Anti-spam flood protection\n"
    "• Bad-word filtering\n"
    "• CAPTCHA verification for new members\n"
    "• Warn, mute, kick, ban moderation tools\n\n"
    "In this private chat, you can use /info to view your own Telegram details."
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == Chat.PRIVATE:
        await update.message.reply_html(PRIVATE_INTRO)
    else:
        await update.message.reply_html(
            "👋 Hello! I'm a group management bot. Use /help to see commands, "
            "or ask an admin for the group rules."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == Chat.PRIVATE:
        await update.message.reply_html(PRIVATE_INTRO)
        return

    admin = await is_admin(update, context)
    if admin:
        help_text = """
<b>📋 Group Manager Commands</b>

<b>Everyone:</b>
/info [@user] — Show your info (or another user's if you're an admin)
/rules — Show group rules

<b>Admins / Mods only:</b>
/ban [@user] [reason] — Ban a user
/unban [@user] — Unban a user
/kick [@user] — Kick a user
/mute [@user] [duration] — Mute (e.g. 10m, 2h, 1d)
/unmute [@user] — Unmute
/warn [@user] [reason] — Issue a warning
/warnings [@user] — Show warnings
/clearwarnings [@user] — Clear warnings
/pin — Pin replied message
/unpin — Unpin current message
/promote [@user] — Make admin
/demote [@user] — Remove admin rights

<b>Group config (admins):</b>
/setwelcome [message] — Set welcome message
/setfarewell [message] — Set farewell message
/setrules [text] — Set group rules
/addfilter [word] — Add to bad-word filter
/removefilter [word] — Remove from filter
/listfilters — List all filtered words
/setflood [count] — Set flood threshold
/antispam on|off — Toggle anti-spam
/captcha on|off — Toggle join CAPTCHA
"""
    else:
        help_text = (
            "<b>📋 Commands available to you</b>\n\n"
            "/info — View your profile info\n"
            "/rules — Show group rules\n"
        )
    await update.message.reply_html(help_text)


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = await get_group_config(update.effective_chat.id)
    rules = cfg.get("rules", "No rules have been set yet.")
    await update.message.reply_html(f"📜 <b>Group Rules:</b>\n\n{rules}")


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    sender = update.effective_user

    if chat.type == Chat.PRIVATE:
        # Private chat: only show the sender's own details
        text = (
            f"👤 <b>Your Info</b>\n"
            f"<b>Name:</b> {sender.full_name or 'Unknown'}\n"
            f"<b>Username:</b> {'@' + sender.username if sender.username else 'No username'}\n"
            f"<b>ID:</b> <code>{sender.id}</code>\n"
            f"<b>Language:</b> {sender.language_code or 'Unknown'}"
        )
        await update.message.reply_html(text)
        return

    # Group: admins can look up others; regular users see only themselves
    admin = await is_admin(update, context)
    if admin:
        user_id, _ = await resolve_target_user(update, context)
        if not user_id:
            user_id = sender.id
    else:
        user_id = sender.id

    try:
        chat_member = await context.bot.get_chat_member(chat.id, user_id)
        user = chat_member.user
    except Exception:
        await update.message.reply_text("Could not fetch user info.")
        return

    await track_user(chat.id, user.id)
    first_seen = await get_user_first_seen(chat.id, user.id)
    warns = await get_warnings(chat.id, user.id)

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
