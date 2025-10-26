"""Split bill handling."""

import re
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from loguru import logger

from bot.services.user_service import UserService
from bot.services.transaction_service import TransactionService
from bot.services.debt_service import DebtService
from bot.states import SplitBill
from bot.keyboards import (
    currency_keyboard,
    category_keyboard,
    skip_note_keyboard as kb_skip_note,
)
from bot.keyboards.split_bill import split_type_keyboard
from models.categories import TransactionType
from models.transactions import TransactionTypeEnum
from core.config import settings
from core.fx_rates import fx_service
from models.users import User

router = Router()


@router.message(Command("split"))
async def cmd_split(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handle /split command - start split bill flow.
    
    Usage:
        /split <amount> - Start splitting a bill with a specific amount
        /split - Start split bill flow and ask for amount
    
    Args:
        message: Telegram message
        state: FSM context
        session: Database session
    """
    # Parse command arguments
    command_parts = message.text.strip().split(maxsplit=1)
    
    if len(command_parts) > 1:
        # Amount provided in command
        try:
            amount = float(command_parts[1])
            await state.update_data(amount=amount)
            await state.set_state(SplitBill.waiting_currency)
            
            # Get user and recent currencies
            user = await UserService.get_or_create_user(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                session=session,
            )
            
            recent_currencies = await UserService.get_recent_currencies(user, session)
            
            # Show currency selection
            keyboard = currency_keyboard(
                recent_currencies=recent_currencies,
                default_currency=user.default_currency,
                supported_currencies=settings.currencies_list,
            )
            
            await message.answer(
                f"💸 Splitting bill: <b>{amount}</b>\n\n"
                f"Select currency:",
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return
        except ValueError:
            # Invalid amount
            pass
    
    # No amount provided - ask for it
    await state.set_state(SplitBill.waiting_amount)
    await message.answer(
        "💸 Split Bill\n\n"
        "Send the total bill amount:"
    )


@router.message(SplitBill.waiting_amount, F.text.regexp(r"^\d+(\.\d{1,2})?$"))
async def handle_split_amount(message: Message, state: FSMContext, session: AsyncSession):
    """Handle amount input for split bill."""
    amount = float(message.text)
    
    await state.update_data(amount=amount)
    await state.set_state(SplitBill.waiting_currency)
    
    # Get user and recent currencies
    user = await UserService.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        session=session,
    )
    
    recent_currencies = await UserService.get_recent_currencies(user, session)
    
    # Show currency selection
    keyboard = currency_keyboard(
        recent_currencies=recent_currencies,
        default_currency=user.default_currency,
        supported_currencies=settings.currencies_list,
    )
    
    await message.answer(
        f"💸 Splitting bill: <b>{amount}</b>\n\n"
        f"Select currency:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(SplitBill.waiting_currency, F.data.startswith("currency:"))
async def handle_split_currency(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Handle currency selection for split bill."""
    currency = callback.data.split(":")[1]
    
    await state.update_data(currency=currency)
    await state.set_state(SplitBill.waiting_category)
    
    # Get expense categories
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    categories = await TransactionService.get_categories(
        TransactionType.EXPENSE.value,
        user,
        session,
    )
    
    keyboard = category_keyboard(categories)
    
    data = await state.get_data()
    amount = data["amount"]
    
    await callback.message.edit_text(
        f"💸 Splitting bill: <b>{amount} {currency}</b>\n\n"
        f"Select category:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(SplitBill.waiting_currency, F.data == "other_currency")
async def handle_split_other_currency(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Handle 'Other Currency' button."""
    await state.set_state(SplitBill.waiting_custom_currency)
    
    data = await state.get_data()
    amount = data["amount"]
    
    await callback.message.edit_text(
        f"💸 Splitting bill: <b>{amount}</b>\n\n"
        f"Please enter a 3-letter currency code (e.g., JPY, GBP, CHF):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(SplitBill.waiting_custom_currency)
async def handle_split_custom_currency(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    """Handle custom currency input."""
    currency = message.text.strip().upper()
    
    # Validate format
    if not re.match(r"^[A-Z]{3}$", currency):
        await message.answer(
            "❌ Invalid format. Please enter a valid 3-letter currency code:",
        )
        return
    
    # Validate currency
    try:
        await fx_service.get_rates_for_transaction(currency, session)
    except ValueError:
        user = await UserService.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            session=session,
        )
        recent_currencies = await UserService.get_recent_currencies(user, session)
        keyboard = currency_keyboard(
            recent_currencies=recent_currencies,
            default_currency=user.default_currency,
            supported_currencies=settings.currencies_list,
        )
        
        await message.answer(
            f"❌ Currency <b>{currency}</b> is not supported.\n\n"
            f"Please select another currency:",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        await state.set_state(SplitBill.waiting_currency)
        return
    
    await state.update_data(currency=currency)
    await state.set_state(SplitBill.waiting_category)
    
    # Get categories
    user = await UserService.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        session=session,
    )
    
    categories = await TransactionService.get_categories(
        TransactionType.EXPENSE.value,
        user,
        session,
    )
    
    keyboard = category_keyboard(categories)
    
    data = await state.get_data()
    amount = data["amount"]
    
    # Send message with categories
    sent_msg = await message.answer(
        f"💸 Splitting bill: <b>{amount} {currency}</b>\n\n"
        f"Select category:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(SplitBill.waiting_category, F.data.startswith("category:"))
async def handle_split_category(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Handle category selection."""
    category_id = int(callback.data.split(":")[1])
    
    await state.update_data(category_id=category_id)
    await state.set_state(SplitBill.waiting_split_type)
    
    keyboard = split_type_keyboard()
    
    data = await state.get_data()
    amount = data["amount"]
    currency = data["currency"]
    
    await callback.message.edit_text(
        f"💸 Bill: <b>{amount} {currency}</b>\n\n"
        f"How to split it?",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(SplitBill.waiting_split_type, F.data == "split:half")
async def handle_split_half(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Handle 50/50 split."""
    data = await state.get_data()
    amount = data["amount"]
    
    # Calculate split
    other_amount = amount / 2
    
    await state.update_data(other_amount=other_amount)
    await state.set_state(SplitBill.waiting_other_user)
    
    await callback.message.edit_text(
        f"💸 Bill: <b>{amount}</b>\n"
        f"🔀 You pay: <b>{amount - other_amount:.2f}</b>\n"
        f"🔀 They pay: <b>{other_amount:.2f}</b>\n\n"
        f"Who are you splitting with?\n\n"
        f"Send their Telegram @username or user ID:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(SplitBill.waiting_split_type, F.data == "split:custom")
async def handle_split_custom(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Handle custom split amount."""
    await state.set_state(SplitBill.waiting_custom_amount)
    
    data = await state.get_data()
    amount = data["amount"]
    
    await callback.message.edit_text(
        f"💸 Total bill: <b>{amount}</b>\n\n"
        f"How much should the other person pay?",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(SplitBill.waiting_custom_amount)
async def handle_custom_split_amount(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    """Handle custom split amount input."""
    try:
        other_amount = float(message.text)
        
        data = await state.get_data()
        total_amount = data["amount"]
        
        if other_amount <= 0 or other_amount >= total_amount:
            await message.answer(
                f"❌ Invalid amount. It must be between 0 and {total_amount}."
                f"\n\nPlease try again:"
            )
            return
        
        await state.update_data(other_amount=other_amount)
        await state.set_state(SplitBill.waiting_other_user)
        
        await message.answer(
            f"💸 Bill: <b>{total_amount}</b>\n"
            f"🔀 You pay: <b>{total_amount - other_amount:.2f}</b>\n"
            f"🔀 They pay: <b>{other_amount:.2f}</b>\n\n"
            f"Who are you splitting with?\n\n"
            f"Send their Telegram @username or user ID:",
            parse_mode="HTML",
        )
    except ValueError:
        await message.answer("❌ Please enter a valid number.")


@router.message(SplitBill.waiting_other_user)
async def handle_other_user(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
):
    """Handle other user identification."""
    debtor_user = None
    telegram_id = None
    username = None
    
    # Check if this is a forwarded message - extract user from forward info
    if message.forward_from:
        telegram_id = message.forward_from.id
        username = message.forward_from.username
        logger.info(f"Received forwarded message from user {telegram_id} (@{username})")
        debtor_user = await UserService.get_user_by_telegram_id(telegram_id, session)
    elif message.forward_from_chat:
        # Forwarded from a chat/channel - not a user
        await message.answer(
            "❌ This is a forwarded message from a chat or channel. Please forward a message from a <b>user</b> instead.",
            parse_mode="HTML"
        )
        return
    else:
        # Regular text message
        user_input = message.text.strip()
        
        # Parse username or user ID
        if user_input.startswith("@"):
            username = user_input[1:]
            # Try to find user in database (case-insensitive)
            stmt = select(User).where(func.lower(User.username) == func.lower(username))
            result = await session.execute(stmt)
            debtor_user = result.scalar_one_or_none()
            
            if debtor_user:
                telegram_id = debtor_user.telegram_id
                logger.info(f"Found user by username @{username}: {telegram_id}")
            else:
                # User not in database, prompt for user ID
                logger.info(f"User @{username} not found in database")
                await message.answer(
                    f"❌ User @{username} not found in the bot's database.\n\n"
                    f"Please provide their <b>Telegram user ID</b> instead.\n\n"
                    f"<b>How to find their ID:</b>\n"
                    f"1. Ask them to send /start to this bot\n"
                    f"2. Or ask them to message @userinfobot and share their ID\n"
                    f"3. Or forward a message from them\n\n"
                    f"Send their Telegram ID (numeric):",
                    parse_mode="HTML"
                )
                return
        else:
            try:
                telegram_id = int(user_input)
                debtor_user = await UserService.get_user_by_telegram_id(telegram_id, session)
            except ValueError:
                await message.answer(
                    "❌ Invalid format. Send @username, user ID, or forward a message from the user.\n\n"
                    "Try again:"
                )
                return
    
    # If user doesn't exist, try to create them with minimal info
    # This allows us to store the debt and notify them when they start the bot
    if not debtor_user and telegram_id:
        try:
            # Check if user exists in Telegram (optional validation)
            telegram_user = await bot.get_chat(telegram_id)
            if telegram_user:
                debtor_user = await UserService.get_or_create_user(
                    telegram_id=telegram_id,
                    username=telegram_user.username,
                    session=session,
                )
                logger.info(f"Created placeholder user for telegram_id: {telegram_id}")
        except Exception as e:
            logger.warning(f"Could not create user for telegram_id {telegram_id}: {e}")
            await message.answer(
                "❌ Could not find or create user. Please check the Telegram ID or username.\n\n"
                "Make sure the user ID is correct."
            )
            return
    
    if not debtor_user:
        await message.answer(
            "❌ Could not find user. Please check the username or ID."
        )
        return
    
    # Store debtor user in state
    await state.update_data(debtor_user_id=debtor_user.telegram_id)
    await state.set_state(SplitBill.waiting_note)
    
    # Create custom keyboard with split-specific callback
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Skip", callback_data="split:skip_note")]
    ])
    
    data = await state.get_data()
    amount = data["amount"]
    currency = data["currency"]
    
    await message.answer(
        f"💸 Splitting <b>{amount} {currency}</b> with {username if 'username' in locals() else f'user {telegram_id}'}\n\n"
        f"Add a note (optional):",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.message(SplitBill.waiting_note)
async def handle_split_note(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
):
    """Handle note input and complete split bill."""
    note = message.text
    
    data = await state.get_data()
    amount = data["amount"]
    currency = data["currency"]
    category_id = data["category_id"]
    other_amount = data["other_amount"]
    debtor_user_id = data["debtor_user_id"]
    
    # Get users
    creditor = await UserService.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        session=session,
    )
    
    debtor = await UserService.get_user_by_telegram_id(debtor_user_id, session)
    
    # Create transaction for full amount (creditor paid)
    transaction = await TransactionService.create_transaction(
        user=creditor,
        amount=amount,
        currency=currency,
        transaction_type=TransactionTypeEnum.EXPENSE,
        category_id=category_id,
        note=f"Split bill: {note}",
        session=session,
    )
    
    # Create debt for the other person's share
    debt = await DebtService.create_debt(
        creditor=creditor,
        debtor=debtor,
        amount=other_amount,
        currency=currency,
        category_id=category_id,
        note=note,
        related_transaction_id=transaction.id,
        session=session,
    )
    
    await state.clear()
    
    # Notify debtor
    notification_sent = False
    try:
        await bot.send_message(
            chat_id=debtor.telegram_id,
            text=(
                f"💸 You have a new debt!\n\n"
                f"Amount: <b>{other_amount:.2f} {currency}</b>\n"
                f"Creditor: {creditor.username or f'User {creditor.telegram_id}'}\n"
                f"Note: {note if note else 'No note'}\n\n"
                f"Use /debts to see all your debts."
            ),
            parse_mode="HTML"
        )
        notification_sent = True
    except Exception as e:
        logger.warning(f"Could not notify debtor {debtor.telegram_id}: {e}")
    
    # Build response message
    response_text = (
        f"✅ Bill split!\n\n"
        f"💸 Total: <b>{amount:.2f} {currency}</b>\n"
        f"🔀 You paid: <b>{amount - other_amount:.2f} {currency}</b>\n"
        f"🔀 They owe: <b>{other_amount:.2f} {currency}</b>\n"
        f"📝 Note: {note}\n"
    )
    
    if not notification_sent:
        response_text += f"\n⚠️ Debtor hasn't started the bot yet. They'll be notified when they do.\n"
    
    response_text += (
        f"🆔 Transaction ID: <code>{transaction.id}</code>\n"
        f"🆔 Debt ID: <code>{debt.id}</code>"
    )
    
    await message.answer(response_text, parse_mode="HTML")


@router.callback_query(SplitBill.waiting_note, F.data == "split:skip_note")
async def handle_split_skip_note(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
):
    """Handle skipping note and complete split bill."""
    data = await state.get_data()
    amount = data["amount"]
    currency = data["currency"]
    category_id = data["category_id"]
    other_amount = data["other_amount"]
    debtor_user_id = data["debtor_user_id"]
    
    # Get users
    creditor = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    debtor = await UserService.get_user_by_telegram_id(debtor_user_id, session)
    
    # Create transaction for full amount
    transaction = await TransactionService.create_transaction(
        user=creditor,
        amount=amount,
        currency=currency,
        transaction_type=TransactionTypeEnum.EXPENSE,
        category_id=category_id,
        note=None,
        session=session,
    )
    
    # Create debt
    debt = await DebtService.create_debt(
        creditor=creditor,
        debtor=debtor,
        amount=other_amount,
        currency=currency,
        category_id=category_id,
        note=None,
        related_transaction_id=transaction.id,
        session=session,
    )
    
    await state.clear()
    
    # Notify debtor
    notification_sent = False
    try:
        await bot.send_message(
            chat_id=debtor.telegram_id,
            text=(
                f"💸 You have a new debt!\n\n"
                f"Amount: <b>{other_amount:.2f} {currency}</b>\n"
                f"Creditor: {creditor.username or f'User {creditor.telegram_id}'}\n\n"
                f"Use /debts to see all your debts."
            ),
            parse_mode="HTML"
        )
        notification_sent = True
    except Exception as e:
        logger.warning(f"Could not notify debtor {debtor.telegram_id}: {e}")
    
    # Build response message
    response_text = (
        f"✅ Bill split!\n\n"
        f"💸 Total: <b>{amount:.2f} {currency}</b>\n"
        f"🔀 You paid: <b>{amount - other_amount:.2f} {currency}</b>\n"
        f"🔀 They owe: <b>{other_amount:.2f} {currency}</b>\n"
    )
    
    if not notification_sent:
        response_text += f"\n⚠️ Debtor hasn't started the bot yet. They'll be notified when they do.\n"
    
    response_text += (
        f"🆔 Transaction ID: <code>{transaction.id}</code>\n"
        f"🆔 Debt ID: <code>{debt.id}</code>"
    )
    
    await callback.message.edit_text(response_text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(SplitBill.waiting_split_type, F.data == "split:cancel")
async def handle_split_cancel(callback: CallbackQuery, state: FSMContext):
    """Cancel split bill flow."""
    await state.clear()
    await callback.message.edit_text("❌ Split bill cancelled.")
    await callback.answer()

