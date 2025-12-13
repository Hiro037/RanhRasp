"""empty message

Revision ID: 9d5c1d2c44b8
Revises: 92789cf29f08
Create Date: 2025-12-05 17:19:33.765814

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d5c1d2c44b8"
down_revision: Union[str, Sequence[str], None] = "92789cf29f08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Используем batch режим для SQLite
    with op.batch_alter_table("user_requests", schema=None) as batch_op:
        # Создаём Foreign Keys с явными именами
        batch_op.create_foreign_key(
            "fk_user_requests_telegram_id_users",  # явное имя constraint
            "users",
            ["telegram_id"],
            ["user_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_user_requests_username_users",  # явное имя constraint
            "users",
            ["username"],
            ["username"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Используем batch режим для SQLite
    with op.batch_alter_table("user_requests", schema=None) as batch_op:
        # Удаляем Foreign Keys по явным именам
        batch_op.drop_constraint("fk_user_requests_username_users", type_="foreignkey")
        batch_op.drop_constraint(
            "fk_user_requests_telegram_id_users", type_="foreignkey"
        )
