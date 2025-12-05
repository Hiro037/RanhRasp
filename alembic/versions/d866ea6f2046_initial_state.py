"""Initial state

Revision ID: d866ea6f2046
Revises: 2c762e8022c8
Create Date: 2025-12-05 16:21:23.181619

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd866ea6f2046'
down_revision: Union[str, Sequence[str], None] = '2c762e8022c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
