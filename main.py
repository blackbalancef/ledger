"""Main entry point for Finance Telegram Bot."""

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from core.config import settings
from core.db import close_db
from core.fx_rates import fx_service
from bot.middlewares import DbSessionMiddleware
from bot.handlers import start, expenses, income, reports, history, categories, split_bill, debts
from bot.utils import set_bot_commands
from bot.tasks.backup_tasks import start_backup_scheduler, stop_backup_scheduler


async def main():
    """Main function to run the bot."""
    logger.info("Starting Finance Bot...")

    # Initialize bot and dispatcher
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())

    # Register middlewares
    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())

    # Register routers
    dp.include_router(start.router)
    dp.include_router(income.router)  # Income must be before expenses to handle states correctly
    dp.include_router(expenses.router)
    dp.include_router(reports.router)
    dp.include_router(history.router)
    dp.include_router(categories.router)
    dp.include_router(split_bill.router)
    dp.include_router(debts.router)

    # Register bot commands
    await set_bot_commands(bot)
    logger.info("Bot commands registered")

    # Initialize FX service Redis connection
    try:
        await fx_service.init_redis()
        logger.info("Redis connection initialized")
    except Exception as e:
        logger.warning(f"Could not initialize Redis: {e}")

    # Start backup scheduler
    await start_backup_scheduler()

    try:
        # Start polling
        logger.info("Bot started successfully!")
        await dp.start_polling(bot)
    finally:
        # Cleanup
        logger.info("Shutting down bot...")
        await stop_backup_scheduler()
        await fx_service.close_redis()
        await fx_service.close_http_client()
        await close_db()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

