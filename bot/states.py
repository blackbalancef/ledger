"""FSM states for bot conversations."""

from aiogram.fsm.state import State, StatesGroup


class AddExpense(StatesGroup):
    """States for adding an expense."""
    waiting_currency = State()
    waiting_custom_currency = State()
    waiting_category = State()
    waiting_note = State()


class AddIncome(StatesGroup):
    """States for adding income."""
    waiting_amount = State()
    waiting_currency = State()
    waiting_custom_currency = State()
    waiting_category = State()
    waiting_note = State()


class ReportCurrency(StatesGroup):
    """States for selecting report display currency."""
    waiting_currency = State()
    waiting_custom_currency = State()


class AddCategory(StatesGroup):
    """States for adding a new category."""
    waiting_name = State()
    waiting_icon = State()
    waiting_description = State()
    waiting_type = State()


class EditCategory(StatesGroup):
    """States for editing an existing category."""
    selecting_category = State()
    selecting_field = State()
    waiting_value = State()


class ArchiveCategory(StatesGroup):
    """States for archiving a category."""
    selecting_category = State()
    selecting_migration_option = State()
    selecting_target_category = State()


class UnarchiveCategory(StatesGroup):
    """States for unarchiving a category."""
    selecting_category = State()


class SplitBill(StatesGroup):
    """States for splitting a bill."""
    waiting_amount = State()
    waiting_currency = State()
    waiting_custom_currency = State()
    waiting_category = State()
    waiting_split_type = State()
    waiting_custom_amount = State()
    waiting_other_user = State()
    waiting_note = State()


class SettleDebt(StatesGroup):
    """States for settling a debt."""
    selecting_debt = State()

