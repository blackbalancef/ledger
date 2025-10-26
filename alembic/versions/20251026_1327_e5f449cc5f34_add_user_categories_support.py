"""add_user_categories_support

Revision ID: e5f449cc5f34
Revises: c69d74133aab
Create Date: 2025-10-26 13:27:28.084123

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f449cc5f34'
down_revision: Union[str, None] = 'c69d74133aab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to categories table
    op.add_column('categories', sa.Column('user_id', sa.BigInteger(), nullable=True))
    op.add_column('categories', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('categories', sa.Column('description', sa.Text(), nullable=True))
    
    # Create foreign key
    op.create_foreign_key('fk_categories_user_id', 'categories', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    
    # Create indexes
    op.create_index(op.f('ix_categories_user_id'), 'categories', ['user_id'], unique=False)
    op.create_index(op.f('ix_categories_is_archived'), 'categories', ['is_archived'], unique=False)
    op.create_index('ix_categories_user_type_archived', 'categories', ['user_id', 'transaction_type', 'is_archived'], unique=False)
    
    # Mark existing categories as templates (user_id = NULL)
    # This is already done by NULL default, but we make it explicit
    op.execute("UPDATE categories SET user_id = NULL WHERE user_id IS NULL")
    
    # Copy default categories to all existing users
    # Get all template categories (those with user_id IS NULL)
    connection = op.get_bind()
    result = connection.execute(sa.text("""
        SELECT id, name, transaction_type, icon, is_default
        FROM categories
        WHERE user_id IS NULL
    """))
    template_categories = result.fetchall()
    
    # Get all users
    users_result = connection.execute(sa.text("SELECT id FROM users"))
    users = users_result.fetchall()
    
    # For each user, copy all template categories
    for user in users:
        user_id = user[0]
        for template in template_categories:
            template_id, name, transaction_type, icon, is_default = template
            connection.execute(sa.text("""
                INSERT INTO categories (name, transaction_type, icon, is_default, user_id, is_archived)
                VALUES (:name, :transaction_type, :icon, :is_default, :user_id, false)
            """), {
                'name': name,
                'transaction_type': transaction_type,
                'icon': icon,
                'is_default': is_default,
                'user_id': user_id
            })
    
    # Log the operation
    num_users = len(users)
    num_templates = len(template_categories)
    if num_users and num_templates:
        connection.execute(sa.text(f"""
            COMMENT ON COLUMN categories.user_id IS 
            'NULL for template categories; user_id for user-specific categories. Migration created {num_users * num_templates} user categories.'
        """))


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_categories_user_type_archived', table_name='categories')
    op.drop_index(op.f('ix_categories_is_archived'), table_name='categories')
    op.drop_index(op.f('ix_categories_user_id'), table_name='categories')
    
    # Drop foreign key
    op.drop_constraint('fk_categories_user_id', 'categories', type_='foreignkey')
    
    # Drop columns
    op.drop_column('categories', 'description')
    op.drop_column('categories', 'is_archived')
    op.drop_column('categories', 'user_id')
