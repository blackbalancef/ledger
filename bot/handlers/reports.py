"""Report generation handlers."""

from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from bot.services.user_service import UserService
from bot.services.transaction_service import TransactionService
from bot.states import ReportCurrency
from bot.keyboards.currency import report_currency_keyboard
from core.config import settings
from core.fx_rates import fx_service

router = Router()


@router.message(Command("report"))
async def cmd_report(message: Message, session: AsyncSession):
    """
    Handle /report command - generate monthly report.

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

    # Get current month report (uses user's preferred_report_currency)
    now = datetime.utcnow()
    report = await TransactionService.get_monthly_report(
        user=user,
        session=session,
        year=now.year,
        month=now.month,
    )

    # Format report
    text = _format_report(report)

    # Add "Recalculate in other currency" button
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💱 Recalculate in other currency",
            callback_data="recalculate_report"
        )]
    ])

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


def _format_report(report: dict) -> str:
    """
    Format report dictionary into human-readable text.

    Args:
        report: Report dictionary from TransactionService

    Returns:
        Formatted report text
    """
    period = report["period"]
    month_name = datetime(period["year"], period["month"], 1).strftime("%B %Y")
    currency = report["display_currency"]

    text = f"📊 <b>Monthly Report - {month_name}</b>\n\n"

    # Expenses section
    if report["expenses"]:
        text += "💸 <b>Expenses:</b>\n"
        for expense in report["expenses"]:
            text += (
                f"{expense['icon']} {expense['category']}: "
                f"<b>{expense['amount']:.2f} {currency}</b>\n"
            )
        text += f"\n📉 Total expenses: <b>{report['totals']['expenses']:.2f} {currency}</b>\n\n"
    else:
        text += "💸 <b>Expenses:</b> No expenses this month\n\n"

    # Income section
    if report["income"]:
        text += "💰 <b>Income:</b>\n"
        for income in report["income"]:
            text += (
                f"{income['icon']} {income['category']}: "
                f"<b>{income['amount']:.2f} {currency}</b>\n"
            )
        text += f"\n📈 Total income: <b>{report['totals']['income']:.2f} {currency}</b>\n\n"
    else:
        text += "💰 <b>Income:</b> No income this month\n\n"

    # Balance
    balance = report['totals']['balance']
    balance_emoji = "💚" if balance >= 0 else "❤️"

    text += f"{balance_emoji} <b>Balance:</b> <b>{balance:.2f} {currency}</b>"

    return text


@router.callback_query(F.data == "recalculate_report")
async def handle_recalculate_report(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """
    Handle recalculate report button - show currency selection.

    Args:
        callback: Callback query
        state: FSM context
        session: Database session
    """
    # Get user
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )

    # Get recent currencies
    recent_currencies = await UserService.get_recent_currencies(user, session)

    # Create currency selection keyboard
    keyboard = report_currency_keyboard(
        recent_currencies=recent_currencies,
        current_currency=user.preferred_report_currency,
        supported_currencies=settings.currencies_list,
    )

    await callback.message.edit_text(
        "Select currency to display the report:",
        reply_markup=keyboard,
    )
    await state.set_state(ReportCurrency.waiting_currency)
    await callback.answer()


@router.callback_query(ReportCurrency.waiting_currency, F.data.startswith("report_currency:"))
async def handle_report_currency_selection(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """
    Handle currency selection for report display.

    Args:
        callback: Callback query
        state: FSM context
        session: Database session
    """
    # Extract currency from callback data
    selected_currency = callback.data.split(":", 1)[1]

    # Get user
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )

    # Update user's preferred report currency
    await UserService.update_preferred_report_currency(
        user=user,
        currency=selected_currency,
        session=session,
    )

    # Get current month report with selected currency
    now = datetime.utcnow()
    report = await TransactionService.get_monthly_report(
        user=user,
        session=session,
        year=now.year,
        month=now.month,
        display_currency=selected_currency,
    )

    # Format and display report
    text = _format_report(report)

    # Add "Recalculate in other currency" button
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💱 Recalculate in other currency",
            callback_data="recalculate_report"
        )]
    ])

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await state.clear()
    await callback.answer(f"Report currency changed to {selected_currency}")


@router.callback_query(ReportCurrency.waiting_currency, F.data == "report_other_currency")
async def handle_report_other_currency(
    callback: CallbackQuery,
    state: FSMContext,
):
    """
    Handle "Other Currency" button - prompt for custom currency input.

    Args:
        callback: Callback query
        state: FSM context
    """
    await callback.message.edit_text(
        "Please enter the currency code (e.g., JPY, GBP, CHF):"
    )
    await state.set_state(ReportCurrency.waiting_custom_currency)
    await callback.answer()


@router.message(ReportCurrency.waiting_custom_currency)
async def handle_report_custom_currency(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    """
    Handle custom currency code input for report.

    Args:
        message: Telegram message
        state: FSM context
        session: Database session
    """
    # Normalize input
    currency_code = message.text.strip().upper()

    # Validate currency code format
    if len(currency_code) != 3 or not currency_code.isalpha():
        await message.answer(
            "❌ Invalid currency code format. Please enter a valid 3-letter "
            "currency code (e.g., JPY, GBP, CHF)."
        )
        return

    # Get user
    user = await UserService.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        session=session,
    )

    # Validate currency by checking if exchange rates are available
    try:
        await fx_service.get_rate("EUR", currency_code, session)
    except Exception as e:
        logger.warning(f"Currency validation failed for {currency_code}: {e}")
        await message.answer(
            f"❌ Currency {currency_code} is not supported or exchange rates "
            f"are unavailable. Please try another currency."
        )
        return

    # Update user's preferred report currency
    await UserService.update_preferred_report_currency(
        user=user,
        currency=currency_code,
        session=session,
    )

    # Get current month report with selected currency
    now = datetime.utcnow()
    report = await TransactionService.get_monthly_report(
        user=user,
        session=session,
        year=now.year,
        month=now.month,
        display_currency=currency_code,
    )

    # Format and display report
    text = _format_report(report)

    # Add "Recalculate in other currency" button
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💱 Recalculate in other currency",
            callback_data="recalculate_report"
        )]
    ])

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await state.clear()

