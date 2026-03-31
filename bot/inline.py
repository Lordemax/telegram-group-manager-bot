"""Inline query handler — lets users query bot info from any chat."""
import logging

from telegram import InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.ext import ContextTypes

from bot.database import get_bad_words, get_group_config

logger = logging.getLogger(__name__)

_HELP_TEXT = """
<b>Telegram Group Manager Bot</b>

<b>Moderation:</b>
/ban [reason] · /unban · /kick · /mute [duration] · /unmute
/warn [reason] · /warnings · /clearwarnings
/pin · /unpin · /promote · /demote

<b>Config (admins only):</b>
/setwelcome &lt;msg&gt; · /setfarewell &lt;msg&gt;
/setrules &lt;text&gt; · /addfilter &lt;word&gt; · /removefilter &lt;word&gt;
/listfilters · /setflood &lt;n&gt; · /antispam on|off · /captcha on|off

<b>User commands:</b>
/rules · /info [@user] · /help

<b>Inline usage:</b>
@botusername help — show this help
@botusername rules — show group rules
"""


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    if not query:
        return

    text = (query.query or "").strip().lower()
    results = []

    if not text or text == "help":
        results.append(
            InlineQueryResultArticle(
                id="help",
                title="Bot Help",
                description="Show all available commands",
                input_message_content=InputTextMessageContent(
                    _HELP_TEXT,
                    parse_mode="HTML",
                ),
                thumbnail_url="https://telegram.org/img/t_logo.png",
            )
        )

    if not text or text == "commands":
        commands_text = (
            "<b>Commands Quick Reference</b>\n\n"
            "/ban /unban /kick /mute /unmute\n"
            "/warn /warnings /clearwarnings\n"
            "/pin /unpin /promote /demote\n"
            "/setwelcome /setfarewell /setrules\n"
            "/addfilter /removefilter /listfilters\n"
            "/setflood /antispam /captcha\n"
            "/rules /info /help"
        )
        results.append(
            InlineQueryResultArticle(
                id="commands",
                title="Command List",
                description="All available bot commands",
                input_message_content=InputTextMessageContent(
                    commands_text, parse_mode="HTML"
                ),
            )
        )

    if not text or text == "about":
        about_text = (
            "<b>Group Manager Bot</b>\n\n"
            "A powerful Telegram group administration bot with:\n"
            "• Moderation (ban, kick, mute, warn)\n"
            "• Anti-spam &amp; flood control\n"
            "• Bad-word filter\n"
            "• Welcome &amp; farewell messages\n"
            "• CAPTCHA verification\n"
            "• Per-group configuration\n"
            "• Inline queries\n"
            "• Multi-language support (EN/ES)"
        )
        results.append(
            InlineQueryResultArticle(
                id="about",
                title="About this bot",
                description="Features and capabilities",
                input_message_content=InputTextMessageContent(
                    about_text, parse_mode="HTML"
                ),
            )
        )

    try:
        await query.answer(results, cache_time=30, is_personal=False)
    except Exception as e:
        logger.warning("Inline query answer failed: %s", e)
