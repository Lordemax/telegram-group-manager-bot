import aiosqlite
from bot.config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_config (
                chat_id INTEGER PRIMARY KEY,
                welcome_msg TEXT DEFAULT 'Welcome {first_name} to {group_name}!',
                farewell_msg TEXT DEFAULT 'Goodbye {first_name}!',
                rules TEXT DEFAULT 'No rules set yet.',
                warn_limit INTEGER DEFAULT 3,
                flood_count INTEGER DEFAULT 5,
                antispam INTEGER DEFAULT 1,
                captcha INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bad_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                word TEXT NOT NULL,
                UNIQUE(chat_id, word)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_info (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        await db.commit()


async def ensure_group(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO group_config (chat_id) VALUES (?)",
            (chat_id,)
        )
        await db.commit()


async def get_group_config(chat_id: int) -> dict:
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM group_config WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else {}


_ALLOWED_GROUP_FIELDS = frozenset({
    "welcome_msg",
    "farewell_msg",
    "rules",
    "warn_limit",
    "flood_count",
    "antispam",
    "captcha",
})


async def set_group_field(chat_id: int, field: str, value):
    if field not in _ALLOWED_GROUP_FIELDS:
        raise ValueError(f"set_group_field: '{field}' is not an allowed column")
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE group_config SET {field} = ? WHERE chat_id = ?",
            (value, chat_id)
        )
        await db.commit()


async def add_warning(chat_id: int, user_id: int, reason: str = "") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO warnings (chat_id, user_id, reason) VALUES (?, ?, ?)",
            (chat_id, user_id, reason)
        )
        await db.commit()
        async with db.execute(
            "SELECT COUNT(*) FROM warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0]


async def get_warnings(chat_id: int, user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM warnings WHERE chat_id = ? AND user_id = ? ORDER BY created_at DESC",
            (chat_id, user_id)
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def clear_warnings(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        await db.commit()


async def add_bad_word(chat_id: int, word: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO bad_words (chat_id, word) VALUES (?, ?)",
            (chat_id, word.lower())
        )
        await db.commit()


async def remove_bad_word(chat_id: int, word: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM bad_words WHERE chat_id = ? AND word = ?",
            (chat_id, word.lower())
        )
        await db.commit()


async def get_bad_words(chat_id: int) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT word FROM bad_words WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]


async def track_user(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_info (chat_id, user_id) VALUES (?, ?)",
            (chat_id, user_id)
        )
        await db.commit()


async def get_all_warnings(chat_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM warnings WHERE chat_id = ? ORDER BY created_at DESC",
            (chat_id,)
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_all_groups() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM group_config") as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_user_first_seen(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT first_seen FROM user_info WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None
