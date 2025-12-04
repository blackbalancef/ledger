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
from bot.states import ReportCurrency, ReportDateRange
from bot.keyboards.currency import report_currency_keyboard
from bot.utils.date_parser import parse_single_date, parse_date_range
from core.config import settings
from core.fx_rates import fx_service

router = Router()


@router.message(Command("report"))
async def cmd_report(message: Message, state: FSMContext, session: AsyncSession):
    """
    Handle /report command - generate monthly report.

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

    # Get current month report (uses user's preferred_report_currency)
    now = datetime.utcnow()
    
    # Store report parameters in state for currency recalculation
    await state.update_data(
        report_type="monthly",
        report_year=now.year,
        report_month=now.month,
    )
    
    report = await TransactionService.get_monthly_report(
        user=user,
        session=session,
        year=now.year,
        month=now.month,
    )

    # Format report
    text = _format_report(report)

    # Add buttons for date selection and currency
    keyboard = _create_report_keyboard()

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


def _format_report(report: dict) -> str:
    """
    Format report dictionary into human-readable text.

    Args:
        report: Report dictionary from TransactionService

    Returns:
        Formatted report text
    """
    currency = report["display_currency"]

    # Determine report title based on period type
    if "period" in report:
        # Monthly report
        period = report["period"]
        month_name = datetime(period["year"], period["month"], 1).strftime("%B %Y")
        text = f"📊 <b>Monthly Report - {month_name}</b>\n\n"
    elif "date_range" in report:
        # Date range report
        date_range = report["date_range"]
        start_date = date_range["start_date"]
        end_date = date_range["end_date"]
        
        # Check if it's a single day
        if start_date.date() == end_date.date():
            date_str = start_date.strftime("%d.%m.%Y")
            text = f"📊 <b>Report - {date_str}</b>\n\n"
        else:
            start_str = start_date.strftime("%d.%m.%Y")
            end_str = end_date.strftime("%d.%m.%Y")
            text = f"📊 <b>Report - {start_str} to {end_str}</b>\n\n"
    else:
        # Fallback
        text = "📊 <b>Report</b>\n\n"

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
        text += "💸 <b>Expenses:</b> No expenses\n\n"

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
        text += "💰 <b>Income:</b> No income\n\n"

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
    Preserves the current report date range/type.

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

    # Try to get stored report parameters from state
    state_data = await state.get_data()
    report_type = state_data.get("report_type", "monthly")
    
    # If no stored parameters, default to current month
    if report_type == "monthly":
        now = datetime.utcnow()
        await state.update_data(
            report_type="monthly",
            report_year=now.year,
            report_month=now.month,
        )
    # If date_range type, parameters should already be stored

    # Get recent currencies
    recent_currencies = await UserService.get_recent_currencies(user, session)

    # Create currency selection keyboard
    keyboard = report_currency_keyboard(
        recent_currencies=recent_currencies,
        current_currency=user.preferred_report_currency,
        supported_currencies=settings.currencies_list,
    )

    # Preserve state data when transitioning
    state_data_before = await state.get_data()
    logger.debug(f"Recalculate handler - state_data before transition: {state_data_before}")
    
    await callback.message.edit_text(
        "Select currency to display the report:",
        reply_markup=keyboard,
    )
    await state.set_state(ReportCurrency.waiting_currency)
    
    # Ensure state data is preserved after state change
    await state.update_data(**state_data_before)
    await callback.answer()


@router.callback_query(ReportCurrency.waiting_currency, F.data.startswith("report_currency:"))
async def handle_report_currency_selection(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """
    Handle currency selection for report display.
    Preserves the current report date range/type.

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

    # Get stored report parameters from state
    state_data = await state.get_data()
    report_type = state_data.get("report_type", "monthly")

    # Generate report based on stored type
    if report_type == "date_range":
        start_date_str = state_data.get("report_start_date")
        end_date_str = state_data.get("report_end_date")
        if start_date_str and end_date_str:
            # Parse ISO format strings back to datetime (handle both string and datetime for robustness)
            start_date = datetime.fromisoformat(start_date_str) if isinstance(start_date_str, str) else start_date_str
            end_date = datetime.fromisoformat(end_date_str) if isinstance(end_date_str, str) else end_date_str
            report = await TransactionService.get_date_range_report(
                user=user,
                session=session,
                start_date=start_date,
                end_date=end_date,
                display_currency=selected_currency,
            )
        else:
            # Fallback to current month if date range not found
            now = datetime.utcnow()
            report = await TransactionService.get_monthly_report(
                user=user,
                session=session,
                year=now.year,
                month=now.month,
                display_currency=selected_currency,
            )
    else:
        # Monthly report
        year = state_data.get("report_year")
        month = state_data.get("report_month")
        now = datetime.utcnow()
        report = await TransactionService.get_monthly_report(
            user=user,
            session=session,
            year=year or now.year,
            month=month or now.month,
            display_currency=selected_currency,
        )

    # Format and display report
    text = _format_report(report)

    # Add buttons for date selection and currency
    keyboard = _create_report_keyboard()

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
    # Preserve state data when transitioning
    state_data = await state.get_data()
    logger.debug(f"Other currency handler - preserving state_data: {state_data}")
    
    await callback.message.edit_text(
        "Please enter the currency code (e.g., JPY, GBP, CHF):"
    )
    await state.set_state(ReportCurrency.waiting_custom_currency)
    
    # Ensure state data is preserved after state change
    await state.update_data(**state_data)
    await callback.answer()


