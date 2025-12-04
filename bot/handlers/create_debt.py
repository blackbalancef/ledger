"""Direct debt creation handling."""

import re
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from loguru import logger

from bot.services.user_service import UserService
from bot.services.debt_service import DebtService
from bot.states import CreateDebt
from bot.keyboards import (
    currency_keyboard,
    category_keyboard,
    skip_note_keyboard,
    debt_direction_keyboard,
)
from models.categories import TransactionType
from core.config import settings
from core.fx_rates import fx_service
from models.users import User

router = Router()


@router.message(Command("debt"))
async def cmd_debt(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handle /debt command - start debt creation flow.
    
    Usage:
        /debt <amount> - Start creating a debt with a specific amount
        /debt - Start debt creation flow and ask for amount
    
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
            await state.set_state(CreateDebt.waiting_currency)
            
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
                f"💸 Creating debt: <b>{amount}</b>\n\n"
                f"Select currency:",
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return
        except ValueError:
            # Invalid amount
            pass
    
    # No amount provided - ask for it
    await state.set_state(CreateDebt.waiting_amount)
    await message.answer(
        "💸 Create Debt\n\n"
        "Send the debt amount:"
    )


@router.message(CreateDebt.waiting_amount, F.text.regexp(r"^\d+(\.\d{1,2})?$"))
async def handle_debt_amount(message: Message, state: FSMContext, session: AsyncSession):
    """Handle amount input for debt creation."""
    amount = float(message.text)
    
    await state.update_data(amount=amount)
    await state.set_state(CreateDebt.waiting_currency)
    
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
        f"💸 Creating debt: <b>{amount}</b>\n\n"
        f"Select currency:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(CreateDebt.waiting_currency, F.data.startswith("currency:"))
async def handle_debt_currency(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Handle currency selection for debt creation."""
    currency = callback.data.split(":")[1]
    
    await state.update_data(currency=currency)
    await state.set_state(CreateDebt.waiting_category)
    
    # Get expense categories
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    from bot.services.transaction_service import TransactionService
    categories = await TransactionService.get_categories(
        TransactionType.EXPENSE.value,
        user,
        session,
    )
    
    keyboard = category_keyboard(categories)
    
    data = await state.get_data()
    amount = data["amount"]
    
    await callback.message.edit_text(
        f"💸 Creating debt: <b>{amount} {currency}</b>\n\n"
        f"Select category:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(CreateDebt.waiting_currency, F.data == "other_currency")
async def handle_debt_other_currency(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Handle 'Other Currency' button."""
    await state.set_state(CreateDebt.waiting_custom_currency)
    
    data = await state.get_data()
    amount = data["amount"]
    
    await callback.message.edit_text(
        f"💸 Creating debt: <b>{amount}</b>\n\n"
        f"Please enter a 3-letter currency code (e.g., JPY, GBP, CHF):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(CreateDebt.waiting_custom_currency)
async def handle_debt_custom_currency(
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
        await state.set_state(CreateDebt.waiting_currency)
        return
    
    await state.update_data(currency=currency)
    await state.set_state(CreateDebt.waiting_category)
    
    # Get categories
    user = await UserService.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        session=session,
    )
    
    from bot.services.transaction_service import TransactionService
    categories = await TransactionService.get_categories(
        TransactionType.EXPENSE.value,
        user,
        session,
    )
    
    keyboard = category_keyboard(categories)
    
    data = await state.get_data()
    amount = data["amount"]
    
    # Send message with categories
    await message.answer(
        f"💸 Creating debt: <b>{amount} {currency}</b>\n\n"
        f"Select category:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(CreateDebt.waiting_category, F.data.startswith("category:"))
async def handle_debt_category(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Handle category selection."""
    category_id = int(callback.data.split(":")[1])
    
    await state.update_data(category_id=category_id)
    await state.set_state(CreateDebt.waiting_direction)
    
    data = await state.get_data()
    amount = data["amount"]
    currency = data["currency"]
    
    keyboard = debt_direction_keyboard()
    
    await callback.message.edit_text(
        f"💸 Creating debt: <b>{amount} {currency}</b>\n\n"
        f"Who owes whom?",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(CreateDebt.waiting_direction, F.data.startswith("debt_direction:"))
async def handle_debt_direction(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Handle debt direction selection."""
    direction = callback.data.split(":")[1]
    is_user_debtor = direction == "i_owe"
    
    await state.update_data(is_user_debtor=is_user_debtor)
    await state.set_state(CreateDebt.waiting_other_user)
    
    data = await state.get_data()
    amount = data["amount"]
    currency = data["currency"]
    
    if is_user_debtor:
        prompt = "Who do you owe this money to?"
    else:
        prompt = "Who owes you this money?"
    
    await callback.message.edit_text(
        f"💸 Creating debt: <b>{amount} {currency}</b>\n\n"
        f"{prompt}\n\n"
        f"Send their Telegram @username, user ID, or forward a message from them:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(CreateDebt.waiting_other_user)
async def handle_debt_other_user(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
):
    """Handle debtor user identification."""
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
    
    # Store other user in state
    await state.update_data(other_user_id=debtor_user.telegram_id)
    await state.set_state(CreateDebt.waiting_note)
    
    # Create keyboard with skip option
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Skip", callback_data="debt:skip_note")]
    ])
    
    data = await state.get_data()
    amount = data["amount"]
    currency = data["currency"]
    is_user_debtor = data.get("is_user_debtor", False)
    
    if is_user_debtor:
        user_label = f"👤 Creditor: {username if 'username' in locals() and username else f'User {telegram_id}'}"
    else:
        user_label = f"👤 Debtor: {username if 'username' in locals() and username else f'User {telegram_id}'}"
    
    await message.answer(
        f"💸 Creating debt: <b>{amount} {currency}</b>\n"
        f"{user_label}\n\n"
        f"Add a note (optional):",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.message(CreateDebt.waiting_note)
async def handle_debt_note(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
):
    """Handle note input and complete debt creation."""
    note = message.text
    
    data = await state.get_data()
    amount = data["amount"]
    currency = data["currency"]
    category_id = data["category_id"]
    other_user_id = data["other_user_id"]
    is_user_debtor = data.get("is_user_debtor", False)
    
    # Get users
    current_user = await UserService.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        session=session,
    )
    
    other_user = await UserService.get_user_by_telegram_id(other_user_id, session)
    
    # Determine creditor and debtor based on direction
    if is_user_debtor:
        creditor = other_user
        debtor = current_user
        direction_text = f"👤 You owe: {other_user.username or f'User {other_user.telegram_id}'}"
    else:
        creditor = current_user
        debtor = other_user
        direction_text = f"👤 Debtor: {other_user.username or f'User {other_user.telegram_id}'}"
    
    # Create debt
    debt = await DebtService.create_debt(
        creditor=creditor,
        debtor=debtor,
        amount=amount,
        currency=currency,
        category_id=category_id,
        note=note,
        related_transaction_id=None,  # Standalone debt, not tied to a transaction
        session=session,
    )
    
    await state.clear()
    
    # Notify the other party
    notification_sent = False
    try:
        if is_user_debtor:
            # User owes them - notify creditor
            notification_text = (
                f"💰 Someone owes you money!\n\n"
                f"Amount: <b>{amount:.2f} {currency}</b>\n"
                f"Debtor: {current_user.username or f'User {current_user.telegram_id}'}\n"
                f"Note: {note if note else 'No note'}\n\n"
                f"Use /debts to see all your debts."
            )
        else:
            # They owe user - notify debtor
            notification_text = (
                f"💸 You have a new debt!\n\n"
                f"Amount: <b>{amount:.2f} {currency}</b>\n"
                f"Creditor: {current_user.username or f'User {current_user.telegram_id}'}\n"
                f"Note: {note if note else 'No note'}\n\n"
                f"Use /debts to see all your debts."
            )
        
        await bot.send_message(
            chat_id=other_user.telegram_id,
            text=notification_text,
            parse_mode="HTML"
        )
        notification_sent = True
    except Exception as e:
        logger.warning(f"Could not notify user {other_user.telegram_id}: {e}")
    
    # Build response message
    response_text = (
        f"✅ Debt created!\n\n"
        f"💸 Amount: <b>{amount:.2f} {currency}</b>\n"
        f"{direction_text}\n"
        f"📝 Note: {note if note else 'No note'}\n"
    )
    
    if not notification_sent:
        response_text += f"\n⚠️ Other party hasn't started the bot yet. They'll be notified when they do.\n"
    
    response_text += f"🆔 Debt ID: <code>{debt.id}</code>"
    
    await message.answer(response_text, parse_mode="HTML")


@router.callback_query(CreateDebt.waiting_note, F.data == "debt:skip_note")
async def handle_debt_skip_note(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
):
    """Handle skipping note and complete debt creation."""
    data = await state.get_data()
    amount = data["amount"]
    currency = data["currency"]
    category_id = data["category_id"]
    other_user_id = data["other_user_id"]
    is_user_debtor = data.get("is_user_debtor", False)
    
    # Get users
    current_user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    other_user = await UserService.get_user_by_telegram_id(other_user_id, session)
    
    # Determine creditor and debtor based on direction
    if is_user_debtor:
        creditor = other_user
        debtor = current_user
        direction_text = f"👤 You owe: {other_user.username or f'User {other_user.telegram_id}'}"
    else:
        creditor = current_user
        debtor = other_user
        direction_text = f"👤 Debtor: {other_user.username or f'User {other_user.telegram_id}'}"
    
    # Create debt
    debt = await DebtService.create_debt(
        creditor=creditor,
        debtor=debtor,
        amount=amount,
        currency=currency,
        category_id=category_id,
        note=None,
        related_transaction_id=None,  # Standalone debt, not tied to a transaction
        session=session,
    )
    
    await state.clear()
    
    # Notify the other party
    notification_sent = False
    try:
        if is_user_debtor:
            # User owes them - notify creditor
            notification_text = (
                f"💰 Someone owes you money!\n\n"
                f"Amount: <b>{amount:.2f} {currency}</b>\n"
                f"Debtor: {current_user.username or f'User {current_user.telegram_id}'}\n\n"
                f"Use /debts to see all your debts."
            )
        else:
            # They owe user - notify debtor
            notification_text = (
                f"💸 You have a new debt!\n\n"
                f"Amount: <b>{amount:.2f} {currency}</b>\n"
                f"Creditor: {current_user.username or f'User {current_user.telegram_id}'}\n\n"
                f"Use /debts to see all your debts."
            )
        
        await bot.send_message(
            chat_id=other_user.telegram_id,
            text=notification_text,
            parse_mode="HTML"
        )
        notification_sent = True
    except Exception as e:
        logger.warning(f"Could not notify user {other_user.telegram_id}: {e}")
    
    # Build response message
    response_text = (
        f"✅ Debt created!\n\n"
        f"💸 Amount: <b>{amount:.2f} {currency}</b>\n"
        f"{direction_text}\n"
    )
    
    if not notification_sent:
        response_text += f"\n⚠️ Other party hasn't started the bot yet. They'll be notified when they do.\n"
    
    response_text += f"🆔 Debt ID: <code>{debt.id}</code>"
    
    await callback.message.edit_text(response_text, parse_mode="HTML")
    await callback.answer()

