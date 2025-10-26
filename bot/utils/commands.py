"""Bot commands registration."""

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault


async def set_bot_commands(bot: Bot):
    """
    Register bot commands in Telegram.
    
    Args:
        bot: Bot instance
    """
    commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="income", description="Add income"),
        BotCommand(command="report", description="Monthly report"),
        BotCommand(command="history", description="View transaction history"),
        BotCommand(command="undo", description="Undo last transaction"),
        BotCommand(command="categories", description="Manage categories"),
        BotCommand(command="split", description="Split a bill with someone"),
        BotCommand(command="debts", description="View debts and who owes whom"),
        BotCommand(command="settle", description="Mark a debt as settled"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

