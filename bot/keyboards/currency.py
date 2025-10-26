"""Currency selection keyboards."""

from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def currency_keyboard(
    recent_currencies: List[str],
    default_currency: str,
    supported_currencies: List[str],
) -> InlineKeyboardMarkup:
    """
    Create inline keyboard for currency selection.

    Args:
        recent_currencies: List of recently used currencies
        default_currency: User's default currency
        supported_currencies: All supported currencies

    Returns:
        InlineKeyboardMarkup
    """
    buttons = []

    # Add recent currencies first (with ⭐)
    seen = set()
    for currency in recent_currencies:
        if currency not in seen:
            buttons.append([
                InlineKeyboardButton(
                    text=f"⭐ {currency}",
                    callback_data=f"currency:{currency}"
                )
            ])
            seen.add(currency)

    # Add default currency if not in recent
    if default_currency not in seen:
        buttons.append([
            InlineKeyboardButton(
                text=f"🏠 {default_currency}",
                callback_data=f"currency:{default_currency}"
            )
        ])
        seen.add(default_currency)

    # Add other supported currencies
    other_buttons = []
    for currency in supported_currencies:
        if currency not in seen:
            other_buttons.append(
                InlineKeyboardButton(
                    text=currency,
                    callback_data=f"currency:{currency}"
                )
            )
            seen.add(currency)

    # Add other currencies in rows of 3
    for i in range(0, len(other_buttons), 3):
        buttons.append(other_buttons[i:i+3])

    # Add "Other Currency" button at the bottom
    buttons.append([
        InlineKeyboardButton(
            text="💱 Other Currency",
            callback_data="other_currency"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def report_currency_keyboard(
    recent_currencies: List[str],
    current_currency: str,
    supported_currencies: List[str],
) -> InlineKeyboardMarkup:
    """
    Create inline keyboard for report currency selection.

    Args:
        recent_currencies: List of recently used currencies
        current_currency: User's current preferred report currency
        supported_currencies: All supported currencies

    Returns:
        InlineKeyboardMarkup
    """
    buttons = []

    # Add current currency first (with ✅)
    seen = set()
    if current_currency:
        buttons.append([
            InlineKeyboardButton(
                text=f"✅ {current_currency}",
                callback_data=f"report_currency:{current_currency}"
            )
        ])
        seen.add(current_currency)

    # Add recent currencies (with ⭐)
    for currency in recent_currencies:
        if currency not in seen:
            buttons.append([
                InlineKeyboardButton(
                    text=f"⭐ {currency}",
                    callback_data=f"report_currency:{currency}"
                )
            ])
            seen.add(currency)

    # Add other supported currencies
    other_buttons = []
    for currency in supported_currencies:
        if currency not in seen:
            other_buttons.append(
                InlineKeyboardButton(
                    text=currency,
                    callback_data=f"report_currency:{currency}"
                )
            )
            seen.add(currency)

    # Add other currencies in rows of 3
    for i in range(0, len(other_buttons), 3):
        buttons.append(other_buttons[i:i+3])

    # Add "Other Currency" button at the bottom
    buttons.append([
        InlineKeyboardButton(
            text="💱 Other Currency",
            callback_data="report_other_currency"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

