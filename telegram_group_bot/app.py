from __future__ import annotations

import logging

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from .config import load_settings
from .db import Database
from .handlers import BotHandlers


def build_application() -> Application:
    settings = load_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    database = Database(settings.database_path)
    handlers = BotHandlers(settings=settings, db=database)

    application = (
        ApplicationBuilder()
        .token(settings.token)
        .post_init(handlers.on_startup)
        .post_shutdown(handlers.on_shutdown)
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["db"] = database
    application.bot_data["runtime"] = handlers.runtime_state

    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help_command))
    application.add_handler(CommandHandler("rules", handlers.rules))
    application.add_handler(CommandHandler("info", handlers.info))
    application.add_handler(CommandHandler("modlog", handlers.modlog))
    application.add_handler(CommandHandler("summary", handlers.summary))
    application.add_handler(CommandHandler("setsummaryhour", handlers.set_summary_hour))
    application.add_handler(CommandHandler("health", handlers.health))
    application.add_handler(CommandHandler("exportdata", handlers.export_data))
    application.add_handler(CommandHandler("screening", handlers.toggle_screening))
    application.add_handler(CommandHandler("setfirstmessagedelay", handlers.set_first_message_delay))
    application.add_handler(CommandHandler("setduplicatethreshold", handlers.set_duplicate_threshold))
    application.add_handler(CommandHandler("setduplicatewindow", handlers.set_duplicate_window))

    application.add_handler(CommandHandler("kick", handlers.kick))
    application.add_handler(CommandHandler("ban", handlers.ban))
    application.add_handler(CommandHandler("unban", handlers.unban))
    application.add_handler(CommandHandler("mute", handlers.mute))
    application.add_handler(CommandHandler("unmute", handlers.unmute))
    application.add_handler(CommandHandler("warn", handlers.warn))
    application.add_handler(CommandHandler("warnings", handlers.warnings))
    application.add_handler(CommandHandler("clearwarnings", handlers.clear_warnings))
    application.add_handler(CommandHandler("pin", handlers.pin))
    application.add_handler(CommandHandler("unpin", handlers.unpin))
    application.add_handler(CommandHandler("promote", handlers.promote))
    application.add_handler(CommandHandler("demote", handlers.demote))

    application.add_handler(CommandHandler("setwelcome", handlers.set_welcome))
    application.add_handler(CommandHandler("setfarewell", handlers.set_farewell))
    application.add_handler(CommandHandler("setrules", handlers.set_rules))
    application.add_handler(CommandHandler("addfilter", handlers.add_filter))
    application.add_handler(CommandHandler("removefilter", handlers.remove_filter))
    application.add_handler(CommandHandler("setflood", handlers.set_flood))
    application.add_handler(CommandHandler("antispam", handlers.toggle_antispam))
    application.add_handler(CommandHandler("captcha", handlers.toggle_captcha))
    application.add_handler(CommandHandler("raid", handlers.toggle_raid))
    application.add_handler(CommandHandler("links", handlers.toggle_links))
    application.add_handler(CommandHandler("allowdomain", handlers.allow_domain))
    application.add_handler(CommandHandler("blockdomain", handlers.block_domain))
    application.add_handler(CommandHandler("removedomain", handlers.remove_domain))
    application.add_handler(CommandHandler("addrequiredchannel", handlers.add_required_channel))
    application.add_handler(CommandHandler("removerequiredchannel", handlers.remove_required_channel))
    application.add_handler(CommandHandler("requiredchannels", handlers.list_required_channels))
    application.add_handler(CommandHandler("setalertchat", handlers.set_alert_chat))

    application.add_handler(CallbackQueryHandler(handlers.captcha_callback, pattern=r"^captcha:"))
    application.add_handler(
        ChatMemberHandler(handlers.track_chat_member_update, ChatMemberHandler.CHAT_MEMBER)
    )
    application.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handlers.handle_new_members)
    )
    application.add_handler(
        MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handlers.handle_member_left)
    )
    application.add_handler(
        MessageHandler(filters.StatusUpdate.ALL, handlers.handle_service_message)
    )
    application.add_handler(
        MessageHandler(
            filters.ALL
            & ~filters.COMMAND
            & ~filters.StatusUpdate.ALL,
            handlers.handle_message,
        )
    )
    return application


def main() -> None:
    application = build_application()
    application.run_polling(allowed_updates=None)
