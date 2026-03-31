"""Admin moderation commands: ban, unban, kick, mute, unmute, pin, unpin, promote, demote."""
import logging
from datetime import datetime, timezone, timedelta

from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes

from bot.database import add_warning, clear_warnings, get_group_config
from bot.helpers import (
    resolve_target_user,
    parse_duration,
    format_duration,
    require_admin,
    require_bot_admin,
)

logger = logging.getLogger(__name__)


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not await require_bot_admin(update, context):
        return

    user_id, mention = await resolve_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a message or provide @username / user_id.")
        return

    args = update.message.text.split()[1:]
    reason = " ".join(args[1:]) if len(args) > 1 else "No reason provided."

    try:
        await context.bot.ban_chat_member(update.effective_chat.id, user_id)
        await update.message.reply_html(
            f"🔨 Banned {mention}.\n<b>Reason:</b> {reason}"
        )
    except Exception as e:
        await update.message.reply_text(f"Failed to ban: {e}")


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not await require_bot_admin(update, context):
        return

    user_id, mention = await resolve_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a message or provide @username / user_id.")
        return

    try:
        await context.bot.unban_chat_member(
            update.effective_chat.id, user_id, only_if_banned=True
        )
        await update.message.reply_html(f"✅ Unbanned {mention}.")
    except Exception as e:
        await update.message.reply_text(f"Failed to unban: {e}")


async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not await require_bot_admin(update, context):
        return

    user_id, mention = await resolve_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a message or provide @username / user_id.")
        return

    try:
        chat_id = update.effective_chat.id
        await context.bot.ban_chat_member(chat_id, user_id)
        await context.bot.unban_chat_member(chat_id, user_id)
        await update.message.reply_html(f"👢 Kicked {mention}.")
    except Exception as e:
        await update.message.reply_text(f"Failed to kick: {e}")


async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not await require_bot_admin(update, context):
        return

    user_id, mention = await resolve_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a message or provide @username / user_id.")
        return

    args = update.message.text.split()[1:]
    if update.message.reply_to_message:
        duration_str = args[0] if args else None
    else:
        duration_str = args[1] if len(args) > 1 else None
    duration_sec = parse_duration(duration_str) if duration_str else None

    until_date = None
    if duration_sec:
        until_date = datetime.now(tz=timezone.utc) + timedelta(seconds=duration_sec)

    silent_permissions = ChatPermissions(
        can_send_messages=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
    )

    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            user_id,
            silent_permissions,
            until_date=until_date,
        )
        duration_text = (
            f" for {format_duration(duration_sec)}" if duration_sec else " indefinitely"
        )
        await update.message.reply_html(f"🔇 Muted {mention}{duration_text}.")
    except Exception as e:
        await update.message.reply_text(f"Failed to mute: {e}")


async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not await require_bot_admin(update, context):
        return

    user_id, mention = await resolve_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a message or provide @username / user_id.")
        return

    full_permissions = ChatPermissions(
        can_send_messages=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_change_info=False,
        can_invite_users=True,
        can_pin_messages=False,
    )

    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id, user_id, full_permissions
        )
        await update.message.reply_html(f"🔊 Unmuted {mention}.")
    except Exception as e:
        await update.message.reply_text(f"Failed to unmute: {e}")


async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return

    user_id, mention = await resolve_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a message or provide @username / user_id.")
        return

    args = update.message.text.split()[1:]
    reason = " ".join(args[1:]) if len(args) > 1 else "No reason provided."
    chat_id = update.effective_chat.id

    cfg = await get_group_config(chat_id)
    warn_limit = cfg.get("warn_limit", 3)

    count = await add_warning(chat_id, user_id, reason)
    await update.message.reply_html(
        f"⚠️ Warned {mention}.\n"
        f"<b>Reason:</b> {reason}\n"
        f"<b>Warnings:</b> {count}/{warn_limit}"
    )

    if count >= warn_limit:
        try:
            await context.bot.ban_chat_member(chat_id, user_id)
            await update.message.reply_html(
                f"🔨 {mention} has been <b>auto-banned</b> for reaching {warn_limit} warnings."
            )
        except Exception as e:
            await update.message.reply_text(f"Auto-ban failed: {e}")


async def warnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return

    user_id, mention = await resolve_target_user(update, context)
    if not user_id:
        if update.effective_user:
            user_id = update.effective_user.id
            mention = update.effective_user.mention_html()
        else:
            await update.message.reply_text("Specify a user.")
            return

    chat_id = update.effective_chat.id
    from bot.database import get_warnings
    warns = await get_warnings(chat_id, user_id)
    cfg = await get_group_config(chat_id)
    warn_limit = cfg.get("warn_limit", 3)

    if not warns:
        await update.message.reply_html(f"{mention} has no warnings.")
        return

    lines = [f"⚠️ Warnings for {mention} ({len(warns)}/{warn_limit}):"]
    for i, w in enumerate(warns, 1):
        reason = w.get("reason") or "No reason"
        created = w.get("created_at", "")[:10]
        lines.append(f"{i}. {reason} — {created}")
    await update.message.reply_html("\n".join(lines))


async def clearwarnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return

    user_id, mention = await resolve_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a message or provide @username / user_id.")
        return

    await clear_warnings(update.effective_chat.id, user_id)
    await update.message.reply_html(f"✅ Cleared all warnings for {mention}.")


async def pin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not await require_bot_admin(update, context):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to the message you want to pin.")
        return
    try:
        await context.bot.pin_chat_message(
            update.effective_chat.id,
            update.message.reply_to_message.message_id,
            disable_notification=False,
        )
        await update.message.reply_text("📌 Message pinned.")
    except Exception as e:
        await update.message.reply_text(f"Failed to pin: {e}")


async def unpin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not await require_bot_admin(update, context):
        return
    try:
        await context.bot.unpin_chat_message(update.effective_chat.id)
        await update.message.reply_text("📌 Message unpinned.")
    except Exception as e:
        await update.message.reply_text(f"Failed to unpin: {e}")


async def promote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not await require_bot_admin(update, context):
        return

    user_id, mention = await resolve_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a message or provide @username / user_id.")
        return

    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id,
            user_id,
            can_delete_messages=True,
            can_restrict_members=True,
            can_pin_messages=True,
            can_invite_users=True,
            can_manage_chat=True,
            can_manage_video_chats=True,
        )
        await update.message.reply_html(f"⭐ Promoted {mention} to admin.")
    except Exception as e:
        await update.message.reply_text(f"Failed to promote: {e}")


async def demote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not await require_bot_admin(update, context):
        return

    user_id, mention = await resolve_target_user(update, context)
    if not user_id:
        await update.message.reply_text("Reply to a message or provide @username / user_id.")
        return

    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id,
            user_id,
            can_delete_messages=False,
            can_restrict_members=False,
            can_pin_messages=False,
            can_invite_users=False,
            can_manage_chat=False,
            can_manage_video_chats=False,
        )
        await update.message.reply_html(f"👤 Demoted {mention} from admin.")
    except Exception as e:
        await update.message.reply_text(f"Failed to demote: {e}")
