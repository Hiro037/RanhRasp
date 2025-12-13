"""Добавление столбцов в UserRequest

Revision ID: 92789cf29f08
Revises: f7347afe74cc
Create Date: 2025-12-05 16:39:13.340508

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "92789cf29f08"
down_revision: Union[str, Sequence[str], None] = "f7347afe74cc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy import inspect

    # Проверяем, существует ли колонка
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("user_requests")]

    with op.batch_alter_table("user_requests", schema=None) as batch_op:
        # Добавляем колонки только если их нет
        if "telegram_id" not in columns:
            batch_op.add_column(
                sa.Column(
                    "telegram_id", sa.BigInteger(), nullable=False, server_default="0"
                )
            )
            batch_op.create_index(
                "ix_user_requests_telegram_id", ["telegram_id"], unique=False
            )
            batch_op.create_foreign_key(
                "fk_user_requests_telegram_id_users",
                "users",
                ["telegram_id"],
                ["user_id"],
                ondelete="CASCADE",
            )

        if "username" not in columns:
            batch_op.add_column(
                sa.Column("username", sa.String(length=255), nullable=True)
            )
            batch_op.create_index(
                "ix_user_requests_username", ["username"], unique=False
            )
            batch_op.create_foreign_key(
                "fk_user_requests_username_users",
                "users",
                ["username"],
                ["username"],
                ondelete="CASCADE",
            )


def downgrade() -> None:
    """Downgrade schema."""
    # Используем batch режим для SQLite
    with op.batch_alter_table("user_requests", schema=None) as batch_op:
        # Удаляем Foreign Keys (с явными именами)
        batch_op.drop_constraint("fk_user_requests_username_users", type_="foreignkey")
        batch_op.drop_constraint(
            "fk_user_requests_telegram_id_users", type_="foreignkey"
        )

        # Удаляем индексы
        batch_op.drop_index("ix_user_requests_username")
        batch_op.drop_index("ix_user_requests_telegram_id")

        # Удаляем колонки
        batch_op.drop_column("username")
        batch_op.drop_column("telegram_id")
