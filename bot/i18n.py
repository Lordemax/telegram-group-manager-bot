"""Simple i18n module — English (en) and Spanish (es)."""

_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "welcome": "Welcome {first_name} to {group_name}!",
        "farewell": "Goodbye {first_name}! We'll miss you.",
        "no_rules": "No rules have been set for this group yet.",
        "rules_header": "📋 Rules for {group_name}:",
        "banned": "🚫 {mention} has been banned.",
        "banned_reason": "🚫 {mention} has been banned.\nReason: {reason}",
        "unbanned": "✅ User {user_id} has been unbanned.",
        "kicked": "👢 {mention} has been kicked.",
        "muted": "🔇 {mention} has been muted.",
        "muted_until": "🔇 {mention} has been muted for {duration}.",
        "unmuted": "🔊 {mention} has been unmuted.",
        "warned": "⚠️ {mention} has been warned ({count}/{limit}). Reason: {reason}",
        "auto_banned": "🚫 {mention} has been auto-banned after reaching the warning limit.",
        "no_target": "Reply to a message or provide @username / user_id.",
        "not_admin": "❌ You need to be an admin to use this command.",
        "bot_not_admin": "❌ I need admin rights to do that.",
        "captcha_prompt": "👋 Welcome {first_name}!\nPlease verify you are human by pressing the button below within 60 seconds.",
        "captcha_button": "✅ I am human",
        "captcha_success": "✅ {first_name} passed the CAPTCHA!",
        "captcha_timeout_kick": "⏰ {user_id} was removed for not completing the CAPTCHA in time.",
        "flood_muted": "🔇 {mention} muted for flooding.",
        "bad_word_deleted": "🚫 Bad word detected — message removed.",
    },
    "es": {
        "welcome": "¡Bienvenido/a {first_name} a {group_name}!",
        "farewell": "¡Hasta luego {first_name}! Te echaremos de menos.",
        "no_rules": "Todavía no se han establecido reglas para este grupo.",
        "rules_header": "📋 Reglas de {group_name}:",
        "banned": "🚫 {mention} ha sido baneado/a.",
        "banned_reason": "🚫 {mention} ha sido baneado/a.\nMotivo: {reason}",
        "unbanned": "✅ El usuario {user_id} ha sido desbaneado.",
        "kicked": "👢 {mention} ha sido expulsado/a.",
        "muted": "🔇 {mention} ha sido silenciado/a.",
        "muted_until": "🔇 {mention} ha sido silenciado/a por {duration}.",
        "unmuted": "🔊 {mention} ya puede escribir.",
        "warned": "⚠️ {mention} ha recibido un aviso ({count}/{limit}). Motivo: {reason}",
        "auto_banned": "🚫 {mention} ha sido baneado/a automáticamente tras alcanzar el límite de avisos.",
        "no_target": "Responde a un mensaje o proporciona @usuario / user_id.",
        "not_admin": "❌ Necesitas ser administrador para usar este comando.",
        "bot_not_admin": "❌ Necesito permisos de administrador para hacer eso.",
        "captcha_prompt": "👋 ¡Bienvenido/a {first_name}!\nPor favor, verifica que eres humano pulsando el botón en 60 segundos.",
        "captcha_button": "✅ Soy humano",
        "captcha_success": "✅ {first_name} pasó el CAPTCHA.",
        "captcha_timeout_kick": "⏰ {user_id} fue eliminado por no completar el CAPTCHA a tiempo.",
        "flood_muted": "🔇 {mention} silenciado/a por spam.",
        "bad_word_deleted": "🚫 Palabra prohibida detectada — mensaje eliminado.",
    },
}

_DEFAULT_LANG = "en"


def t(key: str, lang: str = "en", **kwargs: str) -> str:
    """Return a translated string, falling back to English."""
    lang = lang if lang in _STRINGS else _DEFAULT_LANG
    template = _STRINGS[lang].get(key) or _STRINGS[_DEFAULT_LANG].get(key, key)
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


SUPPORTED_LANGS = list(_STRINGS.keys())
