"""Anti-spam: flood detection and bad-word filter."""
import logging
import time
from collections import defaultdict

from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes

from bot.database import (
    get_group_config,
    get_bad_words,
    add_warning,
    get_group_config,
)
from bot.config import DEFAULT_FLOOD_WINDOW

logger = logging.getLogger(__name__)

SILENT_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)

flood_tracker: dict[tuple, list[float]] = defaultdict(list)


async def antispam_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Central handler for every group message.
    Runs flood detection + bad-word filter.
    """
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not msg or not user or not chat:
        return

    cfg = await get_group_config(chat.id)

    if cfg.get("antispam"):
        flooded = await _check_flood(update, context, cfg)
        if flooded:
            return

    if msg.text:
        await _check_bad_words(update, context, cfg)


async def _check_flood(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: dict) -> bool:
    """Return True if the user is flooding and action was taken."""
    user = update.effective_user
    chat = update.effective_chat
    key = (chat.id, user.id)
    now = time.monotonic()
    flood_count = cfg.get("flood_count", 5)
    window = DEFAULT_FLOOD_WINDOW

    timestamps = flood_tracker[key]
    timestamps.append(now)
    flood_tracker[key] = [t for t in timestamps if now - t <= window]

    if len(flood_tracker[key]) >= flood_count:
        flood_tracker[key] = []
        try:
            await update.effective_message.delete()
        except Exception:
            pass
        try:
            from datetime import datetime, timezone, timedelta
            until = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
            await context.bot.restrict_chat_member(
                chat.id, user.id, SILENT_PERMISSIONS, until_date=until
            )
            count = await add_warning(chat.id, user.id, "Flood / spam detected")
            await context.bot.send_message(
                chat.id,
                f"⚠️ {user.mention_html()} has been muted for 5 minutes for flooding. "
                f"Warning {count} issued.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Flood action failed: %s", e)
        return True
    return False


async def _check_bad_words(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: dict):
    """Delete messages containing filtered words and warn the sender."""
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    text = (msg.text or "").lower()

    bad_words = await get_bad_words(chat.id)
    triggered = [w for w in bad_words if w in text]
    if not triggered:
        return

    try:
        await msg.delete()
    except Exception:
        pass

    try:
        count = await add_warning(chat.id, user.id, f"Used filtered word: {triggered[0]}")
        warn_limit = cfg.get("warn_limit", 3)
        await context.bot.send_message(
            chat.id,
            f"🚫 {user.mention_html()} — message removed for using a filtered word. "
            f"Warning {count}/{warn_limit}.",
            parse_mode="HTML",
        )
        if count >= warn_limit:
            await context.bot.ban_chat_member(chat.id, user.id)
            await context.bot.send_message(
                chat.id,
                f"🔨 {user.mention_html()} has been auto-banned for reaching {warn_limit} warnings.",
                parse_mode="HTML",
            )
    except Exception as e:
        logger.warning("Bad-word action failed: %s", e)
