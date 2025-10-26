"""Category management handlers."""

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from bot.services.user_service import UserService
from bot.services.category_service import CategoryService
from bot.services.transaction_service import TransactionService
from bot.states import (
    AddCategory,
    EditCategory,
    ArchiveCategory,
    UnarchiveCategory,
)
from bot.keyboards.category_management import (
    categories_main_menu,
    category_type_selection,
    user_categories_keyboard,
    archive_options_keyboard,
    edit_category_fields_keyboard,
    skip_description_keyboard,
    confirmation_keyboard,
)
from models.categories import TransactionType

router = Router()


@router.message(F.text == "/categories")
async def handle_categories_command(message: Message, state: FSMContext):
    """Handle /categories command to show main menu."""
    await state.clear()
    
    keyboard = categories_main_menu()
    
    await message.answer(
        "📁 Category Management\n\n"
        "Choose an action:",
        reply_markup=keyboard,
    )


# Add Category Flow
@router.callback_query(F.data == "cat:add")
async def handle_add_category(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Start add category flow."""
    await state.set_state(AddCategory.waiting_name)
    await callback.message.edit_text(
        "➕ Add New Category\n\n"
        "Enter category name:",
    )
    await callback.answer()


@router.message(AddCategory.waiting_name)
async def handle_category_name(
    message: Message,
    state: FSMContext,
):
    """Handle category name input."""
    name = message.text.strip()
    
    if len(name) > 100:
        await message.answer("❌ Name too long (max 100 characters). Please try again:")
        return
    
    await state.update_data(name=name)
    await state.set_state(AddCategory.waiting_icon)
    
    await message.answer(
        f"📝 Category name: <b>{name}</b>\n\n"
        "Send an emoji for this category:",
        parse_mode="HTML",
    )


@router.message(AddCategory.waiting_icon)
async def handle_category_icon(
    message: Message,
    state: FSMContext,
):
    """Handle category icon (emoji) input."""
    icon = message.text.strip()
    
    if len(icon) > 10:
        await message.answer("❌ Icon too long (max 10 characters). Please try again:")
        return
    
    await state.update_data(icon=icon)
    await state.set_state(AddCategory.waiting_description)
    
    keyboard = skip_description_keyboard()
    
    data = await state.get_data()
    await message.answer(
        f"📝 Name: <b>{data['name']}</b>\n"
        f"😀 Icon: {icon}\n\n"
        "Add description (optional):",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(AddCategory.waiting_description, F.data == "cat:skip_desc")
async def handle_skip_description(callback: CallbackQuery, state: FSMContext):
    """Handle skipping description."""
    await state.update_data(description=None)
    await state.set_state(AddCategory.waiting_type)
    
    keyboard = category_type_selection()
    
    data = await state.get_data()
    await callback.message.edit_text(
        f"📝 Name: <b>{data['name']}</b>\n"
        f"😀 Icon: {data['icon']}\n\n"
        "Select type:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddCategory.waiting_description)
async def handle_category_description(
    message: Message,
    state: FSMContext,
):
    """Handle category description input."""
    description = message.text.strip()
    await state.update_data(description=description)
    await state.set_state(AddCategory.waiting_type)
    
    keyboard = category_type_selection()
    
    data = await state.get_data()
    await message.answer(
        f"📝 Name: <b>{data['name']}</b>\n"
        f"😀 Icon: {data['icon']}\n"
        f"📄 Description: {description}\n\n"
        "Select type:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(AddCategory.waiting_type, F.data.startswith("cat:type:"))
async def handle_category_type(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Handle category type selection and create category."""
    transaction_type = callback.data.split(":")[-1]
    
    data = await state.get_data()
    name = data["name"]
    icon = data["icon"]
    description = data.get("description")
    
    # Get user
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    # Create category
    category = await CategoryService.create_category(
        user=user,
        name=name,
        icon=icon,
        transaction_type=transaction_type,
        session=session,
        description=description,
    )
    
    await state.clear()
    
    type_label = "💸 Expense" if transaction_type == "EXPENSE" else "💰 Income"
    
    await callback.message.edit_text(
        f"✅ Category created!\n\n"
        f"📝 Name: <b>{category.name}</b>\n"
        f"😀 Icon: {category.icon}\n"
        f"📄 Description: {category.description or 'No description'}\n"
        f"🏷️ Type: {type_label}\n"
        f"🆔 ID: <code>{category.id}</code>",
        parse_mode="HTML",
    )
    await callback.answer()


# Edit Category Flow
@router.callback_query(F.data == "cat:edit:select")
async def handle_edit_category_select(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Show list of user's categories for editing."""
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    # Get all user's active categories
    categories = await CategoryService.get_user_categories(
        user=user,
        session=session,
        include_archived=False,
    )
    
    if not categories:
        await callback.message.edit_text(
            "❌ No categories found. Create one first!",
        )
        await callback.answer()
        await state.clear()
        return
    
    await state.set_state(EditCategory.selecting_category)
    
    keyboard = user_categories_keyboard(categories)
    
    await callback.message.edit_text(
        "✏️ Edit Category\n\n"
        "Select category to edit:",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(EditCategory.selecting_category, F.data.startswith("cat:select:"))
async def handle_edit_category_selected(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Handle category selection for editing."""
    category_id = int(callback.data.split(":")[-1])
    
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    category = await CategoryService.get_category_by_id(category_id, user, session)
    
    if not category:
        await callback.message.edit_text("❌ Category not found!")
        await callback.answer()
        await state.clear()
        return
    
    await state.update_data(category_id=category_id)
    await state.set_state(EditCategory.selecting_field)
    
    keyboard = edit_category_fields_keyboard()
    
    await callback.message.edit_text(
        f"✏️ Edit Category: <b>{category.icon} {category.name}</b>\n\n"
        f"📄 Description: {category.description or 'No description'}\n\n"
        "Choose field to edit:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(EditCategory.selecting_field, F.data.startswith("cat:edit:field:"))
async def handle_edit_field_selection(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Handle field selection for editing."""
    field = callback.data.split(":")[-1]
    
    field_prompts = {
        "name": "Enter new name:",
        "icon": "Send new emoji:",
        "description": "Enter new description:",
    }
    
    await state.update_data(editing_field=field)
    await state.set_state(EditCategory.waiting_value)
    
    await callback.message.edit_text(
        f"✏️ Editing {field}\n\n{field_prompts[field]}",
    )
    await callback.answer()


@router.message(EditCategory.waiting_value)
async def handle_edit_value(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
):
    """Handle new value input for category field."""
    data = await state.get_data()
    category_id = data["category_id"]
    field = data["editing_field"]
    value = message.text.strip()
    
    user = await UserService.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        session=session,
    )
    
    # Update category
    if field == "name":
        await CategoryService.update_category(category_id, user, session=session, name=value)
    elif field == "icon":
        await CategoryService.update_category(category_id, user, session=session, icon=value)
    elif field == "description":
        await CategoryService.update_category(category_id, user, session=session, description=value)
    
    # Get updated category
    category = await CategoryService.get_category_by_id(category_id, user, session)
    
    await state.clear()
    
    await message.answer(
        f"✅ Category updated!\n\n"
        f"📝 Name: <b>{category.name}</b>\n"
        f"😀 Icon: {category.icon}\n"
        f"📄 Description: {category.description or 'No description'}\n"
        f"🆔 ID: <code>{category.id}</code>",
        parse_mode="HTML",
    )


# Delete/Archive Category Flow
@router.callback_query(F.data == "cat:delete:select")
async def handle_delete_category_select(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Show list of user's categories for deletion."""
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    # Get all user's active categories
    categories = await CategoryService.get_user_categories(
        user=user,
        session=session,
        include_archived=False,
    )
    
    if not categories:
        await callback.message.edit_text(
            "❌ No categories found.",
        )
        await callback.answer()
        await state.clear()
        return
    
    await state.set_state(ArchiveCategory.selecting_category)
    
    keyboard = user_categories_keyboard(categories)
    
    await callback.message.edit_text(
        "🗑️ Delete Category\n\n"
        "Select category to delete:",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(ArchiveCategory.selecting_category, F.data.startswith("cat:select:"))
async def handle_delete_category_selected(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Handle category selection for deletion/archiving."""
    category_id = int(callback.data.split(":")[-1])
    
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    category = await CategoryService.get_category_by_id(category_id, user, session)
    
    if not category:
        await callback.message.edit_text("❌ Category not found!")
        await callback.answer()
        await state.clear()
        return
    
    # Check if category has transactions
    from models.transactions import Transaction
    from sqlalchemy import select
    stmt = select(Transaction).where(Transaction.category_id == category_id).limit(1)
    result = await session.execute(stmt)
    has_transactions = result.scalar_one_or_none() is not None
    
    await state.update_data(category_id=category_id)
    
    # Get other categories for migration
    other_categories = await CategoryService.get_user_categories(
        user=user,
        include_archived=False,
        session=session,
    )
    other_categories = [c for c in other_categories if c.id != category_id]
    
    await state.set_state(ArchiveCategory.selecting_migration_option)
    
    keyboard = archive_options_keyboard(other_categories, has_transactions)
    
    await callback.message.edit_text(
        f"🗑️ Delete Category: <b>{category.icon} {category.name}</b>\n\n"
        f"This category has transactions: {'Yes' if has_transactions else 'No'}\n\n"
        "Choose action:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(ArchiveCategory.selecting_migration_option, F.data == "cat:archive:keep")
async def handle_archive_keep(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Archive category keeping transactions in archived state."""
    data = await state.get_data()
    category_id = data["category_id"]
    
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    category = await CategoryService.get_category_by_id(category_id, user, session)
    
    if not category:
        await callback.message.edit_text("❌ Category not found!")
        await callback.answer()
        await state.clear()
        return
    
    await CategoryService.archive_category(category_id, user, session, None)
    
    await state.clear()
    
    await callback.message.edit_text(
        f"✅ Category archived!\n\n"
        f"📝 Name: {category.icon} {category.name}\n"
        f"🆔 ID: <code>{category.id}</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(ArchiveCategory.selecting_migration_option, F.data == "cat:archive:migrate:select")
async def handle_archive_migrate_select(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Show categories to migrate to."""
    data = await state.get_data()
    category_id = data["category_id"]
    
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    # Get other categories
    other_categories = await CategoryService.get_user_categories(
        user=user,
        include_archived=False,
        session=session,
    )
    other_categories = [c for c in other_categories if c.id != category_id]
    
    await state.set_state(ArchiveCategory.selecting_target_category)
    
    keyboard = user_categories_keyboard(other_categories)
    
    await callback.message.edit_text(
        "➡️ Migrate to Category\n\n"
        "Select category to migrate transactions to:",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(ArchiveCategory.selecting_target_category, F.data.startswith("cat:select:"))
async def handle_archive_with_migration(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Archive category and migrate transactions."""
    data = await state.get_data()
    category_id = data["category_id"]
    target_category_id = int(callback.data.split(":")[-1])
    
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    category = await CategoryService.get_category_by_id(category_id, user, session)
    target_category = await CategoryService.get_category_by_id(target_category_id, user, session)
    
    if not category or not target_category:
        await callback.message.edit_text("❌ Category not found!")
        await callback.answer()
        await state.clear()
        return
    
    await CategoryService.archive_category(category_id, user, session, target_category_id)
    
    await state.clear()
    
    await callback.message.edit_text(
        f"✅ Category archived and migrated!\n\n"
        f"From: {category.icon} {category.name}\n"
        f"To: {target_category.icon} {target_category.name}\n"
        f"🆔 ID: <code>{category.id}</code>",
        parse_mode="HTML",
    )
    await callback.answer()


# Unarchive Category Flow
@router.callback_query(F.data == "cat:unarchive:select")
async def handle_unarchive_category_select(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Show archived categories for unarchiving."""
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    # Get archived categories
    categories = await CategoryService.get_user_categories(
        user=user,
        session=session,
        include_archived=True,
    )
    categories = [c for c in categories if c.is_archived]
    
    if not categories:
        await callback.message.edit_text(
            "❌ No archived categories found.",
        )
        await callback.answer()
        await state.clear()
        return
    
    await state.set_state(UnarchiveCategory.selecting_category)
    
    keyboard = user_categories_keyboard(categories)
    
    await callback.message.edit_text(
        "📦 Unarchive Category\n\n"
        "Select category to restore:",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(UnarchiveCategory.selecting_category, F.data.startswith("cat:select:"))
async def handle_unarchive_category(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    """Unarchive selected category."""
    category_id = int(callback.data.split(":")[-1])
    
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    category = await CategoryService.unarchive_category(category_id, user, session)
    
    await state.clear()
    
    await callback.message.edit_text(
        f"✅ Category restored!\n\n"
        f"📝 Name: <b>{category.icon} {category.name}</b>\n"
        f"📄 Description: {category.description or 'No description'}\n"
        f"🆔 ID: <code>{category.id}</code>",
        parse_mode="HTML",
    )
    await callback.answer()


# List Categories
@router.callback_query(F.data == "cat:list")
async def handle_list_categories(
    callback: CallbackQuery,
    session: AsyncSession,
):
    """List all user's active categories."""
    user = await UserService.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session=session,
    )
    
    # Get all active categories
    expense_categories = await CategoryService.get_user_categories(
        user=user,
        session=session,
        transaction_type="EXPENSE",
        include_archived=False,
    )
    
    income_categories = await CategoryService.get_user_categories(
        user=user,
        session=session,
        transaction_type="INCOME",
        include_archived=False,
    )
    
    text = "📋 Your Categories\n\n"
    
    if expense_categories:
        text += "💸 <b>Expenses:</b>\n"
        for cat in expense_categories:
            text += f"  • {cat.icon} {cat.name}\n"
        text += "\n"
    
    if income_categories:
        text += "💰 <b>Income:</b>\n"
        for cat in income_categories:
            text += f"  • {cat.icon} {cat.name}\n"
    
    if not expense_categories and not income_categories:
        text = "❌ No categories found."
    
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()


# Cancel handler
@router.callback_query(F.data == "cat:cancel")
async def handle_cancel(callback: CallbackQuery, state: FSMContext):
    """Cancel category management operation."""
    await state.clear()
    keyboard = categories_main_menu()
    
    await callback.message.edit_text(
        "📁 Category Management\n\n"
        "Choose an action:",
        reply_markup=keyboard,
    )
    await callback.answer()

