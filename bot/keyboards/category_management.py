"""Category management keyboards."""

from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from models.categories import Category, TransactionType


def categories_main_menu() -> InlineKeyboardMarkup:
    """Create main category management menu."""
    buttons = [
        [InlineKeyboardButton(text="➕ Add Category", callback_data="cat:add")],
        [InlineKeyboardButton(text="✏️ Edit Category", callback_data="cat:edit:select")],
        [InlineKeyboardButton(text="🗑️ Delete Category", callback_data="cat:delete:select")],
        [InlineKeyboardButton(text="📦 Unarchive Category", callback_data="cat:unarchive:select")],
        [InlineKeyboardButton(text="📋 List Categories", callback_data="cat:list")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="cat:cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def category_type_selection() -> InlineKeyboardMarkup:
    """Create keyboard for selecting category type."""
    buttons = [
        [
            InlineKeyboardButton(text="💸 Expense", callback_data="cat:type:EXPENSE"),
            InlineKeyboardButton(text="💰 Income", callback_data="cat:type:INCOME"),
        ],
        [InlineKeyboardButton(text="🔙 Back", callback_data="cat:cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def user_categories_keyboard(categories: List[Category]) -> InlineKeyboardMarkup:
    """
    Create keyboard for selecting a category from a list.

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
                    callback_data=f"cat:select:{category.id}"
                )
            )
        buttons.append(row)

    # Add back button
    buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="cat:cancel")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def archive_options_keyboard(categories: List[Category], has_transactions: bool) -> InlineKeyboardMarkup:
    """
    Create keyboard for archive options.

    Args:
        categories: Available categories to migrate to (excluding the one being archived)
        has_transactions: Whether the category has transactions

    Returns:
        InlineKeyboardMarkup
    """
    buttons = []
    
    if has_transactions:
        # Options: Keep in archived, or migrate to another category
        buttons.append([InlineKeyboardButton(text="✅ Keep as archived", callback_data="cat:archive:keep")])
        
        if categories:
            buttons.append([InlineKeyboardButton(text="➡️ Migrate to another", callback_data="cat:archive:migrate:select")])
        else:
            # No other categories available, only option is to keep archived
            pass
    
    buttons.append([InlineKeyboardButton(text="🔙 Cancel", callback_data="cat:cancel")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def edit_category_fields_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for selecting which field to edit."""
    buttons = [
        [InlineKeyboardButton(text="📝 Name", callback_data="cat:edit:field:name")],
        [InlineKeyboardButton(text="😀 Icon (Emoji)", callback_data="cat:edit:field:icon")],
        [InlineKeyboardButton(text="📄 Description", callback_data="cat:edit:field:description")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="cat:cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def skip_description_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for skipping description input."""
    buttons = [
        [InlineKeyboardButton(text="⏭️ Skip", callback_data="cat:skip_desc")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="cat:cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirmation_keyboard(action: str) -> InlineKeyboardMarkup:
    """
    Create confirmation keyboard.

    Args:
        action: Action to confirm (e.g., 'create', 'delete', 'archive')

    Returns:
        InlineKeyboardMarkup
    """
    buttons = [
        [
            InlineKeyboardButton(text="✅ Confirm", callback_data=f"cat:confirm:{action}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="cat:cancel"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

