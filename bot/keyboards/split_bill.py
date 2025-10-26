"""Keyboards for split bill and debt management."""

from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from models.debts import Debt


def split_type_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for selecting split type."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="50% / 50%", callback_data="split:half")],
        [InlineKeyboardButton(text="Custom Amount", callback_data="split:custom")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="split:cancel")],
    ])
    return keyboard


def debt_list_keyboard(debts: List[Debt], for_settle: bool = False) -> InlineKeyboardMarkup:
    """
    Create keyboard for listing debts with optional settle buttons.
    
    Args:
        debts: List of debt objects
        for_settle: If True, add settle buttons for each debt
    
    Returns:
        InlineKeyboardMarkup
    """
    buttons = []
    
    for debt in debts:
        # Create debt display text
        amount = float(debt.amount)
        currency = debt.currency
        
        # Determine direction
        # Note: This will be called from context, so we'll need to pass creditor/debtor info
        text = f"{amount:.2f} {currency}"
        
        if for_settle:
            buttons.append([
                InlineKeyboardButton(
                    text=f"Settle: {text}",
                    callback_data=f"settle:{debt.id}"
                )
            ])
        else:
            buttons.append([
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"debt:{debt.id}"
                )
            ])
    
    if not buttons:
        buttons.append([InlineKeyboardButton(text="No debts", callback_data="debt:none")])
    
    buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="debts:back")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def skip_note_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard to skip optional note."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Skip note", callback_data="split:skip_note")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="split:cancel")],
    ])
    return keyboard

