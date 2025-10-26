"""Transaction history and undo handlers."""

from uuid import UUID
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from bot.services.user_service import UserService
from bot.services.transaction_service import TransactionService

router = Router()


@router.message(Command("history"))
async def cmd_history(message: Message, session: AsyncSession):
    """
    Handle /history command - show recent transactions.

    Args:
        message: Telegram message
        session: Database session
    """
    # Get user
    user = await UserService.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        session=session,
    )

    # Get transaction history
    transactions = await TransactionService.get_user_history(
        user=user,
        session=session,
        limit=10,
    )

    if not transactions:
        await message.answer("📜 No transactions yet. Start by adding an expense!")
        return

    # Format history
    text = "📜 <b>Recent Transactions:</b>\n\n"

    for i, transaction in enumerate(transactions, 1):
        # Transaction type emoji
        if transaction.transaction_type.value == "expense":
            emoji = "💸"
        elif transaction.transaction_type.value == "income":
            emoji = "💰"
        elif transaction.transaction_type.value == "reversal":
            emoji = "↩️"
        else:
            emoji = "📝"

        # Category
        category = transaction.category.name if transaction.category else "No category"
        category_icon = transaction.category.icon if transaction.category else "📝"

        # Format transaction
        text += (
            f"{i}. {emoji} <b>{transaction.amount:.2f} {transaction.currency}</b>\n"
            f"   {category_icon} {category}\n"
            f"   🕐 {transaction.at_time.strftime('%Y-%m-%d %H:%M')}\n"
        )

        if transaction.note:
            text += f"   📝 {transaction.note}\n"

        text += f"   🆔 <code>{transaction.id}</code>\n\n"

    text += "\n💡 Use /undo to reverse the last transaction"

    await message.answer(text, parse_mode="HTML")


@router.message(Command("undo"))
async def cmd_undo(message: Message, session: AsyncSession):
    """
    Handle /undo command - reverse a transaction.
    
    Usage:
        /undo - reverse the last transaction
        /undo <transaction_id> - reverse a specific transaction by ID

    Args:
        message: Telegram message
        session: Database session
    """
    # Get user
    user = await UserService.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        session=session,
    )

    # Parse command arguments
    command_parts = message.text.strip().split(maxsplit=1)
    transaction_id = None
    
    if len(command_parts) > 1:
        # Transaction ID provided
        transaction_id_str = command_parts[1].strip()
        
        # Validate UUID format
        try:
            transaction_id = UUID(transaction_id_str)
        except ValueError:
            await message.answer(
                "❌ Invalid transaction ID format!\n\n"
                "Please provide a valid transaction ID or use /undo without arguments to reverse the last transaction.",
                parse_mode="HTML"
            )
            return
        
        # Fetch specific transaction
        from sqlalchemy import select
        from models.transactions import Transaction
        
        stmt = select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user.id,
        )
        result = await session.execute(stmt)
        target_transaction = result.scalar_one_or_none()
        
        if not target_transaction:
            await message.answer(
                "❌ Transaction not found or access denied!\n\n"
                f"ID: <code>{transaction_id}</code>",
                parse_mode="HTML"
            )
            return
    else:
        # No transaction ID provided - get last transaction
        transactions = await TransactionService.get_user_history(
            user=user,
            session=session,
            limit=1,
        )

        if not transactions:
            await message.answer("❌ No transactions to undo!")
            return

        target_transaction = transactions[0]
        transaction_id = target_transaction.id

    # Check if it's already a reversal
    if target_transaction.transaction_type.value == "reversal":
        await message.answer("❌ Cannot undo a reversal transaction!")
        return

    try:
        # Create reversal
        reversal = await TransactionService.reverse_transaction(
            transaction_id=transaction_id,
            user=user,
            session=session,
        )

        await message.answer(
            f"✅ Transaction reversed!\n\n"
            f"Original: <b>{target_transaction.amount:.2f} {target_transaction.currency}</b>\n"
            f"Original ID: <code>{transaction_id}</code>\n"
            f"Reversal ID: <code>{reversal.id}</code>",
            parse_mode="HTML",
        )

    except ValueError as e:
        await message.answer(f"❌ Error: {str(e)}")


@router.callback_query(F.data.startswith("undo:"))
async def handle_undo_callback(callback: CallbackQuery, session: AsyncSession):
    """
    Handle undo callback from history.

    Args:
        callback: Callback query
        session: Database session
    """
    transaction_id = UUID(callback.data.split(":")[1])

    # Get user
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )

    try:
        # Get original transaction to retrieve details
        from sqlalchemy import select
        from models.transactions import Transaction
        
        stmt = select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user.id,
        )
        result = await session.execute(stmt)
        original_transaction = result.scalar_one_or_none()
        
        if not original_transaction:
            await callback.answer("Transaction not found!", show_alert=True)
            return
        
        # Check if it's already a reversal
        if original_transaction.transaction_type.value == "reversal":
            await callback.answer("Cannot cancel a reversal transaction!", show_alert=True)
            return

        # Create reversal
        reversal = await TransactionService.reverse_transaction(
            transaction_id=transaction_id,
            user=user,
            session=session,
        )

        # Edit the original message to show cancelled status
        await callback.message.edit_text(
            f"❌ <b>Transaction Cancelled</b>\n\n"
            f"💰 Amount: <b>{original_transaction.amount:.2f} {original_transaction.currency}</b>\n"
            f"🆔 Original ID: <code>{transaction_id}</code>\n"
            f"↩️ Reversal ID: <code>{reversal.id}</code>",
            parse_mode="HTML",
        )
        await callback.answer("Transaction cancelled!")

    except ValueError as e:
        await callback.answer(f"Error: {str(e)}", show_alert=True)

