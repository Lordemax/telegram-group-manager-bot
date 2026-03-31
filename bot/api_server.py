"""aiohttp REST API server — exposes bot data for the web dashboard."""
import logging
import os

from aiohttp import web

from bot.database import (
    add_bad_word,
    clear_warnings,
    get_all_groups,
    get_all_warnings,
    get_bad_words,
    get_group_config,
    get_warnings,
    remove_bad_word,
    set_group_field,
)
from bot.i18n import SUPPORTED_LANGS

logger = logging.getLogger(__name__)

PORT = int(os.environ.get("BOT_API_PORT", os.environ.get("PORT", 8081)))

routes = web.RouteTableDef()


def _cors_headers() -> dict:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


@routes.options("/{path_info:.*}")
async def options_handler(request: web.Request) -> web.Response:
    return web.Response(headers=_cors_headers())


@routes.get("/api/health")
async def health(_: web.Request) -> web.Response:
    return web.json_response(
        {"status": "ok", "service": "telegram-group-manager-bot"},
        headers=_cors_headers(),
    )


@routes.get("/api/meta")
async def meta(_: web.Request) -> web.Response:
    return web.json_response(
        {"supported_langs": SUPPORTED_LANGS, "version": "1.0.0"},
        headers=_cors_headers(),
    )


@routes.get("/api/groups")
async def list_groups(_: web.Request) -> web.Response:
    groups = await get_all_groups()
    return web.json_response(groups, headers=_cors_headers())


@routes.get("/api/groups/{chat_id}")
async def get_group(request: web.Request) -> web.Response:
    chat_id = int(request.match_info["chat_id"])
    config = await get_group_config(chat_id)
    if not config:
        raise web.HTTPNotFound(reason="Group not found")
    return web.json_response(config, headers=_cors_headers())


@routes.patch("/api/groups/{chat_id}")
async def update_group(request: web.Request) -> web.Response:
    chat_id = int(request.match_info["chat_id"])
    body = await request.json()
    updated = {}
    for field, value in body.items():
        try:
            await set_group_field(chat_id, field, value)
            updated[field] = value
        except ValueError as e:
            raise web.HTTPBadRequest(reason=str(e))
    return web.json_response({"updated": updated}, headers=_cors_headers())


@routes.get("/api/groups/{chat_id}/warnings")
async def list_warnings(request: web.Request) -> web.Response:
    chat_id = int(request.match_info["chat_id"])
    user_id_param = request.rel_url.query.get("user_id")
    if user_id_param:
        warnings = await get_warnings(chat_id, int(user_id_param))
    else:
        warnings = await get_all_warnings(chat_id)
    return web.json_response(warnings, headers=_cors_headers())


@routes.delete("/api/groups/{chat_id}/warnings/{user_id}")
async def delete_warnings(request: web.Request) -> web.Response:
    chat_id = int(request.match_info["chat_id"])
    user_id = int(request.match_info["user_id"])
    await clear_warnings(chat_id, user_id)
    return web.json_response({"cleared": True}, headers=_cors_headers())


@routes.get("/api/groups/{chat_id}/badwords")
async def list_badwords(request: web.Request) -> web.Response:
    chat_id = int(request.match_info["chat_id"])
    words = await get_bad_words(chat_id)
    return web.json_response(words, headers=_cors_headers())


@routes.post("/api/groups/{chat_id}/badwords")
async def add_badword(request: web.Request) -> web.Response:
    chat_id = int(request.match_info["chat_id"])
    body = await request.json()
    word = body.get("word", "").strip()
    if not word:
        raise web.HTTPBadRequest(reason="'word' field is required")
    await add_bad_word(chat_id, word)
    return web.json_response({"added": word}, headers=_cors_headers())


@routes.delete("/api/groups/{chat_id}/badwords/{word}")
async def delete_badword(request: web.Request) -> web.Response:
    chat_id = int(request.match_info["chat_id"])
    word = request.match_info["word"]
    await remove_bad_word(chat_id, word)
    return web.json_response({"removed": word}, headers=_cors_headers())


async def build_app() -> web.Application:
    app = web.Application()
    app.add_routes(routes)
    return app


async def start_api_server():
    app = await build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("REST API server listening on port %d", PORT)
    return runner
