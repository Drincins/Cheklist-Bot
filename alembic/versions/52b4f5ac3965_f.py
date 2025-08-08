"""f

Revision ID: 52b4f5ac3965
Revises: 86642aac70b5
Create Date: 2025-08-09 01:38:45.772989

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52b4f5ac3965'
down_revision: Union[str, Sequence[str], None] = '86642aac70b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
