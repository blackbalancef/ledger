"""Keyboards for debt creation."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def debt_direction_keyboard() -> InlineKeyboardMarkup:
    """
    Create keyboard for selecting debt direction.
    
    Returns:
        InlineKeyboardMarkup with "I owe them" and "They owe me" options
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💸 I owe them",
                    callback_data="debt_direction:i_owe"
                ),
                InlineKeyboardButton(
                    text="💰 They owe me",
                    callback_data="debt_direction:owe_me"
                ),
            ]
        ]
    )

