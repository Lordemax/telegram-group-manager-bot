#!/usr/bin/env python3
"""Entry point — starts the bot using long polling."""
import asyncio
import logging
import signal
import sys

logger = logging.getLogger(__name__)


async def _main():
    try:
        from bot.main import build_application
    except RuntimeError as e:
        print(f"\n[ERROR] {e}\n", file=sys.stderr)
        sys.exit(1)

    app = build_application()
    logger.info("Starting bot (long polling)…")

    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(
            allowed_updates=["message", "callback_query", "chat_member", "inline_query"],
            drop_pending_updates=True,
        )

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def _signal_handler():
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)

        await stop_event.wait()

        await app.updater.stop()
        await app.stop()


def main():
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )
    asyncio.run(_main())


if __name__ == "__main__":
    main()
