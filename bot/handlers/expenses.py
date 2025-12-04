"""Expense handling."""

import re
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from datetime import datetime

from bot.services.user_service import UserService
from bot.services.transaction_service import TransactionService
from bot.states import AddExpense, SplitBill, CreateDebt, ReportDateRange
from bot.keyboards import currency_keyboard, category_keyboard, skip_note_keyboard, transaction_confirmation_keyboard, date_input_keyboard
from bot.utils.date_parser import parse_single_date
from models.categories import TransactionType
from models.transactions import TransactionTypeEnum
from core.config import settings
from core.fx_rates import fx_service

router = Router()


@router.message(
    ~StateFilter(SplitBill.waiting_amount),
    ~StateFilter(SplitBill.waiting_custom_currency),
    ~StateFilter(SplitBill.waiting_custom_amount),
    ~StateFilter(SplitBill.waiting_other_user),
    ~StateFilter(CreateDebt.waiting_amount),
    ~StateFilter(CreateDebt.waiting_custom_currency),
    ~StateFilter(CreateDebt.waiting_direction),
    ~StateFilter(CreateDebt.waiting_other_user),
    ~StateFilter(CreateDebt.waiting_note),
    ~StateFilter(ReportDateRange.waiting_single_date),
    ~StateFilter(ReportDateRange.waiting_date_range),
    ~StateFilter(AddExpense.waiting_date),
    F.text.regexp(r"^\d+(\.\d{1,2})?$")
)
async def handle_amount(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handle expense amount input.

    Args:
        message: Telegram message
        state: FSM context
        session: Database session
    """
    amount = float(message.text)

    # Store amount in state
    await state.update_data(amount=amount)
    await state.set_state(AddExpense.waiting_currency)

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
        f"💸 Adding expense: <b>{amount}</b>\n\n"
        f"Select currency:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(AddExpense.waiting_currency, F.data.startswith("currency:"))
async def handle_currency_selection(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """
    Handle currency selection for expense.

    Args:
        callback: Callback query
        state: FSM context
        session: Database session
    """
    currency = callback.data.split(":")[1]

    # Store currency in state
    await state.update_data(currency=currency)
    await state.set_state(AddExpense.waiting_category)

    # Get expense categories for user
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
        f"💸 Adding expense: <b>{amount} {currency}</b>\n\n"
        f"Select category:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(AddExpense.waiting_currency, F.data == "other_currency")
async def handle_other_currency(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """
    Handle "Other Currency" button click.

    Args:
        callback: Callback query
        state: FSM context
        session: Database session
    """
    await state.set_state(AddExpense.waiting_custom_currency)

    data = await state.get_data()
    amount = data["amount"]

    await callback.message.edit_text(
        f"💸 Adding expense: <b>{amount}</b>\n\n"
        f"Please enter a 3-letter currency code (e.g., JPY, GBP, CHF):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddExpense.waiting_custom_currency)
async def handle_custom_currency_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    """
    Handle custom currency code input.

    Args:
        message: Telegram message
        state: FSM context
        session: Database session
    """
    currency = message.text.strip().upper()

    # Validate format (3 letters)
    if not re.match(r"^[A-Z]{3}$", currency):
        await message.answer(
            "❌ Invalid format. Please enter a valid 3-letter currency code (e.g., JPY, GBP):",
            parse_mode="HTML",
        )
        return

    # Validate currency by checking if exchange rates are available
    try:
        await fx_service.get_rates_for_transaction(currency, session)
    except ValueError:
        # Get user to show currency keyboard again
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
            f"❌ Currency <b>{currency}</b> is not supported or exchange rates are unavailable.\n\n"
            f"Please select another currency:",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        await state.set_state(AddExpense.waiting_currency)
        return

    # Currency is valid, proceed to category selection
    await state.update_data(currency=currency)
    await state.set_state(AddExpense.waiting_category)

    # Get expense categories for user
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

    await message.answer(
        f"💸 Adding expense: <b>{amount} {currency}</b>\n\n"
        f"Select category:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(AddExpense.waiting_category, F.data.startswith("category:"))
async def handle_category_selection(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """
    Handle category selection for expense.

    Args:
        callback: Callback query
        state: FSM context
        session: Database session
    """
    category_id = int(callback.data.split(":")[1])

    # Store category in state
    await state.update_data(category_id=category_id)
    await state.set_state(AddExpense.waiting_note)

    data = await state.get_data()
    amount = data["amount"]
    currency = data["currency"]

    keyboard = skip_note_keyboard()

    await callback.message.edit_text(
        f"💸 Adding expense: <b>{amount} {currency}</b>\n\n"
        f"Add a note or skip:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddExpense.waiting_note)
async def handle_note_input(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handle note input for expense.

    Args:
        message: Telegram message
        state: FSM context
        session: Database session
    """
    note = message.text

    # Store note in state and transition to date input
    await state.update_data(note=note)
    await state.set_state(AddExpense.waiting_date)

    # Get data from state
    data = await state.get_data()
    amount = data["amount"]
    currency = data["currency"]

    keyboard = date_input_keyboard()

    await message.answer(
        f"💸 Adding expense: <b>{amount} {currency}</b>\n"
        f"📝 Note: {note}\n\n"
        f"Enter date (DD.MM.YYYY or DD.MM) or use today:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(AddExpense.waiting_note, F.data == "skip_note")
async def handle_skip_note(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Handle skipping note input.

    Args:
        callback: Callback query
        state: FSM context
        session: Database session
    """
    # Store None for note and transition to date input
    await state.update_data(note=None)
    await state.set_state(AddExpense.waiting_date)

    # Get data from state
    data = await state.get_data()
    amount = data["amount"]
    currency = data["currency"]

    keyboard = date_input_keyboard()

    await callback.message.edit_text(
        f"💸 Adding expense: <b>{amount} {currency}</b>\n\n"
        f"Enter date (DD.MM.YYYY or DD.MM) or use today:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddExpense.waiting_date)
async def handle_date_input(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handle date input for expense.

    Args:
        message: Telegram message
        state: FSM context
        session: Database session
    """
    try:
        # Parse date input
        date_obj = parse_single_date(message.text)
        
        # Set time to start of day for consistency
        transaction_date = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
    except ValueError as e:
        await message.answer(
            f"❌ {str(e)}\n\n"
            f"Please enter a date in DD.MM.YYYY or DD.MM format (e.g., 15.03.2024 or 15.09):",
            parse_mode="HTML",
        )
        return

    # Get all data from state
    data = await state.get_data()
    amount = data["amount"]
    currency = data["currency"]
    category_id = data["category_id"]
    note = data.get("note")

    # Get user
    user = await UserService.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        session=session,
    )

    # Create transaction with custom date
    transaction = await TransactionService.create_transaction(
        user=user,
        amount=amount,
        currency=currency,
        transaction_type=TransactionTypeEnum.EXPENSE,
        category_id=category_id,
        note=note,
        session=session,
        at_time=transaction_date,
    )

    await state.clear()

    keyboard = transaction_confirmation_keyboard(str(transaction.id))

    date_str = transaction_date.strftime("%d.%m.%Y")
    note_text = f"📝 Note: {note}\n" if note else ""
    
    await message.answer(
        f"✅ Expense added!\n\n"
        f"💸 Amount: <b>{amount} {currency}</b>\n"
        f"{note_text}"
        f"📅 Date: {date_str}\n"
        f"🆔 ID: <code>{transaction.id}</code>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(AddExpense.waiting_date, F.data == "use_today")
async def handle_use_today(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Handle "Use today" button click for date input.

    Args:
        callback: Callback query
        state: FSM context
        session: Database session
    """
    # Get all data from state
    data = await state.get_data()
    amount = data["amount"]
    currency = data["currency"]
    category_id = data["category_id"]
    note = data.get("note")

    # Get user
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )

    # Create transaction with current date/time
    transaction = await TransactionService.create_transaction(
        user=user,
        amount=amount,
        currency=currency,
        transaction_type=TransactionTypeEnum.EXPENSE,
        category_id=category_id,
        note=note,
        session=session,
    )

    await state.clear()

    keyboard = transaction_confirmation_keyboard(str(transaction.id))

    note_text = f"📝 Note: {note}\n" if note else ""
    
    await callback.message.edit_text(
        f"✅ Expense added!\n\n"
        f"💸 Amount: <b>{amount} {currency}</b>\n"
        f"{note_text}"
        f"🆔 ID: <code>{transaction.id}</code>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()

