"""empty message

Revision ID: 7cd98df2ea56
Revises: 9d5c1d2c44b8
Create Date: 2025-12-05 17:30:40.549987

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7cd98df2ea56'
down_revision: Union[str, Sequence[str], None] = '9d5c1d2c44b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Используем batch режим для SQLite
    with op.batch_alter_table('user_requests', schema=None) as batch_op:
        # Удаляем индекс
        batch_op.drop_index('ix_user_requests_username')

        # Удаляем Foreign Keys
        batch_op.drop_constraint('fk_user_requests_telegram_id_users', type_='foreignkey')
        batch_op.drop_constraint('fk_user_requests_username_users', type_='foreignkey')


def downgrade() -> None:
    """Downgrade schema."""
    # Используем batch режим для SQLite
    with op.batch_alter_table('user_requests', schema=None) as batch_op:
        # Восстанавливаем Foreign Keys
        batch_op.create_foreign_key(
            'fk_user_requests_username_users',
            'users',
            ['username'],
            ['username'],
            ondelete='CASCADE'
        )
        batch_op.create_foreign_key(
            'fk_user_requests_telegram_id_users',
            'users',
            ['telegram_id'],
            ['user_id'],
            ondelete='CASCADE'
        )

        # Восстанавливаем индекс
        batch_op.create_index('ix_user_requests_username', ['username'], unique=False)
