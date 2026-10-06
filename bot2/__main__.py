"""Run ZC Forward Bot with: python -m zcbot"""

from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler

from pyrogram import Client, idle
from pyrogram.enums import ParseMode
from pyrogram.errors import RPCError
from pyrogram.types import BotCommand

from .config import load_settings
from .db import Database
from .engine import ForwardEngine
from .handlers import admin, forward, input, manager, settings, start
from .services import Services


def configure_logging(log_path: str) -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.handlers[:] = [console, file_handler]
    # Network library DEBUG can include request metadata; never retain it in production logs.
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)


async def expiry_worker(services: Services) -> None:
    while True:
        try:
            expired = await services.db.expire_plans()
            for user in expired:
                try:
                    await services.app.send_message(
                        int(user["_id"]),
                        "❌ Your ZC subscription has expired and your account is now on the Free plan.",
                    )
                except (OSError, RPCError):
                    logging.getLogger(__name__).debug("Could not deliver expiry notice to %s", user["_id"])
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger(__name__).exception("Plan expiry check failed")
        await asyncio.sleep(3600)


async def main() -> None:
    config = load_settings()
    config.workdir.mkdir(parents=True, exist_ok=True)
    configure_logging(str(config.workdir / "zcbot.log"))
    log = logging.getLogger(__name__)

    db = Database(config.mongo_uri, config.encryption_key)
    await db.connect()
    app = Client(
        name="zc_control",
        api_id=config.api_id,
        api_hash=config.api_hash,
        bot_token=config.bot_token,
        in_memory=True,
        workdir=str(config.workdir),
    )
    engine = ForwardEngine(config, db, app)
    services = Services(config=config, db=db, app=app, engine=engine)

    # Handler order: input flow first, then commands and feature callback groups.
    input.register(app, services)
    start.register(app, services)
    settings.register(app, services)
    manager.register(app, services)
    forward.register(app, services)
    admin.register(app, services)

    expiry_task: asyncio.Task[None] | None = None
    try:
        await app.start()
        app.set_parse_mode(ParseMode.HTML)
        await app.set_bot_commands(
            [
                BotCommand("start", "Open welcome menu"),
                BotCommand("forward", "Forward messages"),
                BotCommand("settings", "Open settings"),
                BotCommand("unequify", "Delete duplicate media"),
                BotCommand("myplan", "Show subscription"),
                BotCommand("transfer", "Transfer active plan"),
                BotCommand("cancel", "Cancel current setup"),
                BotCommand("reset", "Reset settings"),
                BotCommand("admin", "Owner administration"),
            ]
        )
        await engine.restore_jobs()
        expiry_task = asyncio.create_task(expiry_worker(services), name="zc-plan-expiry")
        log.info("ZC Forward Bot started")
        await idle()
    finally:
        if expiry_task:
            expiry_task.cancel()
            await asyncio.gather(expiry_task, return_exceptions=True)
        await engine.stop()
        await app.stop()
        await db.close()
        log.info("ZC Forward Bot stopped")


if __name__ == "__main__":
    try:
        import uvloop

        uvloop.install()
    except ImportError:
        pass
    asyncio.run(main())
