"""Start command handler."""

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from bot.services.user_service import UserService
from bot.services.debt_service import DebtService

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, bot: Bot):
    """
    Handle /start command.

    Args:
        message: Telegram message
        session: Database session
        bot: Bot instance
    """
    user = await UserService.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        session=session,
    )

    welcome_text = (
        f"👋 Welcome to Finance Bot, {message.from_user.first_name}!\n\n"
        f"I'll help you track your expenses and income.\n\n"
        f"📊 Here's what I can do:\n\n"
        f"💸 <b>Add expense:</b> Just send me a number (e.g., 1200)\n"
        f"💰 <b>Add income:</b> Use /income or send +5000\n"
        f"📈 <b>Monthly report:</b> Use /report\n"
        f"📜 <b>History:</b> Use /history to see recent transactions\n"
        f"↩️ <b>Undo:</b> Use /undo to cancel last transaction\n\n"
        f"💱 Your default currency: <b>{user.default_currency}</b>\n\n"
        f"Let's start tracking! Send me an amount to add your first expense."
    )

    await message.answer(welcome_text, parse_mode="HTML")
    
    # Check for pending debts and notify user
    try:
        pending_debts = await DebtService.get_user_debts(
            user=user,
            session=session,
            only_unsettled=True,
        )
        
        # Filter only debts where user is the debtor (owes money)
        user_is_debtor = [debt for debt in pending_debts if debt.debtor_user_id == user.id]
        
        if user_is_debtor:
            logger.info(f"User {user.telegram_id} has {len(user_is_debtor)} pending debts")
            await bot.send_message(
                chat_id=user.telegram_id,
                text=(
                    f"🔔 You have {len(user_is_debtor)} pending debt(s)!\n\n"
                    f"Use /debts to see details and settle them."
                ),
                parse_mode="HTML"
            )
    except Exception as e:
        logger.warning(f"Could not check pending debts for user {user.telegram_id}: {e}")