@router.message(ReportCurrency.waiting_custom_currency)
async def handle_report_custom_currency(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    """
    Handle custom currency code input for report.
    Preserves the current report date range/type.

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
        await state.clear()  # Clear state to allow user to continue using bot normally
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
        await state.clear()  # Clear state to allow user to continue using bot normally
        return

    # Update user's preferred report currency
    await UserService.update_preferred_report_currency(
        user=user,
        currency=currency_code,
        session=session,
    )

    # Get stored report parameters from state
    state_data = await state.get_data()
    report_type = state_data.get("report_type", "monthly")
    
    logger.debug(f"Custom currency handler - report_type: {report_type}, state_data keys: {list(state_data.keys())}, full_data: {state_data}")

    # Check for date range data (either by report_type or by presence of date fields)
    start_date_str = state_data.get("report_start_date")
    end_date_str = state_data.get("report_end_date")
    has_date_range = (report_type == "date_range" or (start_date_str is not None and end_date_str is not None))
    
    if has_date_range and start_date_str is not None and end_date_str is not None:
        # Parse ISO format strings back to datetime
        try:
            start_date = datetime.fromisoformat(start_date_str) if isinstance(start_date_str, str) else start_date_str
            end_date = datetime.fromisoformat(end_date_str) if isinstance(end_date_str, str) else end_date_str
            logger.debug(f"Using date range report: {start_date} to {end_date}")
            report = await TransactionService.get_date_range_report(
                user=user,
                session=session,
                start_date=start_date,
                end_date=end_date,
                display_currency=currency_code,
            )
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing date range: {e}, falling back to monthly")
            now = datetime.utcnow()
            report = await TransactionService.get_monthly_report(
                user=user,
                session=session,
                year=now.year,
                month=now.month,
                display_currency=currency_code,
            )
    else:
        # Monthly report
        year = state_data.get("report_year")
        month = state_data.get("report_month")
        now = datetime.utcnow()
        report = await TransactionService.get_monthly_report(
            user=user,
            session=session,
            year=year or now.year,
            month=month or now.month,
            display_currency=currency_code,
        )

    # Format and display report
    text = _format_report(report)

    # Add buttons for date selection and currency
    keyboard = _create_report_keyboard()

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await state.clear()


def _create_report_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard with date selection and currency options."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📅 Today",
                callback_data="report_today"
            ),
            InlineKeyboardButton(
                text="📆 Last Month",
                callback_data="report_last_month"
            )
        ],
        [
            InlineKeyboardButton(
                text="📆 Custom Date",
                callback_data="report_custom_date"
            ),
            InlineKeyboardButton(
                text="📊 Date Range",
                callback_data="report_date_range"
            )
        ],
        [
            InlineKeyboardButton(
                text="💱 Recalculate in other currency",
                callback_data="recalculate_report"
            )
        ]
    ])


@router.callback_query(F.data == "report_today")
async def handle_report_today(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """
    Handle "Today" button - show report for today.

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

    # Get today's date range (start and end of day)
    now = datetime.utcnow()
    start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Store report parameters in state for currency recalculation
    # Store as ISO strings for JSON serialization
    await state.update_data(
        report_type="date_range",
        report_start_date=start_date.isoformat(),
        report_end_date=end_date.isoformat(),
    )

    # Get report for today
    report = await TransactionService.get_date_range_report(
        user=user,
        session=session,
        start_date=start_date,
        end_date=end_date,
    )

    # Format and display report
    text = _format_report(report)
    keyboard = _create_report_keyboard()

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer("Report for today")


@router.callback_query(F.data == "report_last_month")
async def handle_report_last_month(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """
    Handle "Last Month" button - show report for last month.

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

    # Calculate last month
    now = datetime.utcnow()
    if now.month == 1:
        last_month = 12
        last_year = now.year - 1
    else:
        last_month = now.month - 1
        last_year = now.year

    # Store report parameters in state for currency recalculation
    await state.update_data(
        report_type="monthly",
        report_year=last_year,
        report_month=last_month,
    )

    # Get report for last month
    report = await TransactionService.get_monthly_report(
        user=user,
        session=session,
        year=last_year,
        month=last_month,
    )

    # Format and display report
    text = _format_report(report)
    keyboard = _create_report_keyboard()

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer(f"Report for {datetime(last_year, last_month, 1).strftime('%B %Y')}")


@router.callback_query(F.data == "report_custom_date")
async def handle_report_custom_date(
    callback: CallbackQuery,
    state: FSMContext,
):
    """
    Handle "Custom Date" button - prompt for single date input.

    Args:
        callback: Callback query
        state: FSM context
    """
    await callback.message.edit_text(
        "Please enter a date:\n\n"
        "• DD.MM.YYYY (e.g., 15.03.2024)\n"
        "• DD.MM (e.g., 15.09) - uses current year"
    )
    await state.set_state(ReportDateRange.waiting_single_date)
    await callback.answer()


@router.message(ReportDateRange.waiting_single_date)
async def handle_single_date_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    """
    Handle single date input for report.

    Args:
        message: Telegram message
        state: FSM context
        session: Database session
    """
    try:
        # Parse date
        date_obj = parse_single_date(message.text)
        
        # Set date range to start and end of the selected day
        start_date = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = date_obj.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Store report parameters in state for currency recalculation
        # Store as ISO strings for JSON serialization
        await state.update_data(
            report_type="date_range",
            report_start_date=start_date.isoformat(),
            report_end_date=end_date.isoformat(),
        )

        # Get user
        user = await UserService.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            session=session,
        )

        # Get report for the selected date
        report = await TransactionService.get_date_range_report(
            user=user,
            session=session,
            start_date=start_date,
            end_date=end_date,
        )

        # Format and display report
        text = _format_report(report)
        keyboard = _create_report_keyboard()

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        # Don't clear state - keep it for currency recalculation

    except ValueError as e:
        await message.answer(f"❌ {str(e)}\n\nPlease try again:")
        await state.clear()  # Clear state to allow user to continue using bot normally
        return


@router.callback_query(F.data == "report_date_range")
async def handle_report_date_range(
    callback: CallbackQuery,
    state: FSMContext,
):
    """
    Handle "Date Range" button - prompt for date range input.

    Args:
        callback: Callback query
        state: FSM context
    """
    await callback.message.edit_text(
        "Please enter a date range:\n\n"
        "• DD.MM-DD.MM (e.g., 01.03-15.03) - uses current year\n"
        "• DD.MM.YYYY - DD.MM.YYYY (e.g., 01.03.2024 - 15.03.2024)"
    )
    await state.set_state(ReportDateRange.waiting_date_range)
    await callback.answer()


@router.message(ReportDateRange.waiting_date_range)
async def handle_date_range_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    """
    Handle date range input for report.

    Args:
        message: Telegram message
        state: FSM context
        session: Database session
    """
    try:
        # Parse date range
        start_date, end_date = parse_date_range(message.text)

        # Store report parameters in state for currency recalculation
        # Store as ISO strings for JSON serialization
        await state.update_data(
            report_type="date_range",
            report_start_date=start_date.isoformat(),
            report_end_date=end_date.isoformat(),
        )

        # Get user
        user = await UserService.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            session=session,
        )

        # Get report for the selected date range
        report = await TransactionService.get_date_range_report(
            user=user,
            session=session,
            start_date=start_date,
            end_date=end_date,
        )

        # Format and display report
        text = _format_report(report)
        keyboard = _create_report_keyboard()

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        # Don't clear state - keep it for currency recalculation

    except ValueError as e:
        await message.answer(f"❌ {str(e)}\n\nPlease try again:")
        await state.clear()  # Clear state to allow user to continue using bot normally
        return

