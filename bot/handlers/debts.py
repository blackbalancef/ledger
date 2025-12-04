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
from bot.states import SettleDebt, NetDebtCancellation
from models.users import User
from sqlalchemy import select

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
    
    # Check for mutual debts and show net calculations
    mutual_debts_info = []
    
    # Get all unique users we have debts with
    other_user_ids = set()
    for debt in debts:
        if debt.creditor_user_id == user.id:
            other_user_ids.add(debt.debtor_user_id)
        else:
            other_user_ids.add(debt.creditor_user_id)
    
    # Check each user for mutual debts
    for other_user_id in other_user_ids:
        stmt = select(User).where(User.id == other_user_id)
        result = await session.execute(stmt)
        other_user = result.scalar_one_or_none()
        
        if other_user:
            # Calculate net in EUR
            net_eur = await DebtService.calculate_net_debts(user, other_user, session, "EUR")
            net_usd = await DebtService.calculate_net_debts(user, other_user, session, "USD")
            
            # Only show if there are mutual debts (both directions)
            if len(net_eur["debts_to_cancel"]) > 1:
                other_name = other_user.username or f"User {other_user.telegram_id}"
                if abs(net_eur["net_amount"]) < 0.01:
                    net_text = "✅ Balanced! (No net debt)"
                elif net_eur["net_amount"] > 0:
                    net_text = f"You owe {abs(net_eur['net_amount']):.2f} EUR"
                else:
                    net_text = f"They owe you {abs(net_eur['net_amount']):.2f} EUR"
                
                mutual_debts_info.append({
                    "user": other_user,
                    "net_eur": net_eur,
                    "net_usd": net_usd,
                    "text": net_text,
                })
    
    # Show net calculations if any
    if mutual_debts_info:
        text += "🔄 <b>Mutual Debts (Net):</b>\n"
        for info in mutual_debts_info:
            other_name = info["user"].username or f"User {info['user'].telegram_id}"
            text += f"\n👤 {other_name}:\n"
            text += f"  • {info['text']}\n"
            text += f"  • ({abs(info['net_usd']['net_amount']):.2f} USD)\n"
        text += "\n"
    
    # Build keyboard
    buttons = []
    if debts:
        buttons.append([InlineKeyboardButton(text="💚 Settle a debt", callback_data="settle:show_list")])
    
    # Add cancel mutual debts buttons
    for info in mutual_debts_info:
        other_name = info["user"].username or f"User {info['user'].telegram_id}"
        buttons.append([
            InlineKeyboardButton(
                text=f"🔄 Cancel mutual debts with {other_name[:20]}",
                callback_data=f"net_debt:show:{info['user'].id}:EUR"
            )
        ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    
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


@router.callback_query(F.data.startswith("net_debt:show:"))
async def handle_show_net_calculation(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Show detailed net debt calculation."""
    # Parse callback data: net_debt:show:user_id:base_currency
    parts = callback.data.split(":")
    other_user_id = int(parts[2])
    base_currency = parts[3] if len(parts) > 3 else "EUR"
    
    # Get users
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    stmt = select(User).where(User.id == other_user_id)
    result = await session.execute(stmt)
    other_user = result.scalar_one_or_none()
    
    if not other_user:
        await callback.answer("❌ User not found!", show_alert=True)
        return
    
    # Calculate net debts
    calculation = await DebtService.calculate_net_debts(user, other_user, session, base_currency)
    
    if len(calculation["debts_to_cancel"]) < 2:
        await callback.answer("❌ No mutual debts to cancel!", show_alert=True)
        return
    
    # Build detailed calculation text
    other_name = other_user.username or f"User {other_user.telegram_id}"
    text = f"🔄 <b>Net Debt Calculation</b>\n\n"
    text += f"Between you and <b>{other_name}</b>\n\n"
    text += f"<b>Debts to cancel:</b>\n"
    
    for i, item in enumerate(calculation["breakdown"], 1):
        debt = item["debt"]
        if item["direction"] == "user1_owes_user2":
            direction_text = f"You owe {other_name}"
        else:
            direction_text = f"{other_name} owes you"
        
        text += (
            f"\n{i}. {direction_text}\n"
            f"   Amount: <b>{item['amount_original']:.2f} {item['currency']}</b>\n"
            f"   = {item['amount_base']:.2f} {base_currency}\n"
        )
    
    text += f"\n<b>Calculation:</b>\n"
    text += f"Total you owe: {calculation['total_user1_owes']:.2f} {base_currency}\n"
    text += f"Total they owe: {calculation['total_user2_owes']:.2f} {base_currency}\n"
    text += f"\n<b>Net result:</b> "
    
    if abs(calculation["net_amount"]) < 0.01:
        text += "✅ <b>Balanced! (No net debt)</b>"
    elif calculation["net_amount"] > 0:
        text += f"💸 <b>You owe {calculation['net_amount']:.2f} {base_currency}</b>"
    else:
        text += f"💰 <b>They owe you {abs(calculation['net_amount']):.2f} {base_currency}</b>"
    
    # Add confirmation button
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Confirm cancellation",
                callback_data=f"net_debt:confirm:{other_user_id}:{base_currency}"
            ),
            InlineKeyboardButton(
                text="❌ Cancel",
                callback_data="net_debt:cancel"
            ),
        ]
    ])
    
    await state.set_state(NetDebtCancellation.confirming)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("net_debt:confirm:"))
async def handle_confirm_net_cancellation(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
):
    """Execute net debt cancellation."""
    # Parse callback data: net_debt:confirm:user_id:base_currency
    parts = callback.data.split(":")
    other_user_id = int(parts[2])
    base_currency = parts[3] if len(parts) > 3 else "EUR"
    
    # Get users
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    stmt = select(User).where(User.id == other_user_id)
    result = await session.execute(stmt)
    other_user = result.scalar_one_or_none()
    
    if not other_user:
        await callback.answer("❌ User not found!", show_alert=True)
        return
    
    try:
        # Get calculation before cancellation for notification
        calculation_before = await DebtService.calculate_net_debts(user, other_user, session, base_currency)
        
        # Cancel mutual debts
        result = await DebtService.cancel_mutual_debts(user, other_user, base_currency, session)
        
        # Build notification text for other user
        other_name = other_user.username or f"User {other_user.telegram_id}"
        user_name = user.username or f"User {user.telegram_id}"
        
        notification_text = (
            f"🔄 <b>Mutual Debts Cancelled</b>\n\n"
            f"<b>{user_name}</b> has cancelled mutual debts with you.\n\n"
            f"<b>Cancelled debts:</b> {len(result['cancelled_debts'])}\n\n"
        )
        
        # Show calculation breakdown
        notification_text += "<b>Calculation breakdown:</b>\n"
        for item in calculation_before["breakdown"]:
            debt = item["debt"]
            if item["direction"] == "user1_owes_user2":
                direction_text = f"{user_name} owes you"
            else:
                direction_text = f"You owe {user_name}"
            
            notification_text += (
                f"• {direction_text}: {item['amount_original']:.2f} {item['currency']} "
                f"({item['amount_base']:.2f} {base_currency})\n"
            )
        
        notification_text += f"\n<b>Net result:</b> "
        
        if result["net_debt"]:
            if result["net_debt"].debtor_user_id == other_user.id:
                notification_text += f"💸 <b>You owe {float(result['net_debt'].amount):.2f} {result['net_debt'].currency}</b>\n\n"
            else:
                notification_text += f"💰 <b>They owe you {float(result['net_debt'].amount):.2f} {result['net_debt'].currency}</b>\n\n"
            
            notification_text += (
                f"✅ A new net debt has been created.\n"
                f"🆔 Debt ID: <code>{result['net_debt'].id}</code>"
            )
        else:
            notification_text += "✅ <b>All debts cancelled! (Net is zero)</b>"
        
        # Notify other user
        try:
            await bot.send_message(
                chat_id=other_user.telegram_id,
                text=notification_text,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Could not notify user {other_user.telegram_id}: {e}")
        
        # Show confirmation to initiator
        confirmation_text = (
            f"✅ <b>Mutual debts cancelled!</b>\n\n"
            f"Cancelled <b>{len(result['cancelled_debts'])}</b> debt(s)\n"
        )
        
        if result["net_debt"]:
            confirmation_text += (
                f"\nCreated net debt:\n"
                f"Amount: <b>{float(result['net_debt'].amount):.2f} {result['net_debt'].currency}</b>\n"
                f"🆔 Debt ID: <code>{result['net_debt'].id}</code>\n\n"
                f"✅ {other_name} has been notified."
            )
        else:
            confirmation_text += "\n✅ All debts balanced! No net debt created."
        
        await callback.message.edit_text(confirmation_text, parse_mode="HTML")
        await state.clear()
        await callback.answer("✅ Cancellation completed!")
        
    except Exception as e:
        logger.error(f"Error cancelling mutual debts: {e}")
        await callback.answer("❌ Error cancelling debts. Please try again.", show_alert=True)




@router.callback_query(F.data == "net_debt:cancel")
async def handle_cancel_net_debt(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Cancel net debt calculation."""
    await state.clear()
    await callback.message.edit_text("❌ Cancellation cancelled.")
    await callback.answer()

