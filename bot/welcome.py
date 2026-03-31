"""Welcome, farewell, and new member tracking."""
import asyncio
import logging

from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.database import get_group_config, track_user
from bot.config import CAPTCHA_TIMEOUT

logger = logging.getLogger(__name__)

SILENT_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)

FULL_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_invite_users=True,
)


def _format_msg(template: str, user, chat) -> str:
    first_name = user.first_name or "Member"
    username = f"@{user.username}" if user.username else first_name
    group_name = chat.title or "this group"
    return (
        template
        .replace("{first_name}", first_name)
        .replace("{username}", username)
        .replace("{group_name}", group_name)
    )


async def new_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    cfg = await get_group_config(chat.id)

    for member in update.message.new_chat_members:
        if member.is_bot:
            continue

        await track_user(chat.id, member.id)

        if cfg.get("captcha"):
            await _start_captcha(update, context, member, chat, cfg)
        else:
            welcome_msg = cfg.get(
                "welcome_msg", "Welcome {first_name} to {group_name}!"
            )
            text = _format_msg(welcome_msg, member, chat)
            await update.message.reply_html(text)


async def _start_captcha(update, context, member, chat, cfg):
    """Restrict new member and send CAPTCHA inline keyboard."""
    try:
        await context.bot.restrict_chat_member(
            chat.id, member.id, SILENT_PERMISSIONS
        )
    except Exception:
        pass

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(
            "✅ I am human — click to join",
            callback_data=f"captcha:{member.id}"
        )]]
    )

    captcha_msg = await update.message.reply_html(
        f"👋 Welcome <b>{member.full_name}</b>!\n"
        f"Please click the button below within {CAPTCHA_TIMEOUT} seconds to verify you are human.",
        reply_markup=keyboard,
    )

    context.application.create_task(
        _captcha_timeout(context, chat.id, member.id, captcha_msg.message_id),
        update=update,
    )


async def _captcha_timeout(context: ContextTypes.DEFAULT_TYPE, chat_id, user_id, msg_id):
    await asyncio.sleep(CAPTCHA_TIMEOUT)
    if context.bot_data.get(f"captcha_done:{chat_id}:{user_id}"):
        return
    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        await context.bot.unban_chat_member(chat_id, user_id)
        await context.bot.delete_message(chat_id, msg_id)
        await context.bot.send_message(
            chat_id,
            f"User {user_id} was removed for not completing the CAPTCHA in time."
        )
    except Exception as e:
        logger.warning("CAPTCHA timeout action failed: %s", e)


async def captcha_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    if not data.startswith("captcha:"):
        return

    expected_user_id = int(data.split(":")[1])
    presser = query.from_user.id

    if presser != expected_user_id:
        await query.answer("This button is not for you!", show_alert=True)
        return

    chat_id = query.message.chat_id
    context.bot_data[f"captcha_done:{chat_id}:{expected_user_id}"] = True

    try:
        await context.bot.restrict_chat_member(
            chat_id, expected_user_id, FULL_PERMISSIONS
        )
        cfg = await get_group_config(chat_id)
        welcome_msg = cfg.get("welcome_msg", "Welcome {first_name} to {group_name}!")
        chat = query.message.chat
        user = query.from_user
        text = _format_msg(welcome_msg, user, chat)
        await query.message.edit_text(text, parse_mode="HTML")
        await query.answer("Welcome! You have been verified.")
    except Exception as e:
        logger.error("CAPTCHA grant failed: %s", e)
        await query.answer("Something went wrong. Please contact an admin.")


async def left_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    member = update.message.left_chat_member
    if not member or member.is_bot:
        return

    cfg = await get_group_config(chat.id)
    farewell_msg = cfg.get("farewell_msg", "Goodbye {first_name}!")
    text = _format_msg(farewell_msg, member, chat)
    await update.message.reply_html(text)


async def service_msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-delete Telegram service messages like 'X joined via invite link'."""
    try:
        await update.message.delete()
    except Exception:
        pass
