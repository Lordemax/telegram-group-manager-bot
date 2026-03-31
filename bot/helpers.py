"""
Shared helpers: permission checks, target-user resolution, duration parsing.

@username resolution strategy
------------------------------
The Telegram Bot API does NOT support resolving @usernames via getChatMember —
that endpoint requires a numeric user_id. The only reliable username resolution
available to bots is `getChat(@username)`, which returns a Chat object whose
`id` is the numeric user_id for private/user chats.

We therefore use `get_chat` for @username resolution. This works for public
Telegram usernames. If the user has no username or has made their account
private, callers should use reply-to-message or numeric user_id instead.
"""
import logging
import re
from telegram import Update, Chat, ChatMember
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return True if the command sender is a group admin or creator."""
    if update.effective_chat.type == Chat.PRIVATE:
        return True
    user = update.effective_user
    chat = update.effective_chat
    member = await context.bot.get_chat_member(chat.id, user.id)
    return member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER)


async def bot_is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return True if the bot itself is an admin in the group."""
    chat = update.effective_chat
    me = await context.bot.get_me()
    member = await context.bot.get_chat_member(chat.id, me.id)
    return member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER)


async def resolve_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Resolve the target user and return (user_id: int, mention_html: str) or (None, None).

    Resolution order:
    1. Reply to a message — use replied-to user's numeric ID directly (most reliable).
    2. Numeric user_id argument — use as-is.
    3. @username argument — call get_chat(@username) to get the numeric user_id.
       Note: works for public Telegram usernames only. Falls back gracefully.

    Always returns an int user_id so Telegram Bot API calls succeed.
    """
    msg = update.effective_message

    if msg.reply_to_message and msg.reply_to_message.from_user:
        target = msg.reply_to_message.from_user
        return target.id, target.mention_html()

    args = msg.text.split()[1:] if msg.text else []
    if not args:
        return None, None

    token = args[0]

    if not token.startswith("@"):
        try:
            uid = int(token)
            return uid, f"<code>{uid}</code>"
        except ValueError:
            return None, None

    username = token.lstrip("@")
    try:
        chat_info = await context.bot.get_chat(f"@{username}")
        uid = chat_info.id
        return uid, f"<a href='tg://user?id={uid}'>@{username}</a>"
    except Exception as e:
        logger.warning("Could not resolve @%s via get_chat: %s", username, e)

    return None, None


def parse_duration(text: str) -> int | None:
    """
    Parse a duration string like '10m', '2h', '1d' into seconds.
    Returns None if unparseable.
    """
    match = re.fullmatch(r"(\d+)([smhd]?)", text.strip().lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2) or "s"
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return value * multipliers[unit]


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Send error and return False if user is not admin."""
    if not await is_admin(update, context):
        await update.effective_message.reply_text(
            "This command is restricted to group admins."
        )
        return False
    return True


async def require_bot_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Send error and return False if bot is not admin."""
    if not await bot_is_admin(update, context):
        await update.effective_message.reply_text(
            "I need to be an admin to perform this action."
        )
        return False
    return True
