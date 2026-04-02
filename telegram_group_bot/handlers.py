from __future__ import annotations

import html
import json
import logging
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlparse

from telegram import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update, User
from telegram.constants import ChatMemberStatus, ChatType, ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

from .config import Settings
from .db import Database, GroupSettings


LOGGER = logging.getLogger(__name__)
ADMIN_STATUSES = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}
LINK_RE = re.compile(r"https?://\S+|t\.me/\S+|www\.\S+", re.IGNORECASE)
DOMAIN_RE = re.compile(r"^(?:https?://)?(?:www\.)?([^/\s:]+)", re.IGNORECASE)
MUTED_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
)
DEFAULT_MEMBER_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_change_info=False,
    can_invite_users=True,
    can_pin_messages=False,
)


@dataclass(slots=True)
class RuntimeState:
    flood_events: dict[tuple[int, int], deque[datetime]] = field(default_factory=lambda: defaultdict(deque))
    join_events: dict[int, deque[datetime]] = field(default_factory=lambda: defaultdict(deque))
    recent_texts: dict[int, dict[str, deque[tuple[int, datetime]]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(deque))
    )
    startup_time: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class TargetUser:
    user_id: int
    display_name: str
    reason: str = ""


class BotHandlers:
    def __init__(self, *, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self.runtime_state = RuntimeState()
        self.application = None

    async def on_startup(self, app) -> None:
        self.application = app
        await self.db.initialize()
        if getattr(app, "job_queue", None):
            for captcha in await self.db.list_pending_captchas():
                expires_at = datetime.fromisoformat(captcha["expires_at"])
                delay = max(int((expires_at - datetime.now(UTC)).total_seconds()), 0)
                app.job_queue.run_once(
                    self.expire_captcha,
                    when=delay,
                    data={"chat_id": captcha["chat_id"], "user_id": captcha["user_id"]},
                    name=f"captcha:{captcha['chat_id']}:{captcha['user_id']}",
                )
            await self.refresh_summary_jobs(app)
        LOGGER.info("Telegram group bot is ready.")

    async def on_shutdown(self, _) -> None:
        LOGGER.info("Telegram group bot is shutting down.")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if not message:
            return
        await message.reply_text(
            "Group management bot is online. Use /help for commands and /health for runtime status."
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if not message:
            return
        await message.reply_text(
            "Admin commands:\n"
            "/kick /ban /unban /mute /unmute /warn /warnings /clearwarnings\n"
            "/pin /unpin /promote /demote\n"
            "/setwelcome /setfarewell /setrules /addfilter /removefilter /setflood\n"
            "/antispam on|off /captcha on|off /raid on|off /screening on|off\n"
            "/setfirstmessagedelay minutes /setduplicatethreshold count /setduplicatewindow seconds\n"
            "/links on|off /allowdomain domain /blockdomain domain /removedomain domain\n"
            "/addrequiredchannel @channel /removerequiredchannel @channel /requiredchannels\n"
            "/setalertchat [chat_id] /setsummaryhour hour|off /summary /modlog [count] /exportdata /health\n\n"
            "User commands:\n/start /help /rules /info"
        )

    async def rules(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        message = update.effective_message
        chat = update.effective_chat
        if not message or not chat:
            return
        settings = await self.db.get_group_settings(chat.id)
        await message.reply_text(settings.rules_text)

    async def info(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        if not message or not chat:
            return
        target = await self.resolve_target_user(update, context, allow_reason=False)
        if target is None:
            user = update.effective_user
            if user is None:
                return
            target = TargetUser(user.id, self.user_label(user))
        member = await self.db.get_member(chat.id, target.user_id)
        warns = await self.db.get_warning_count(chat.id, target.user_id)
        lines = [f"User: {target.display_name}", f"User ID: {target.user_id}", f"Warnings: {warns}"]
        if member and member.joined_at:
            lines.append(f"Joined: {member.joined_at}")
        await message.reply_text("\n".join(lines))

    async def modlog(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        limit = 10
        if context.args:
            try:
                limit = min(max(int(context.args[0]), 1), 25)
            except ValueError:
                await message.reply_text("Usage: /modlog [1-25]")
                return
        events = await self.db.get_modlog(chat.id, limit)
        if not events:
            await message.reply_text("No moderation events recorded yet.")
            return
        lines = []
        for event in events:
            actor = event.actor_name or "system"
            target = event.target_name or "-"
            reason = f" | {event.reason}" if event.reason else ""
            lines.append(f"{event.created_at} | {event.event_type} | {actor} -> {target}{reason}")
        await message.reply_text("\n".join(lines))

    async def summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        text = await self.build_summary(chat.id)
        await message.reply_text(text)

    async def set_summary_hour(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        if not context.args:
            await message.reply_text("Usage: /setsummaryhour hour|off")
            return
        arg = context.args[0].lower()
        if arg == "off":
            await self.db.update_group_setting(chat.id, "summary_enabled", 0)
            await self.db.update_group_setting(chat.id, "summary_hour", None)
            await self.refresh_summary_jobs(context.application)
            await self.log_event(chat.id, "summary_config", user, reason="disabled")
            await message.reply_text("Scheduled summaries disabled.")
            return
        try:
            hour = int(arg)
        except ValueError:
            await message.reply_text("Hour must be 0-23 or 'off'.")
            return
        if hour < 0 or hour > 23:
            await message.reply_text("Hour must be 0-23.")
            return
        await self.db.update_group_setting(chat.id, "summary_hour", hour)
        await self.db.update_group_setting(chat.id, "summary_enabled", 1)
        await self.refresh_summary_jobs(context.application)
        await self.log_event(chat.id, "summary_config", user, reason=f"hour={hour}")
        await message.reply_text(f"Daily summaries scheduled for {hour:02d}:00 {self.settings.timezone.key}.")

    async def health(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        settings = await self.db.get_group_settings(chat.id)
        uptime = datetime.now(UTC) - self.runtime_state.startup_time
        lines = [
            f"Uptime: {str(uptime).split('.')[0]}",
            f"DB: {self.settings.database_path}",
            f"Raid mode: {'on' if settings.raid_mode_enabled else 'off'}",
            f"Anti-spam: {'on' if settings.antispam_enabled else 'off'}",
            f"CAPTCHA: {'on' if settings.captcha_enabled else 'off'}",
            f"Screening: {'on' if settings.screening_enabled else 'off'}",
            f"Link filter: {'on' if settings.link_filter_enabled else 'off'}",
            f"First message delay: {settings.first_message_delay_seconds}s",
            f"Duplicate window: {settings.duplicate_message_window_seconds}s",
            f"Duplicate threshold: {settings.duplicate_message_threshold}",
            f"Alert chat: {settings.admin_alert_chat_id or 'not set'}",
            f"Summary hour: {settings.summary_hour if settings.summary_enabled else 'disabled'}",
        ]
        await message.reply_text("\n".join(lines))

    async def export_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        data = await self.db.export_group_state(chat.id)
        export_path = self.settings.export_dir / f"group-{chat.id}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
        export_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        with export_path.open("rb") as handle:
            await context.bot.send_document(chat.id, document=handle, filename=export_path.name)
        await self.log_event(chat.id, "export", user, reason=export_path.name)

    async def kick(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._moderate_simple(update, context, action="kick")

    async def ban(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._moderate_simple(update, context, action="ban")

    async def unban(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        target = await self.require_target_user(update, context)
        if target is None:
            return
        await context.bot.unban_chat_member(chat.id, target.user_id, only_if_banned=True)
        await self.log_event(chat.id, "unban", user, target=target)
        await message.reply_text(f"Unbanned {target.display_name}.")

    async def mute(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        target = await self.require_target_user(update, context)
        if target is None or not await self.can_act_on_target(message, chat.id, target.user_id):
            return
        duration_minutes = self.parse_duration_minutes(target.reason) or self.settings.default_mute_minutes
        until_date = datetime.now(UTC) + timedelta(minutes=duration_minutes)
        await context.bot.restrict_chat_member(chat.id, target.user_id, permissions=MUTED_PERMISSIONS, until_date=until_date)
        await self.log_event(chat.id, "mute", user, target=target, reason=f"{duration_minutes}m")
        await message.reply_text(f"Muted {target.display_name} for {duration_minutes} minute(s).")

    async def unmute(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        target = await self.require_target_user(update, context)
        if target is None:
            return
        await context.bot.restrict_chat_member(chat.id, target.user_id, permissions=DEFAULT_MEMBER_PERMISSIONS)
        await self.log_event(chat.id, "unmute", user, target=target)
        await message.reply_text(f"Unmuted {target.display_name}.")

    async def warn(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        target = await self.require_target_user(update, context)
        if target is None:
            return
        count = await self.issue_warning(context, chat.id, target.user_id, target.display_name, target.reason or "manual warn", actor=user)
        if count < self.settings.warn_limit:
            await message.reply_text(f"{target.display_name} now has {count}/{self.settings.warn_limit} warning(s).")

    async def warnings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        target = await self.require_target_user(update, context)
        if target is None:
            return
        count = await self.db.get_warning_count(chat.id, target.user_id)
        await message.reply_text(f"{target.display_name} has {count} warning(s).")

    async def clear_warnings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        target = await self.require_target_user(update, context)
        if target is None:
            return
        await self.db.clear_warnings(chat.id, target.user_id)
        await self.log_event(chat.id, "clearwarnings", user, target=target)
        await message.reply_text(f"Cleared warnings for {target.display_name}.")

    async def pin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        if not message.reply_to_message:
            await message.reply_text("Reply to the message you want to pin.")
            return
        await context.bot.pin_chat_message(chat.id, message.reply_to_message.message_id)
        await self.log_event(chat.id, "pin", user, reason=f"message_id={message.reply_to_message.message_id}")
        await message.reply_text("Pinned the replied-to message.")

    async def unpin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        await context.bot.unpin_all_chat_messages(chat.id)
        await self.log_event(chat.id, "unpin", user)
        await message.reply_text("Unpinned the current pinned message.")

    async def promote(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        target = await self.require_target_user(update, context)
        if target is None:
            return
        await context.bot.promote_chat_member(chat.id, target.user_id, can_manage_chat=True, can_delete_messages=True, can_manage_video_chats=False, can_restrict_members=True, can_promote_members=False, can_change_info=False, can_invite_users=True, can_post_stories=False, can_edit_stories=False, can_delete_stories=False, can_pin_messages=True, is_anonymous=False)
        await self.log_event(chat.id, "promote", user, target=target)
        await message.reply_text(f"Promoted {target.display_name}.")

    async def demote(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        target = await self.require_target_user(update, context)
        if target is None:
            return
        await context.bot.promote_chat_member(chat.id, target.user_id, can_manage_chat=False, can_delete_messages=False, can_manage_video_chats=False, can_restrict_members=False, can_promote_members=False, can_change_info=False, can_invite_users=False, can_post_stories=False, can_edit_stories=False, can_delete_stories=False, can_pin_messages=False, is_anonymous=False)
        await self.log_event(chat.id, "demote", user, target=target)
        await message.reply_text(f"Demoted {target.display_name}.")
    async def set_welcome(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_group_text_setting(update, context, "welcome_message", "/setwelcome [message]")

    async def set_farewell(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_group_text_setting(update, context, "farewell_message", "/setfarewell [message]")

    async def set_rules(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_group_text_setting(update, context, "rules_text", "/setrules [text]")

    async def add_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_bad_word(update, context, add=True)

    async def remove_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_bad_word(update, context, add=False)

    async def set_flood(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        if not context.args:
            await message.reply_text("Usage: /setflood [count]")
            return
        try:
            count = max(int(context.args[0]), 2)
        except ValueError:
            await message.reply_text("Flood threshold must be a number >= 2.")
            return
        await self.db.update_group_setting(chat.id, "flood_threshold", count)
        await self.log_event(chat.id, "setflood", user, reason=str(count))
        await message.reply_text(f"Flood threshold is now {count}.")

    async def toggle_antispam(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_group_toggle_setting(update, context, "antispam_enabled", "/antispam on|off")

    async def toggle_captcha(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_group_toggle_setting(update, context, "captcha_enabled", "/captcha on|off")

    async def toggle_raid(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_group_toggle_setting(update, context, "raid_mode_enabled", "/raid on|off")

    async def toggle_links(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_group_toggle_setting(update, context, "link_filter_enabled", "/links on|off")

    async def toggle_screening(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_group_toggle_setting(update, context, "screening_enabled", "/screening on|off")

    async def set_first_message_delay(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_group_integer_setting(
            update,
            context,
            "first_message_delay_seconds",
            "/setfirstmessagedelay [minutes]",
            transform=lambda value: max(value, 0) * 60,
            success_label="First message delay",
        )

    async def set_duplicate_threshold(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_group_integer_setting(
            update,
            context,
            "duplicate_message_threshold",
            "/setduplicatethreshold [count]",
            transform=lambda value: max(value, 2),
            success_label="Duplicate threshold",
        )

    async def set_duplicate_window(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_group_integer_setting(
            update,
            context,
            "duplicate_message_window_seconds",
            "/setduplicatewindow [seconds]",
            transform=lambda value: max(value, 10),
            success_label="Duplicate window",
        )

    async def allow_domain(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_domain_rule(update, context, "allow")

    async def block_domain(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_domain_rule(update, context, "block")

    async def remove_domain(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        if not context.args:
            await message.reply_text("Usage: /removedomain example.com")
            return
        domain = self.normalize_domain(context.args[0])
        if not domain:
            await message.reply_text("Invalid domain.")
            return
        removed = await self.db.remove_domain_rule(chat.id, domain)
        if removed:
            await self.log_event(chat.id, "domain_rule_remove", user, reason=domain)
            await message.reply_text(f"Removed domain rule for {domain}.")
        else:
            await message.reply_text(f"No rule found for {domain}.")

    async def set_alert_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        alert_chat_id = chat.id
        if context.args:
            try:
                alert_chat_id = int(context.args[0])
            except ValueError:
                await message.reply_text("Usage: /setalertchat [chat_id]")
                return
        await self.db.update_group_setting(chat.id, "admin_alert_chat_id", alert_chat_id)
        await self.log_event(chat.id, "alert_chat_config", user, reason=str(alert_chat_id))
        await message.reply_text(f"Admin alert chat set to {alert_chat_id}.")

    async def add_required_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_required_channel(update, context, add=True)

    async def remove_required_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.update_required_channel(update, context, add=False)

    async def list_required_channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        channels = await self.db.list_required_channels(chat.id)
        if not channels:
            await message.reply_text("No required channels configured.")
            return
        await message.reply_text("Required channels:\n" + "\n".join(channels))

    async def track_chat_member_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        change = update.chat_member
        if not change:
            return
        user = change.new_chat_member.user
        await self.db.upsert_member(
            change.chat.id,
            user.id,
            first_name=user.full_name,
            username=user.username,
            joined=change.new_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED},
            left=change.new_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.BANNED},
        )

    async def handle_new_members(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        if not message or not chat or not message.new_chat_members:
            return
        settings = await self.db.get_group_settings(chat.id)
        joins = self.runtime_state.join_events[chat.id]
        required_channels = await self.db.list_required_channels(chat.id)
        now = datetime.now(UTC)
        for user in message.new_chat_members:
            if user.is_bot:
                continue
            joins.append(now)
            self.trim_deque(joins, timedelta(seconds=self.settings.join_rate_window_seconds))
            await self.db.upsert_member(chat.id, user.id, first_name=user.full_name, username=user.username, joined=True)
            await self.log_event(chat.id, "join", None, target=TargetUser(user.id, self.user_label(user)))
            if len(joins) >= settings.join_rate_threshold:
                await self.log_event(chat.id, "join_rate_alert", None, reason=f"joins={len(joins)}")
                await self.send_admin_alert(chat.id, f"Join-rate alert: {len(joins)} members joined within {self.settings.join_rate_window_seconds}s.")
            missing_channels = await self.get_missing_required_channels(chat.id, user.id, required_channels)
            if missing_channels or settings.captcha_enabled or settings.raid_mode_enabled:
                await context.bot.restrict_chat_member(chat.id, user.id, permissions=MUTED_PERMISSIONS)
                buttons: list[list[InlineKeyboardButton]] = []
                if missing_channels:
                    for channel in missing_channels:
                        join_url = self.channel_join_url(channel)
                        if join_url:
                            buttons.append([InlineKeyboardButton(f"Join {channel}", url=join_url)])
                    prompt = (
                        f"{self.mention_html(user)} join the required channels first, then press Verify within "
                        f"{self.settings.captcha_timeout_seconds} seconds."
                    )
                else:
                    prompt = (
                        f"{self.mention_html(user)} please verify within "
                        f"{self.settings.captcha_timeout_seconds} seconds."
                    )
                buttons.append([InlineKeyboardButton("Verify", callback_data=f"captcha:{chat.id}:{user.id}")])
                challenge = await message.reply_text(
                    prompt,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
                expires_at = datetime.now(UTC) + timedelta(seconds=self.settings.captcha_timeout_seconds)
                await self.db.create_captcha(chat.id, user.id, challenge_message_id=challenge.message_id, service_message_id=message.message_id, expires_at=expires_at.isoformat())
                if context.job_queue:
                    context.job_queue.run_once(self.expire_captcha, when=self.settings.captcha_timeout_seconds, data={"chat_id": chat.id, "user_id": user.id}, name=f"captcha:{chat.id}:{user.id}")
            welcome = self.render_group_text(settings.welcome_message, user, chat.title or "this group")
            await message.reply_text(welcome, parse_mode=ParseMode.HTML)
        if settings.auto_delete_service_messages:
            await self.safe_delete(message)

    async def handle_member_left(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        message = update.effective_message
        chat = update.effective_chat
        if not message or not chat or not message.left_chat_member:
            return
        user = message.left_chat_member
        await self.db.upsert_member(chat.id, user.id, first_name=user.full_name, username=user.username, left=True)
        await self.log_event(chat.id, "leave", None, target=TargetUser(user.id, self.user_label(user)))
        settings = await self.db.get_group_settings(chat.id)
        farewell = self.render_group_text(settings.farewell_message, user, chat.title or "this group")
        await message.reply_text(farewell, parse_mode=ParseMode.HTML)
        if settings.auto_delete_service_messages:
            await self.safe_delete(message)

    async def handle_service_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        message = update.effective_message
        chat = update.effective_chat
        if not message or not chat:
            return
        if message.new_chat_members or message.left_chat_member:
            return
        settings = await self.db.get_group_settings(chat.id)
        if settings.auto_delete_service_messages:
            await self.safe_delete(message)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not user or user.is_bot:
            return
        if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            return
        member = await self.db.get_member(chat.id, user.id)
        settings = await self.db.get_group_settings(chat.id)
        if settings.screening_enabled and member and member.joined_at:
            joined_at = datetime.fromisoformat(member.joined_at)
            delay_until = joined_at + timedelta(seconds=settings.first_message_delay_seconds)
            if datetime.now(UTC) < delay_until:
                await self.safe_delete(message)
                remaining = max(int((delay_until - datetime.now(UTC)).total_seconds()), 1)
                await self.log_event(
                    chat.id,
                    "screening_delay_block",
                    None,
                    target=TargetUser(user.id, self.user_label(user)),
                    reason=f"remaining={remaining}s",
                )
                await context.bot.send_message(
                    chat.id,
                    f"{self.user_label(user)} must wait {remaining}s before sending messages.",
                )
                return
        await self.db.upsert_member(chat.id, user.id, first_name=user.full_name, username=user.username)
        if settings.screening_enabled and message.text:
            duplicate_triggered = await self.check_duplicate_message(
                chat.id,
                user.id,
                message.text,
                settings.duplicate_message_window_seconds,
                settings.duplicate_message_threshold,
            )
            if duplicate_triggered:
                await self.safe_delete(message)
                await self.issue_warning(
                    context,
                    chat.id,
                    user.id,
                    self.user_label(user),
                    "duplicate message pattern detected",
                    actor=None,
                )
                await self.log_event(
                    chat.id,
                    "duplicate_block",
                    None,
                    target=TargetUser(user.id, self.user_label(user)),
                    reason="duplicate message",
                )
                await self.send_admin_alert(chat.id, f"Duplicate message pattern blocked for {self.user_label(user)}.")
                return
        if settings.antispam_enabled:
            threshold = min(settings.flood_threshold, 3) if settings.raid_mode_enabled else settings.flood_threshold
            hit = await self.check_flood(chat.id, user.id, threshold)
            if hit:
                await self.safe_delete(message)
                await self.issue_warning(context, chat.id, user.id, self.user_label(user), "flood spam detected", actor=None)
                until_date = datetime.now(UTC) + timedelta(minutes=self.settings.spam_mute_minutes)
                await context.bot.restrict_chat_member(chat.id, user.id, permissions=MUTED_PERMISSIONS, until_date=until_date)
                await self.log_event(chat.id, "auto_mute", None, target=TargetUser(user.id, self.user_label(user)), reason="flood spam")
                await self.send_admin_alert(chat.id, f"Auto-muted {self.user_label(user)} for flood spam.")
                return
        if message.text and await self.contains_filtered_word(chat.id, message.text):
            await self.safe_delete(message)
            await self.issue_warning(context, chat.id, user.id, self.user_label(user), "bad-word filter triggered", actor=None)
            await self.log_event(chat.id, "filter_hit", None, target=TargetUser(user.id, self.user_label(user)), reason="bad-word")
            await self.send_admin_alert(chat.id, f"Bad-word filter hit by {self.user_label(user)}.")
            return
        if message.text and settings.link_filter_enabled:
            blocked_domain = await self.find_blocked_domain(chat.id, message.text)
            if blocked_domain is not None:
                await self.safe_delete(message)
                await self.issue_warning(context, chat.id, user.id, self.user_label(user), f"blocked link: {blocked_domain}", actor=None)
                await self.log_event(chat.id, "link_block", None, target=TargetUser(user.id, self.user_label(user)), reason=blocked_domain)
                await self.send_admin_alert(chat.id, f"Blocked link from {self.user_label(user)}: {blocked_domain}")

    async def captcha_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.data:
            return
        await query.answer()
        _, chat_id_raw, user_id_raw = query.data.split(":")
        chat_id = int(chat_id_raw)
        user_id = int(user_id_raw)
        if not query.from_user or query.from_user.id != user_id:
            await query.answer("This CAPTCHA is not for you.", show_alert=True)
            return
        captcha = await self.db.get_captcha(chat_id, user_id)
        if captcha is None or captcha["verified"]:
            await query.edit_message_text("CAPTCHA already resolved.")
            return
        missing_channels = await self.get_missing_required_channels(chat_id, user_id)
        if missing_channels:
            await query.answer("Join the required channels first, then press Verify again.", show_alert=True)
            return
        await self.db.verify_captcha(chat_id, user_id)
        await self.db.delete_captcha(chat_id, user_id)
        await context.bot.restrict_chat_member(chat_id, user_id, permissions=DEFAULT_MEMBER_PERMISSIONS)
        await self.log_event(chat_id, "captcha_pass", None, target_user_id=user_id, target_name=str(user_id))
        await query.edit_message_text("Verification complete. Welcome aboard.")

    async def expire_captcha(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        data = context.job.data or {}
        chat_id = data.get("chat_id")
        user_id = data.get("user_id")
        if chat_id is None or user_id is None:
            return
        captcha = await self.db.get_captcha(chat_id, user_id)
        if captcha is None or captcha["verified"]:
            await self.db.delete_captcha(chat_id, user_id)
            return
        try:
            await context.bot.ban_chat_member(chat_id, user_id, revoke_messages=True)
            await context.bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
            if captcha["challenge_message_id"]:
                await context.bot.edit_message_text("CAPTCHA expired. User was removed.", chat_id=chat_id, message_id=captcha["challenge_message_id"])
        except BadRequest:
            LOGGER.exception("Failed to expire CAPTCHA for %s in %s", user_id, chat_id)
        finally:
            await self.db.delete_captcha(chat_id, user_id)
            await self.log_event(chat_id, "captcha_fail", None, target_user_id=user_id, target_name=str(user_id), reason="expired")
            await self.send_admin_alert(chat_id, f"CAPTCHA failed for user {user_id}; user removed.")
    async def scheduled_summary(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = context.job.chat_id
        if chat_id is None:
            return
        text = await self.build_summary(chat_id)
        settings = await self.db.get_group_settings(chat_id)
        target_chat = settings.admin_alert_chat_id or chat_id
        try:
            await context.bot.send_message(target_chat, f"Scheduled summary\n\n{text}")
        except BadRequest:
            LOGGER.exception("Failed to send scheduled summary to %s", target_chat)

    async def refresh_summary_jobs(self, app) -> None:
        if not getattr(app, "job_queue", None):
            return
        current = list(app.job_queue.jobs())
        for job in current:
            if job.name and job.name.startswith("summary:"):
                job.schedule_removal()
        for settings in await self.db.list_groups_with_summaries():
            run_time = time(hour=settings.summary_hour or 0, minute=0, tzinfo=self.settings.timezone)
            app.job_queue.run_daily(self.scheduled_summary, time=run_time, chat_id=settings.chat_id, name=f"summary:{settings.chat_id}")

    async def update_group_text_setting(self, update: Update, context: ContextTypes.DEFAULT_TYPE, field: str, usage: str) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        text = " ".join(context.args).strip()
        if not text:
            await message.reply_text(f"Usage: {usage}")
            return
        await self.db.update_group_setting(chat.id, field, text)
        await self.log_event(chat.id, field, user, reason=text[:100])
        await message.reply_text("Updated successfully.")

    async def update_group_toggle_setting(self, update: Update, context: ContextTypes.DEFAULT_TYPE, field: str, usage: str) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        if not context.args or context.args[0].lower() not in {"on", "off"}:
            await message.reply_text(f"Usage: {usage}")
            return
        value = 1 if context.args[0].lower() == "on" else 0
        await self.db.update_group_setting(chat.id, field, value)
        await self.log_event(chat.id, field, user, reason=context.args[0].lower())
        await message.reply_text(f"{field.replace('_', ' ')} set to {context.args[0].lower()}.")

    async def update_group_integer_setting(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        field: str,
        usage: str,
        *,
        transform,
        success_label: str,
    ) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        if not context.args:
            await message.reply_text(f"Usage: {usage}")
            return
        try:
            raw_value = int(context.args[0])
        except ValueError:
            await message.reply_text(f"Usage: {usage}")
            return
        value = transform(raw_value)
        await self.db.update_group_setting(chat.id, field, value)
        await self.log_event(chat.id, field, user, reason=str(value))
        await message.reply_text(f"{success_label} set to {value}.")

    async def update_bad_word(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *, add: bool) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        if not context.args:
            await message.reply_text(f"Usage: {'/addfilter' if add else '/removefilter'} [word]")
            return
        word = context.args[0].strip().lower()
        if add:
            await self.db.add_bad_word(chat.id, word)
            await self.log_event(chat.id, "add_filter", user, reason=word)
            await message.reply_text(f"Added '{word}' to the filter list.")
        else:
            removed = await self.db.remove_bad_word(chat.id, word)
            if removed:
                await self.log_event(chat.id, "remove_filter", user, reason=word)
                await message.reply_text(f"Removed '{word}' from the filter list.")
            else:
                await message.reply_text(f"'{word}' was not in the filter list.")

    async def update_domain_rule(self, update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        if not context.args:
            await message.reply_text(f"Usage: /{'allowdomain' if action == 'allow' else 'blockdomain'} example.com")
            return
        domain = self.normalize_domain(context.args[0])
        if not domain:
            await message.reply_text("Invalid domain.")
            return
        await self.db.add_domain_rule(chat.id, domain, action)
        await self.log_event(chat.id, f"domain_rule_{action}", user, reason=domain)
        await message.reply_text(f"Domain {domain} set to {action}.")

    async def update_required_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *, add: bool) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        if not context.args:
            usage = "/addrequiredchannel @channel" if add else "/removerequiredchannel @channel"
            await message.reply_text(f"Usage: {usage}")
            return
        channel_ref = self.normalize_channel_ref(context.args[0])
        if not channel_ref:
            await message.reply_text("Use a public channel username like @newschannel.")
            return
        if add:
            await self.db.add_required_channel(chat.id, channel_ref)
            await self.log_event(chat.id, "required_channel_add", user, reason=channel_ref)
            await message.reply_text(f"Added required channel {channel_ref}.")
        else:
            removed = await self.db.remove_required_channel(chat.id, channel_ref)
            if removed:
                await self.log_event(chat.id, "required_channel_remove", user, reason=channel_ref)
                await message.reply_text(f"Removed required channel {channel_ref}.")
            else:
                await message.reply_text(f"{channel_ref} was not configured.")

    async def _moderate_simple(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *, action: str) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not await self.ensure_admin(message, chat.id, user):
            return
        target = await self.require_target_user(update, context)
        if target is None or not await self.can_act_on_target(message, chat.id, target.user_id):
            return
        if action == "kick":
            await context.bot.ban_chat_member(chat.id, target.user_id, revoke_messages=True)
            await context.bot.unban_chat_member(chat.id, target.user_id, only_if_banned=True)
            reply = f"Kicked {target.display_name}."
        else:
            await context.bot.ban_chat_member(chat.id, target.user_id, revoke_messages=True)
            reply = f"Banned {target.display_name}."
        await self.log_event(chat.id, action, user, target=target, reason=target.reason or None)
        await message.reply_text(reply)

    async def require_target_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> TargetUser | None:
        message = update.effective_message
        target = await self.resolve_target_user(update, context, allow_reason=True)
        if target is None and message:
            await message.reply_text("Reply to the user's message, use @username, or pass a numeric Telegram user ID.")
        return target

    async def resolve_target_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *, allow_reason: bool) -> TargetUser | None:
        message = update.effective_message
        chat = update.effective_chat
        if not message or not chat:
            return None
        if message.reply_to_message and message.reply_to_message.from_user:
            user = message.reply_to_message.from_user
            return TargetUser(user.id, self.user_label(user), " ".join(context.args).strip() if allow_reason else "")
        if not context.args:
            return None
        raw_target = context.args[0]
        reason = " ".join(context.args[1:]).strip() if allow_reason else ""
        if raw_target.startswith("@"):
            record = await self.db.find_member_by_username(chat.id, raw_target)
            if not record:
                return None
            display_name = record.first_name or f"@{record.username}" if record.username else raw_target
            return TargetUser(record.user_id, display_name, reason)
        try:
            user_id = int(raw_target)
        except ValueError:
            return None
        member = await self.db.get_member(chat.id, user_id)
        return TargetUser(user_id, member.first_name if member and member.first_name else str(user_id), reason)

    async def ensure_admin(self, message: Message, chat_id: int, user: User | None) -> bool:
        if user is None:
            return False
        member = await message.get_bot().get_chat_member(chat_id, user.id)
        if member.status not in ADMIN_STATUSES:
            await message.reply_text("This command is restricted to group admins.")
            return False
        return True

    async def can_act_on_target(self, message: Message, chat_id: int, user_id: int) -> bool:
        try:
            member = await message.get_bot().get_chat_member(chat_id, user_id)
        except BadRequest:
            return True
        if member.status in ADMIN_STATUSES:
            await message.reply_text("I can't act on another admin.")
            return False
        return True

    async def issue_warning(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, display_name: str, reason: str, *, actor: User | None) -> int:
        count = await self.db.add_warning(chat_id, user_id, reason)
        await self.log_event(chat_id, "warn", actor, target_user_id=user_id, target_name=display_name, reason=reason, metadata={"count": count})
        if count >= self.settings.warn_limit:
            await context.bot.ban_chat_member(chat_id, user_id, revoke_messages=True)
            await self.log_event(chat_id, "auto_ban", None, target_user_id=user_id, target_name=display_name, reason="warning threshold")
            await context.bot.send_message(chat_id, f"{display_name} reached {count} warnings and was auto-banned.")
            await self.send_admin_alert(chat_id, f"Auto-banned {display_name} after {count} warnings.")
        return count

    async def check_flood(self, chat_id: int, user_id: int, threshold: int) -> bool:
        events = self.runtime_state.flood_events[(chat_id, user_id)]
        events.append(datetime.now(UTC))
        self.trim_deque(events, timedelta(seconds=self.settings.spam_window_seconds))
        return len(events) >= threshold

    async def check_duplicate_message(
        self,
        chat_id: int,
        user_id: int,
        text: str,
        window_seconds: int,
        threshold: int,
    ) -> bool:
        normalized = self.normalize_message_text(text)
        if not normalized:
            return False
        bucket = self.runtime_state.recent_texts[chat_id][normalized]
        now = datetime.now(UTC)
        bucket.append((user_id, now))
        cutoff = now - timedelta(seconds=window_seconds)
        while bucket and bucket[0][1] < cutoff:
            bucket.popleft()
        unique_users = {entry_user for entry_user, _ in bucket}
        return len(bucket) >= threshold and len(unique_users) >= 1

    async def contains_filtered_word(self, chat_id: int, text: str) -> bool:
        lowered = text.lower()
        for word in await self.db.list_bad_words(chat_id):
            if re.search(rf"\b{re.escape(word)}\b", lowered):
                return True
        return False

    async def find_blocked_domain(self, chat_id: int, text: str) -> str | None:
        matches = LINK_RE.findall(text)
        if not matches:
            return None
        has_allow_rules = bool(await self.db.list_domain_rules(chat_id, "allow"))
        for raw in matches:
            domain = self.normalize_domain(raw)
            if not domain:
                continue
            action = await self.db.get_domain_action(chat_id, domain)
            if action == "block":
                return domain
            if has_allow_rules and action != "allow":
                return domain
        return None

    async def get_missing_required_channels(
        self,
        chat_id: int,
        user_id: int,
        channels: list[str] | None = None,
    ) -> list[str]:
        refs = channels if channels is not None else await self.db.list_required_channels(chat_id)
        missing: list[str] = []
        for channel in refs:
            try:
                member = await self.application.bot.get_chat_member(channel, user_id) if self.application else None
            except BadRequest:
                missing.append(channel)
                continue
            if member is None or member.status not in {
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER,
            }:
                missing.append(channel)
        return missing

    async def build_summary(self, chat_id: int) -> str:
        since = datetime.now(UTC) - timedelta(hours=self.settings.summary_history_hours)
        counts = await self.db.get_event_counts_since(chat_id, since)
        events = await self.db.list_recent_events(chat_id, since)
        top_events: dict[str, int] = defaultdict(int)
        for event in events:
            top_events[event.event_type] += 1
        lines = [f"Summary for last {self.settings.summary_history_hours}h"]
        if not counts:
            lines.append("No moderation activity recorded.")
            return "\n".join(lines)
        for key in sorted(counts):
            lines.append(f"{key}: {counts[key]}")
        return "\n".join(lines)

    async def send_admin_alert(self, source_chat_id: int, text: str) -> None:
        settings = await self.db.get_group_settings(source_chat_id)
        target_chat = settings.admin_alert_chat_id
        if not target_chat or self.application is None:
            return
        try:
            await self.application.bot.send_message(target_chat, text)
        except BadRequest:
            LOGGER.exception("Failed to send admin alert to %s", target_chat)

    async def log_event(
        self,
        chat_id: int,
        event_type: str,
        actor: User | None = None,
        *,
        target: TargetUser | None = None,
        target_user_id: int | None = None,
        target_name: str | None = None,
        reason: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        await self.db.log_event(
            chat_id,
            event_type,
            actor_user_id=actor.id if actor else None,
            actor_name=self.user_label(actor) if actor else None,
            target_user_id=target.user_id if target else target_user_id,
            target_name=target.display_name if target else target_name,
            reason=reason,
            metadata=metadata or {},
        )

    def trim_deque(self, items: deque[datetime], window: timedelta) -> None:
        cutoff = datetime.now(UTC) - window
        while items and items[0] < cutoff:
            items.popleft()

    def normalize_message_text(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", text.strip().lower())
        return normalized[:300]

    def parse_duration_minutes(self, raw: str) -> int | None:
        if not raw:
            return None
        match = re.search(r"(\d+)([mh]?)", raw.lower())
        if not match:
            return None
        amount = int(match.group(1))
        return amount * 60 if match.group(2) == "h" else amount

    def normalize_domain(self, value: str) -> str | None:
        raw = value.strip().lower()
        if not raw:
            return None
        if not raw.startswith(("http://", "https://")):
            raw = f"https://{raw}"
        parsed = urlparse(raw)
        host = parsed.netloc or parsed.path
        host = host.lower().lstrip("www.").split(":")[0]
        return host if "." in host else None

    def normalize_channel_ref(self, value: str) -> str | None:
        raw = value.strip()
        if not raw:
            return None
        if raw.startswith("https://t.me/"):
            raw = "@" + raw.removeprefix("https://t.me/").strip("/")
        if not raw.startswith("@"):
            raw = "@" + raw
        username = raw[1:]
        if not re.fullmatch(r"[A-Za-z0-9_]{4,}", username):
            return None
        return raw

    def channel_join_url(self, channel_ref: str) -> str | None:
        if not channel_ref.startswith("@"):
            return None
        return f"https://t.me/{channel_ref[1:]}"

    def render_group_text(self, template: str, user: User, group_name: str) -> str:
        return template.format(
            user=self.mention_html(user),
            first_name=html.escape(user.first_name or user.full_name),
            username=f"@{user.username}" if user.username else "unknown",
            group=html.escape(group_name),
        )

    def mention_html(self, user: User) -> str:
        return f'<a href="tg://user?id={user.id}">{html.escape(user.full_name)}</a>'

    def user_label(self, user: User | None) -> str:
        if user is None:
            return "system"
        if user.username:
            return f"@{user.username}"
        return user.full_name

    async def safe_delete(self, message: Message) -> None:
        try:
            await message.delete()
        except (BadRequest, Forbidden):
            LOGGER.debug("Unable to delete message %s in chat %s", message.message_id, message.chat_id)
