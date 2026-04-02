from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite

from .config import DEFAULT_FAREWELL, DEFAULT_RULES, DEFAULT_WELCOME


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return utc_now().isoformat()


@dataclass(slots=True)
class GroupSettings:
    chat_id: int
    welcome_message: str = DEFAULT_WELCOME
    farewell_message: str = DEFAULT_FAREWELL
    rules_text: str = DEFAULT_RULES
    flood_threshold: int = 5
    antispam_enabled: bool = True
    captcha_enabled: bool = True
    auto_delete_service_messages: bool = True
    raid_mode_enabled: bool = False
    link_filter_enabled: bool = False
    join_rate_threshold: int = 10
    admin_alert_chat_id: int | None = None
    summary_enabled: bool = False
    summary_hour: int | None = None
    screening_enabled: bool = False
    first_message_delay_seconds: int = 300
    duplicate_message_window_seconds: int = 60
    duplicate_message_threshold: int = 3


@dataclass(slots=True)
class MemberRecord:
    chat_id: int
    user_id: int
    joined_at: str | None = None
    first_name: str | None = None
    username: str | None = None
    last_seen_at: str | None = None
    left_at: str | None = None


@dataclass(slots=True)
class ModEvent:
    id: int
    chat_id: int
    actor_user_id: int | None
    actor_name: str | None
    target_user_id: int | None
    target_name: str | None
    event_type: str
    reason: str | None
    metadata: dict[str, Any]
    created_at: str


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self.path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        return conn

    async def close(self, conn: aiosqlite.Connection) -> None:
        await conn.close()

    async def initialize(self) -> None:
        db = await self.connect()
        try:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS group_settings (
                    chat_id INTEGER PRIMARY KEY,
                    welcome_message TEXT NOT NULL,
                    farewell_message TEXT NOT NULL,
                    rules_text TEXT NOT NULL,
                    flood_threshold INTEGER NOT NULL DEFAULT 5,
                    antispam_enabled INTEGER NOT NULL DEFAULT 1,
                    captcha_enabled INTEGER NOT NULL DEFAULT 1,
                    auto_delete_service_messages INTEGER NOT NULL DEFAULT 1,
                    raid_mode_enabled INTEGER NOT NULL DEFAULT 0,
                    link_filter_enabled INTEGER NOT NULL DEFAULT 0,
                    join_rate_threshold INTEGER NOT NULL DEFAULT 10,
                    admin_alert_chat_id INTEGER,
                    summary_enabled INTEGER NOT NULL DEFAULT 0,
                    summary_hour INTEGER,
                    screening_enabled INTEGER NOT NULL DEFAULT 0,
                    first_message_delay_seconds INTEGER NOT NULL DEFAULT 300,
                    duplicate_message_window_seconds INTEGER NOT NULL DEFAULT 60,
                    duplicate_message_threshold INTEGER NOT NULL DEFAULT 3
                );

                CREATE TABLE IF NOT EXISTS members (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    joined_at TEXT,
                    first_name TEXT,
                    username TEXT,
                    last_seen_at TEXT,
                    left_at TEXT,
                    PRIMARY KEY (chat_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS warnings (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    reasons_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (chat_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS bad_words (
                    chat_id INTEGER NOT NULL,
                    word TEXT NOT NULL,
                    PRIMARY KEY (chat_id, word)
                );

                CREATE TABLE IF NOT EXISTS captcha_challenges (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    challenge_message_id INTEGER,
                    service_message_id INTEGER,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    verified INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (chat_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS domain_rules (
                    chat_id INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    action TEXT NOT NULL,
                    PRIMARY KEY (chat_id, domain)
                );

                CREATE TABLE IF NOT EXISTS required_channels (
                    chat_id INTEGER NOT NULL,
                    channel_ref TEXT NOT NULL,
                    PRIMARY KEY (chat_id, channel_ref)
                );

                CREATE TABLE IF NOT EXISTS mod_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    actor_user_id INTEGER,
                    actor_name TEXT,
                    target_user_id INTEGER,
                    target_name TEXT,
                    event_type TEXT NOT NULL,
                    reason TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                """
            )
            await self._migrate_group_settings(db)
            await db.commit()
        finally:
            await self.close(db)

    async def _migrate_group_settings(self, db: aiosqlite.Connection) -> None:
        cursor = await db.execute("PRAGMA table_info(group_settings)")
        columns = {row["name"] for row in await cursor.fetchall()}
        migrations = {
            "raid_mode_enabled": "ALTER TABLE group_settings ADD COLUMN raid_mode_enabled INTEGER NOT NULL DEFAULT 0",
            "link_filter_enabled": "ALTER TABLE group_settings ADD COLUMN link_filter_enabled INTEGER NOT NULL DEFAULT 0",
            "join_rate_threshold": "ALTER TABLE group_settings ADD COLUMN join_rate_threshold INTEGER NOT NULL DEFAULT 10",
            "admin_alert_chat_id": "ALTER TABLE group_settings ADD COLUMN admin_alert_chat_id INTEGER",
            "summary_enabled": "ALTER TABLE group_settings ADD COLUMN summary_enabled INTEGER NOT NULL DEFAULT 0",
            "summary_hour": "ALTER TABLE group_settings ADD COLUMN summary_hour INTEGER",
            "screening_enabled": "ALTER TABLE group_settings ADD COLUMN screening_enabled INTEGER NOT NULL DEFAULT 0",
            "first_message_delay_seconds": "ALTER TABLE group_settings ADD COLUMN first_message_delay_seconds INTEGER NOT NULL DEFAULT 300",
            "duplicate_message_window_seconds": "ALTER TABLE group_settings ADD COLUMN duplicate_message_window_seconds INTEGER NOT NULL DEFAULT 60",
            "duplicate_message_threshold": "ALTER TABLE group_settings ADD COLUMN duplicate_message_threshold INTEGER NOT NULL DEFAULT 3",
        }
        for column, sql in migrations.items():
            if column not in columns:
                await db.execute(sql)

    async def get_group_settings(self, chat_id: int) -> GroupSettings:
        db = await self.connect()
        try:
            cursor = await db.execute("SELECT * FROM group_settings WHERE chat_id = ?", (chat_id,))
            row = await cursor.fetchone()
            if row is None:
                settings = GroupSettings(chat_id=chat_id)
                await db.execute(
                    """
                    INSERT INTO group_settings (
                        chat_id, welcome_message, farewell_message, rules_text,
                        flood_threshold, antispam_enabled, captcha_enabled,
                        auto_delete_service_messages, raid_mode_enabled, link_filter_enabled,
                        join_rate_threshold, admin_alert_chat_id, summary_enabled, summary_hour,
                        screening_enabled, first_message_delay_seconds, duplicate_message_window_seconds,
                        duplicate_message_threshold
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        settings.chat_id,
                        settings.welcome_message,
                        settings.farewell_message,
                        settings.rules_text,
                        settings.flood_threshold,
                        int(settings.antispam_enabled),
                        int(settings.captcha_enabled),
                        int(settings.auto_delete_service_messages),
                        int(settings.raid_mode_enabled),
                        int(settings.link_filter_enabled),
                        settings.join_rate_threshold,
                        settings.admin_alert_chat_id,
                        int(settings.summary_enabled),
                        settings.summary_hour,
                        int(settings.screening_enabled),
                        settings.first_message_delay_seconds,
                        settings.duplicate_message_window_seconds,
                        settings.duplicate_message_threshold,
                    ),
                )
                await db.commit()
                return settings
            return self._row_to_group_settings(row)
        finally:
            await self.close(db)

    async def update_group_setting(self, chat_id: int, field: str, value: object) -> GroupSettings:
        allowed_fields = {
            "welcome_message",
            "farewell_message",
            "rules_text",
            "flood_threshold",
            "antispam_enabled",
            "captcha_enabled",
            "auto_delete_service_messages",
            "raid_mode_enabled",
            "link_filter_enabled",
            "join_rate_threshold",
            "admin_alert_chat_id",
            "summary_enabled",
            "summary_hour",
            "screening_enabled",
            "first_message_delay_seconds",
            "duplicate_message_window_seconds",
            "duplicate_message_threshold",
        }
        if field not in allowed_fields:
            raise ValueError(f"Unsupported group setting field: {field}")
        await self.get_group_settings(chat_id)
        db = await self.connect()
        try:
            await db.execute(f"UPDATE group_settings SET {field} = ? WHERE chat_id = ?", (value, chat_id))
            await db.commit()
        finally:
            await self.close(db)
        return await self.get_group_settings(chat_id)

    async def list_groups_with_summaries(self) -> list[GroupSettings]:
        db = await self.connect()
        try:
            cursor = await db.execute(
                "SELECT * FROM group_settings WHERE summary_enabled = 1 AND summary_hour IS NOT NULL"
            )
            rows = await cursor.fetchall()
            return [self._row_to_group_settings(row) for row in rows]
        finally:
            await self.close(db)

    async def upsert_member(
        self,
        chat_id: int,
        user_id: int,
        *,
        first_name: str | None,
        username: str | None,
        joined: bool = False,
        left: bool = False,
    ) -> None:
        now = utc_now_iso()
        db = await self.connect()
        try:
            cursor = await db.execute(
                "SELECT joined_at FROM members WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            )
            row = await cursor.fetchone()
            joined_at = row["joined_at"] if row else None
            if joined and not joined_at:
                joined_at = now
            await db.execute(
                """
                INSERT INTO members (
                    chat_id, user_id, joined_at, first_name, username, last_seen_at, left_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    first_name = excluded.first_name,
                    username = excluded.username,
                    last_seen_at = excluded.last_seen_at,
                    joined_at = COALESCE(members.joined_at, excluded.joined_at),
                    left_at = excluded.left_at
                """,
                (chat_id, user_id, joined_at, first_name, username, now, now if left else None),
            )
            await db.commit()
        finally:
            await self.close(db)

    async def get_member(self, chat_id: int, user_id: int) -> MemberRecord | None:
        db = await self.connect()
        try:
            cursor = await db.execute("SELECT * FROM members WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            row = await cursor.fetchone()
            return self._row_to_member(row) if row else None
        finally:
            await self.close(db)

    async def find_member_by_username(self, chat_id: int, username: str) -> MemberRecord | None:
        db = await self.connect()
        try:
            cursor = await db.execute(
                """
                SELECT * FROM members
                WHERE chat_id = ? AND lower(username) = ?
                ORDER BY COALESCE(last_seen_at, joined_at) DESC
                LIMIT 1
                """,
                (chat_id, username.lstrip("@").lower()),
            )
            row = await cursor.fetchone()
            return self._row_to_member(row) if row else None
        finally:
            await self.close(db)

    async def add_warning(self, chat_id: int, user_id: int, reason: str | None) -> int:
        now = utc_now_iso()
        db = await self.connect()
        try:
            cursor = await db.execute(
                "SELECT count, reasons_json FROM warnings WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            )
            row = await cursor.fetchone()
            count = 0
            reasons: list[str] = []
            if row is not None:
                count = row["count"]
                reasons = json.loads(row["reasons_json"])
            count += 1
            if reason:
                reasons.append(reason)
            await db.execute(
                """
                INSERT INTO warnings (chat_id, user_id, count, reasons_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    count = excluded.count,
                    reasons_json = excluded.reasons_json,
                    updated_at = excluded.updated_at
                """,
                (chat_id, user_id, count, json.dumps(reasons[-20:]), now),
            )
            await db.commit()
            return count
        finally:
            await self.close(db)

    async def get_warning_count(self, chat_id: int, user_id: int) -> int:
        db = await self.connect()
        try:
            cursor = await db.execute("SELECT count FROM warnings WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            row = await cursor.fetchone()
            return int(row["count"]) if row else 0
        finally:
            await self.close(db)

    async def clear_warnings(self, chat_id: int, user_id: int) -> None:
        db = await self.connect()
        try:
            await db.execute("DELETE FROM warnings WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            await db.commit()
        finally:
            await self.close(db)

    async def list_bad_words(self, chat_id: int) -> list[str]:
        db = await self.connect()
        try:
            cursor = await db.execute("SELECT word FROM bad_words WHERE chat_id = ? ORDER BY word ASC", (chat_id,))
            return [row["word"] for row in await cursor.fetchall()]
        finally:
            await self.close(db)

    async def add_bad_word(self, chat_id: int, word: str) -> None:
        db = await self.connect()
        try:
            await db.execute("INSERT OR IGNORE INTO bad_words (chat_id, word) VALUES (?, ?)", (chat_id, word.lower()))
            await db.commit()
        finally:
            await self.close(db)

    async def remove_bad_word(self, chat_id: int, word: str) -> bool:
        db = await self.connect()
        try:
            cursor = await db.execute("DELETE FROM bad_words WHERE chat_id = ? AND word = ?", (chat_id, word.lower()))
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await self.close(db)

    async def list_domain_rules(self, chat_id: int, action: str | None = None) -> list[str]:
        db = await self.connect()
        try:
            if action is None:
                cursor = await db.execute("SELECT domain FROM domain_rules WHERE chat_id = ? ORDER BY domain ASC", (chat_id,))
            else:
                cursor = await db.execute(
                    "SELECT domain FROM domain_rules WHERE chat_id = ? AND action = ? ORDER BY domain ASC",
                    (chat_id, action),
                )
            return [row["domain"] for row in await cursor.fetchall()]
        finally:
            await self.close(db)

    async def add_domain_rule(self, chat_id: int, domain: str, action: str) -> None:
        db = await self.connect()
        try:
            await db.execute(
                "INSERT INTO domain_rules (chat_id, domain, action) VALUES (?, ?, ?) ON CONFLICT(chat_id, domain) DO UPDATE SET action = excluded.action",
                (chat_id, domain.lower(), action),
            )
            await db.commit()
        finally:
            await self.close(db)

    async def remove_domain_rule(self, chat_id: int, domain: str) -> bool:
        db = await self.connect()
        try:
            cursor = await db.execute("DELETE FROM domain_rules WHERE chat_id = ? AND domain = ?", (chat_id, domain.lower()))
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await self.close(db)

    async def get_domain_action(self, chat_id: int, domain: str) -> str | None:
        db = await self.connect()
        try:
            cursor = await db.execute("SELECT action FROM domain_rules WHERE chat_id = ? AND domain = ?", (chat_id, domain.lower()))
            row = await cursor.fetchone()
            return str(row["action"]) if row else None
        finally:
            await self.close(db)

    async def list_required_channels(self, chat_id: int) -> list[str]:
        db = await self.connect()
        try:
            cursor = await db.execute(
                "SELECT channel_ref FROM required_channels WHERE chat_id = ? ORDER BY channel_ref ASC",
                (chat_id,),
            )
            return [row["channel_ref"] for row in await cursor.fetchall()]
        finally:
            await self.close(db)

    async def add_required_channel(self, chat_id: int, channel_ref: str) -> None:
        db = await self.connect()
        try:
            await db.execute(
                "INSERT OR IGNORE INTO required_channels (chat_id, channel_ref) VALUES (?, ?)",
                (chat_id, channel_ref),
            )
            await db.commit()
        finally:
            await self.close(db)

    async def remove_required_channel(self, chat_id: int, channel_ref: str) -> bool:
        db = await self.connect()
        try:
            cursor = await db.execute(
                "DELETE FROM required_channels WHERE chat_id = ? AND channel_ref = ?",
                (chat_id, channel_ref),
            )
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await self.close(db)

    async def log_event(
        self,
        chat_id: int,
        event_type: str,
        *,
        actor_user_id: int | None = None,
        actor_name: str | None = None,
        target_user_id: int | None = None,
        target_name: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        db = await self.connect()
        try:
            await db.execute(
                """
                INSERT INTO mod_events (
                    chat_id, actor_user_id, actor_name, target_user_id, target_name,
                    event_type, reason, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    actor_user_id,
                    actor_name,
                    target_user_id,
                    target_name,
                    event_type,
                    reason,
                    json.dumps(metadata or {}),
                    utc_now_iso(),
                ),
            )
            await db.commit()
        finally:
            await self.close(db)

    async def get_modlog(self, chat_id: int, limit: int = 10) -> list[ModEvent]:
        db = await self.connect()
        try:
            cursor = await db.execute(
                "SELECT * FROM mod_events WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
                (chat_id, limit),
            )
            rows = await cursor.fetchall()
            return [self._row_to_mod_event(row) for row in rows]
        finally:
            await self.close(db)

    async def get_event_counts_since(self, chat_id: int, since: datetime) -> dict[str, int]:
        db = await self.connect()
        try:
            cursor = await db.execute(
                "SELECT event_type, COUNT(*) AS total FROM mod_events WHERE chat_id = ? AND created_at >= ? GROUP BY event_type",
                (chat_id, since.isoformat()),
            )
            rows = await cursor.fetchall()
            return {row['event_type']: int(row['total']) for row in rows}
        finally:
            await self.close(db)

    async def list_recent_events(self, chat_id: int, since: datetime) -> list[ModEvent]:
        db = await self.connect()
        try:
            cursor = await db.execute(
                "SELECT * FROM mod_events WHERE chat_id = ? AND created_at >= ? ORDER BY id DESC",
                (chat_id, since.isoformat()),
            )
            rows = await cursor.fetchall()
            return [self._row_to_mod_event(row) for row in rows]
        finally:
            await self.close(db)

    async def create_captcha(self, chat_id: int, user_id: int, *, challenge_message_id: int, service_message_id: int | None, expires_at: str) -> None:
        db = await self.connect()
        try:
            await db.execute(
                """
                INSERT INTO captcha_challenges (
                    chat_id, user_id, challenge_message_id, service_message_id, created_at, expires_at, verified
                ) VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    challenge_message_id = excluded.challenge_message_id,
                    service_message_id = excluded.service_message_id,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at,
                    verified = 0
                """,
                (chat_id, user_id, challenge_message_id, service_message_id, utc_now_iso(), expires_at),
            )
            await db.commit()
        finally:
            await self.close(db)

    async def get_captcha(self, chat_id: int, user_id: int) -> aiosqlite.Row | None:
        db = await self.connect()
        try:
            cursor = await db.execute("SELECT * FROM captcha_challenges WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            return await cursor.fetchone()
        finally:
            await self.close(db)

    async def list_pending_captchas(self) -> list[aiosqlite.Row]:
        db = await self.connect()
        try:
            cursor = await db.execute("SELECT * FROM captcha_challenges WHERE verified = 0")
            return await cursor.fetchall()
        finally:
            await self.close(db)

    async def verify_captcha(self, chat_id: int, user_id: int) -> None:
        db = await self.connect()
        try:
            await db.execute("UPDATE captcha_challenges SET verified = 1 WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            await db.commit()
        finally:
            await self.close(db)

    async def delete_captcha(self, chat_id: int, user_id: int) -> None:
        db = await self.connect()
        try:
            await db.execute("DELETE FROM captcha_challenges WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            await db.commit()
        finally:
            await self.close(db)

    async def export_group_state(self, chat_id: int) -> dict[str, Any]:
        settings = await self.get_group_settings(chat_id)
        db = await self.connect()
        try:
            members_cur = await db.execute("SELECT * FROM members WHERE chat_id = ? ORDER BY COALESCE(last_seen_at, joined_at) DESC", (chat_id,))
            warnings_cur = await db.execute("SELECT * FROM warnings WHERE chat_id = ? ORDER BY updated_at DESC", (chat_id,))
            events_cur = await db.execute("SELECT * FROM mod_events WHERE chat_id = ? ORDER BY id DESC LIMIT 200", (chat_id,))
            domains_cur = await db.execute("SELECT domain, action FROM domain_rules WHERE chat_id = ? ORDER BY domain ASC", (chat_id,))
            required_cur = await db.execute("SELECT channel_ref FROM required_channels WHERE chat_id = ? ORDER BY channel_ref ASC", (chat_id,))
            filters_cur = await db.execute("SELECT word FROM bad_words WHERE chat_id = ? ORDER BY word ASC", (chat_id,))
            members = [dict(row) for row in await members_cur.fetchall()]
            warnings = []
            for row in await warnings_cur.fetchall():
                warnings.append({
                    'chat_id': row['chat_id'],
                    'user_id': row['user_id'],
                    'count': row['count'],
                    'reasons': json.loads(row['reasons_json']),
                    'updated_at': row['updated_at'],
                })
            events = [asdict(self._row_to_mod_event(row)) for row in await events_cur.fetchall()]
            return {
                'settings': asdict(settings),
                'members': members,
                'warnings': warnings,
                'domain_rules': [dict(row) for row in await domains_cur.fetchall()],
                'required_channels': [row['channel_ref'] for row in await required_cur.fetchall()],
                'bad_words': [row['word'] for row in await filters_cur.fetchall()],
                'mod_events': events,
                'exported_at': utc_now_iso(),
            }
        finally:
            await self.close(db)

    def _row_to_group_settings(self, row: aiosqlite.Row) -> GroupSettings:
        return GroupSettings(
            chat_id=row['chat_id'],
            welcome_message=row['welcome_message'],
            farewell_message=row['farewell_message'],
            rules_text=row['rules_text'],
            flood_threshold=row['flood_threshold'],
            antispam_enabled=bool(row['antispam_enabled']),
            captcha_enabled=bool(row['captcha_enabled']),
            auto_delete_service_messages=bool(row['auto_delete_service_messages']),
            raid_mode_enabled=bool(row['raid_mode_enabled']),
            link_filter_enabled=bool(row['link_filter_enabled']),
            join_rate_threshold=row['join_rate_threshold'],
            admin_alert_chat_id=row['admin_alert_chat_id'],
            summary_enabled=bool(row['summary_enabled']),
            summary_hour=row['summary_hour'],
            screening_enabled=bool(row['screening_enabled']),
            first_message_delay_seconds=row['first_message_delay_seconds'],
            duplicate_message_window_seconds=row['duplicate_message_window_seconds'],
            duplicate_message_threshold=row['duplicate_message_threshold'],
        )

    def _row_to_member(self, row: aiosqlite.Row) -> MemberRecord:
        return MemberRecord(
            chat_id=row['chat_id'],
            user_id=row['user_id'],
            joined_at=row['joined_at'],
            first_name=row['first_name'],
            username=row['username'],
            last_seen_at=row['last_seen_at'],
            left_at=row['left_at'],
        )

    def _row_to_mod_event(self, row: aiosqlite.Row) -> ModEvent:
        return ModEvent(
            id=row['id'],
            chat_id=row['chat_id'],
            actor_user_id=row['actor_user_id'],
            actor_name=row['actor_name'],
            target_user_id=row['target_user_id'],
            target_name=row['target_name'],
            event_type=row['event_type'],
            reason=row['reason'],
            metadata=json.loads(row['metadata_json']),
            created_at=row['created_at'],
        )
