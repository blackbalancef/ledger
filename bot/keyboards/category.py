"""Category selection keyboards."""

from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from models.categories import Category


def category_keyboard(categories: List[Category]) -> InlineKeyboardMarkup:
    """
    Create inline keyboard for category selection.

    Args:
        categories: List of categories

    Returns:
        InlineKeyboardMarkup
    """
    buttons = []

    # Add categories in rows of 2
    for i in range(0, len(categories), 2):
        row = []
        for category in categories[i:i+2]:
            row.append(
                InlineKeyboardButton(
                    text=f"{category.icon} {category.name}",
                    callback_data=f"category:{category.id}"
                )
            )
        buttons.append(row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)

