"""Admin config commands: setwelcome, setfarewell, setrules, addfilter, removefilter,
setflood, antispam, captcha."""
from telegram import Update
from telegram.ext import ContextTypes

from bot.database import (
    set_group_field,
    get_group_config,
    add_bad_word,
    remove_bad_word,
    get_bad_words,
)
from bot.helpers import require_admin


async def setwelcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    args = update.message.text.split(None, 1)
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /setwelcome <message>\n"
            "Placeholders: {first_name} {username} {group_name}"
        )
        return
    msg = args[1]
    await set_group_field(update.effective_chat.id, "welcome_msg", msg)
    await update.message.reply_html(f"✅ Welcome message set:\n<i>{msg}</i>")


async def setfarewell_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    args = update.message.text.split(None, 1)
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /setfarewell <message>\n"
            "Placeholders: {first_name} {username} {group_name}"
        )
        return
    msg = args[1]
    await set_group_field(update.effective_chat.id, "farewell_msg", msg)
    await update.message.reply_html(f"✅ Farewell message set:\n<i>{msg}</i>")


async def setrules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    args = update.message.text.split(None, 1)
    if len(args) < 2:
        await update.message.reply_text("Usage: /setrules <rules text>")
        return
    rules = args[1]
    await set_group_field(update.effective_chat.id, "rules", rules)
    await update.message.reply_html(f"✅ Rules updated:\n<i>{rules}</i>")


async def addfilter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    args = update.message.text.split()[1:]
    if not args:
        await update.message.reply_text("Usage: /addfilter <word>")
        return
    word = args[0].lower()
    await add_bad_word(update.effective_chat.id, word)
    await update.message.reply_text(f"✅ Added '{word}' to the word filter.")


async def removefilter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    args = update.message.text.split()[1:]
    if not args:
        await update.message.reply_text("Usage: /removefilter <word>")
        return
    word = args[0].lower()
    await remove_bad_word(update.effective_chat.id, word)
    await update.message.reply_text(f"✅ Removed '{word}' from the word filter.")


async def listfilters_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    words = await get_bad_words(update.effective_chat.id)
    if not words:
        await update.message.reply_text("No words in the filter list.")
    else:
        await update.message.reply_html(
            "<b>Filtered words:</b>\n" + "\n".join(f"• {w}" for w in words)
        )


async def setflood_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    args = update.message.text.split()[1:]
    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: /setflood <number> (messages per 5 seconds)")
        return
    count = int(args[0])
    if count < 2:
        await update.message.reply_text("Flood limit must be at least 2.")
        return
    await set_group_field(update.effective_chat.id, "flood_count", count)
    await update.message.reply_text(f"✅ Flood limit set to {count} messages per 5 seconds.")


async def antispam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    args = update.message.text.split()[1:]
    if not args or args[0].lower() not in ("on", "off"):
        cfg = await get_group_config(update.effective_chat.id)
        state = "on" if cfg.get("antispam") else "off"
        await update.message.reply_text(f"Anti-spam is currently {state}. Use /antispam on|off")
        return
    enabled = args[0].lower() == "on"
    await set_group_field(update.effective_chat.id, "antispam", int(enabled))
    await update.message.reply_text(f"✅ Anti-spam turned {'on' if enabled else 'off'}.")


async def captcha_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    args = update.message.text.split()[1:]
    if not args or args[0].lower() not in ("on", "off"):
        cfg = await get_group_config(update.effective_chat.id)
        state = "on" if cfg.get("captcha") else "off"
        await update.message.reply_text(f"CAPTCHA is currently {state}. Use /captcha on|off")
        return
    enabled = args[0].lower() == "on"
    await set_group_field(update.effective_chat.id, "captcha", int(enabled))
    await update.message.reply_text(f"✅ Join CAPTCHA turned {'on' if enabled else 'off'}.")
