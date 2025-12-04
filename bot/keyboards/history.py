"""History and transaction management keyboards."""

from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from models.transactions import Transaction


def history_keyboard(transactions: List[Transaction]) -> InlineKeyboardMarkup:
    """
    Create inline keyboard for transaction history with undo buttons.

    Args:
        transactions: List of transactions

    Returns:
        InlineKeyboardMarkup
    """
    buttons = []

    for transaction in transactions:
        buttons.append([
            InlineKeyboardButton(
                text=f"❌ Undo {transaction.id}",
                callback_data=f"undo:{transaction.id}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def skip_note_keyboard() -> InlineKeyboardMarkup:
    """
    Create keyboard with skip button for note input.

    Returns:
        InlineKeyboardMarkup
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Skip", callback_data="skip_note")]
    ])


def transaction_confirmation_keyboard(transaction_id: str) -> InlineKeyboardMarkup:
    """
    Create keyboard with cancel button for transaction confirmation.

    Args:
        transaction_id: Transaction ID to cancel

    Returns:
        InlineKeyboardMarkup
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data=f"undo:{transaction_id}")]
    ])


def date_input_keyboard() -> InlineKeyboardMarkup:
    """
    Create keyboard with "Use today" button for date input.

    Returns:
        InlineKeyboardMarkup
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Use today", callback_data="use_today")]
    ])

