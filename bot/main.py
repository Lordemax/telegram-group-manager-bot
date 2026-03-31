"""Bot application setup — registers all handlers."""
import logging

from telegram import Update, Chat
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

from bot.config import TELEGRAM_BOT_TOKEN
from bot.database import init_db, ensure_group, update_group_name
from bot.moderation import (
    ban_command,
    clearwarnings_command,
    demote_command,
    kick_command,
    mute_command,
    pin_command,
    promote_command,
    unban_command,
    unmute_command,
    unpin_command,
    warn_command,
    warnings_command,
)
from bot.user_commands import (
    help_command,
    info_command,
    rules_command,
    start_command,
)
from bot.welcome import (
    captcha_callback,
    left_member_handler,
    new_member_handler,
    service_msg_handler,
)
from bot.antispam import antispam_handler
from bot.inline import inline_query_handler
from bot.config_commands import (
    addfilter_command,
    antispam_command,
    captcha_command,
    listfilters_command,
    removefilter_command,
    setfarewell_command,
    setflood_command,
    setrules_command,
    setwelcome_command,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context):
    logger.error("Unhandled exception", exc_info=context.error)


async def post_init(application: Application):
    await init_db()
    logger.info("Database initialised.")


async def track_group_handler(update: Update, context):
    """Silently keep group name up to date whenever any group message arrives."""
    chat = update.effective_chat
    if chat and chat.type in (Chat.GROUP, Chat.SUPERGROUP):
        name = chat.title or ""
        await ensure_group(chat.id, group_name=name)
        if name:
            await update_group_name(chat.id, name)


def build_application() -> Application:
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    group_filter = filters.ChatType.GROUPS
    private_filter = filters.ChatType.PRIVATE

    # ── Group name tracker (highest priority, runs on every group message) ──
    app.add_handler(
        MessageHandler(group_filter, track_group_handler),
        group=-1,
    )

    # ── User commands ──────────────────────────────────────────────────────
    # /start and /help: allowed in all chats (show group-only info in private)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    # /rules: group only (makes no sense in private)
    app.add_handler(CommandHandler("rules", rules_command, filters=group_filter))
    # /info: all chats — behaviour differs based on chat type (see user_commands.py)
    app.add_handler(CommandHandler("info", info_command))

    # ── Moderation (groups + admins only) ─────────────────────────────────
    app.add_handler(CommandHandler("ban", ban_command, filters=group_filter))
    app.add_handler(CommandHandler("unban", unban_command, filters=group_filter))
    app.add_handler(CommandHandler("kick", kick_command, filters=group_filter))
    app.add_handler(CommandHandler("mute", mute_command, filters=group_filter))
    app.add_handler(CommandHandler("unmute", unmute_command, filters=group_filter))
    app.add_handler(CommandHandler("warn", warn_command, filters=group_filter))
    app.add_handler(CommandHandler("warnings", warnings_command, filters=group_filter))
    app.add_handler(CommandHandler("clearwarnings", clearwarnings_command, filters=group_filter))
    app.add_handler(CommandHandler("pin", pin_command, filters=group_filter))
    app.add_handler(CommandHandler("unpin", unpin_command, filters=group_filter))
    app.add_handler(CommandHandler("promote", promote_command, filters=group_filter))
    app.add_handler(CommandHandler("demote", demote_command, filters=group_filter))

    # ── Config commands (groups + admins only) ─────────────────────────────
    app.add_handler(CommandHandler("setwelcome", setwelcome_command, filters=group_filter))
    app.add_handler(CommandHandler("setfarewell", setfarewell_command, filters=group_filter))
    app.add_handler(CommandHandler("setrules", setrules_command, filters=group_filter))
    app.add_handler(CommandHandler("addfilter", addfilter_command, filters=group_filter))
    app.add_handler(CommandHandler("removefilter", removefilter_command, filters=group_filter))
    app.add_handler(CommandHandler("listfilters", listfilters_command, filters=group_filter))
    app.add_handler(CommandHandler("setflood", setflood_command, filters=group_filter))
    app.add_handler(CommandHandler("antispam", antispam_command, filters=group_filter))
    app.add_handler(CommandHandler("captcha", captcha_command, filters=group_filter))

    # ── Private chat: silently ignore any other commands ──────────────────
    async def private_unknown(update: Update, context):
        await update.message.reply_html(
            "ℹ️ I only work in groups. You can use /info to view your Telegram details, "
            "or /start for more information."
        )
    app.add_handler(
        MessageHandler(private_filter & filters.COMMAND, private_unknown)
    )

    # ── Member events ──────────────────────────────────────────────────────
    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & group_filter, new_member_handler)
    )
    app.add_handler(
        MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER & group_filter, left_member_handler)
    )

    # ── Auto-delete Telegram service messages ──────────────────────────────
    service_updates = (
        filters.StatusUpdate.PINNED_MESSAGE
        | filters.StatusUpdate.NEW_CHAT_TITLE
        | filters.StatusUpdate.NEW_CHAT_PHOTO
        | filters.StatusUpdate.DELETE_CHAT_PHOTO
        | filters.StatusUpdate.CONNECTED_WEBSITE
    )
    app.add_handler(
        MessageHandler(service_updates & group_filter, service_msg_handler)
    )

    # ── Anti-spam message handler (lowest priority) ────────────────────────
    app.add_handler(
        MessageHandler(
            filters.TEXT & group_filter & ~filters.COMMAND,
            antispam_handler,
        )
    )

    # ── CAPTCHA inline button ──────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(captcha_callback, pattern=r"^captcha:"))

    # ── Inline queries ─────────────────────────────────────────────────────
    app.add_handler(InlineQueryHandler(inline_query_handler))

    # ── Error handler ──────────────────────────────────────────────────────
    app.add_error_handler(error_handler)

    return app
