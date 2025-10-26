"""Debt management handlers."""

from uuid import UUID
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from bot.services.user_service import UserService
from bot.services.debt_service import DebtService
from bot.services.transaction_service import TransactionService
from bot.states import SettleDebt

router = Router()


@router.message(Command("debts"))
async def cmd_debts(message: Message, session: AsyncSession):
    """
    Handle /debts command - show debt summary.
    
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
    
    # Get debt summary
    summary = await DebtService.get_debt_summary(user, session)
    
    # Get all debts for inline buttons
    debts = await DebtService.get_user_debts(user, session, only_unsettled=True)
    
    # Format output
    text = "💸 <b>Debt Summary</b>\n\n"
    
    owed_to_me = summary["owed_to_me"]
    i_owe = summary["i_owe"]
    
    if not owed_to_me and not i_owe:
        text = "✅ <b>No outstanding debts!</b>"
        await message.answer(text, parse_mode="HTML")
        return
    
    # Who owes me
    if owed_to_me:
        text += "💰 <b>Money owed to you:</b>\n"
        for person, currencies in owed_to_me.items():
            text += f"\n👤 {person}:\n"
            for currency, amount in currencies.items():
                text += f"  • {amount:.2f} {currency}\n"
        text += "\n"
    
    # Who I owe
    if i_owe:
        text += "💸 <b>What you owe:</b>\n"
        for person, currencies in i_owe.items():
            text += f"\n👤 {person}:\n"
            for currency, amount in currencies.items():
                text += f"  • {amount:.2f} {currency}\n"
        text += "\n"
    
    # Add settle button if there are unsettled debts
    keyboard = None
    if debts:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💚 Settle a debt", callback_data="settle:show_list")],
        ])
    
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.message(Command("settle"))
async def cmd_settle(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handle /settle command - show debt list for settling.
    
    Args:
        message: Telegram message
        state: FSM context
        session: Database session
    """
    # Get user
    user = await UserService.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        session=session,
    )
    
    # Get all unsettled debts
    debts = await DebtService.get_user_debts(user, session, only_unsettled=True)
    
    if not debts:
        await message.answer("✅ <b>No outstanding debts to settle!</b>", parse_mode="HTML")
        await state.clear()
        return
    
    # Create list of debts with settle buttons
    text = "💸 <b>Unsettled Debts</b>\n\n"
    text += "Select a debt to settle:\n\n"
    
    buttons = []
    for i, debt in enumerate(debts, 1):
        # Determine direction
        is_creditor = debt.creditor_user_id == user.id
        other_person = debt.debtor.username if is_creditor else debt.creditor.username
        other_person = other_person or f"User {debt.debtor.telegram_id if is_creditor else debt.creditor.telegram_id}"
        
        direction = "owes you" if is_creditor else "you owe"
        
        text += (
            f"{i}. {direction.capitalize()}: <b>{float(debt.amount):.2f} {debt.currency}</b>\n"
            f"   👤 {other_person}\n"
        )
        
        buttons.append([
            InlineKeyboardButton(
                text=f"Settle #{i}: {float(debt.amount):.2f} {debt.currency}",
                callback_data=f"settle:debt:{debt.id}"
            )
        ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await state.set_state(SettleDebt.selecting_debt)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "settle:show_list")
async def handle_settle_show_list(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Show debt list from inline button."""
    # Get user
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    # Get all unsettled debts
    debts = await DebtService.get_user_debts(user, session, only_unsettled=True)
    
    if not debts:
        await callback.message.edit_text("✅ <b>No outstanding debts!</b>", parse_mode="HTML")
        await state.clear()
        await callback.answer()
        return
    
    # Create list of debts with settle buttons
    text = "💸 <b>Unsettled Debts</b>\n\n"
    text += "Select a debt to settle:\n\n"
    
    buttons = []
    for i, debt in enumerate(debts, 1):
        # Determine direction
        is_creditor = debt.creditor_user_id == user.id
        other_person = debt.debtor.username if is_creditor else debt.creditor.username
        other_person = other_person or f"User {debt.debtor.telegram_id if is_creditor else debt.creditor.telegram_id}"
        
        direction = "owes you" if is_creditor else "you owe"
        
        text += (
            f"{i}. {direction.capitalize()}: <b>{float(debt.amount):.2f} {debt.currency}</b>\n"
            f"   👤 {other_person}\n"
        )
        
        buttons.append([
            InlineKeyboardButton(
                text=f"Settle #{i}: {float(debt.amount):.2f} {debt.currency}",
                callback_data=f"settle:debt:{debt.id}"
            )
        ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await state.set_state(SettleDebt.selecting_debt)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(SettleDebt.selecting_debt, F.data.startswith("settle:debt:"))
async def handle_settle_debt(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
):
    """
    Handle debt settlement.
    
    Args:
        callback: Callback query
        state: FSM context
        session: Database session
        bot: Bot instance
    """
    debt_id = UUID(callback.data.split(":")[-1])
    
    # Get user
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    # Get debt
    debt = await DebtService.get_debt_by_id(debt_id, user, session)
    
    if not debt:
        await callback.answer("❌ Debt not found!", show_alert=True)
        return
    
    try:
        # Settle debt (creates settlement transaction)
        settlement = await DebtService.settle_debt(debt_id, user, session)
        
        # Notify both parties
        try:
            # Notify creditor (the person who was owed)
            if debt.creditor.telegram_id != user.telegram_id:
                await bot.send_message(
                    chat_id=debt.creditor.telegram_id,
                    text=(
                        f"✅ Debt settled!\n\n"
                        f"You were owed: <b>{float(debt.amount):.2f} {debt.currency}</b>\n"
                        f"Debtor: {debt.debtor.username or f'User {debt.debtor.telegram_id}'}\n\n"
                        f"Debt ID: <code>{debt.id}</code>"
                    ),
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.warning(f"Could not notify creditor {debt.creditor.telegram_id}: {e}")
        
        try:
            # Notify debtor (the person who owed)
            if debt.debtor.telegram_id != user.telegram_id:
                await bot.send_message(
                    chat_id=debt.debtor.telegram_id,
                    text=(
                        f"✅ Debt settled!\n\n"
                        f"You owed: <b>{float(debt.amount):.2f} {debt.currency}</b>\n"
                        f"Creditor: {debt.creditor.username or f'User {debt.creditor.telegram_id}'}\n\n"
                        f"Debt ID: <code>{debt.id}</code>"
                    ),
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.warning(f"Could not notify debtor {debt.debtor.telegram_id}: {e}")
        
        # Show confirmation
        await callback.message.edit_text(
            f"✅ <b>Debt settled!</b>\n\n"
            f"Amount: <b>{float(debt.amount):.2f} {debt.currency}</b>\n"
            f"🆔 Debt ID: <code>{debt.id}</code>\n"
            f"🆔 Transaction ID: <code>{settlement.id}</code>",
            parse_mode="HTML",
        )
        await state.clear()
        await callback.answer("✅ Debt settled!")
        
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)

