"""T098: projects.updated_at column + backfill = created_at.

Revision ID: cc78f2ee52bb
Revises: d82c9915c172
Create Date: 2026-05-17 22:18:14.981409

Phase 1 (см. `specs/T098-manifest-primary/spec.md`) добавил
`Project.updated_at` в domain. Здесь — соответствующая колонка
в `projects` таблице.

Backfill: для существующих строк `updated_at = created_at`
(spec → Clarify #10, принцип наименьшего сюрприза). Для SQLite
делаем три шага через `batch_alter_table`:
1. add column nullable;
2. UPDATE ... SET updated_at = created_at;
3. alter to NOT NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'cc78f2ee52bb'
down_revision: str | Sequence[str] | None = 'd82c9915c172'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('projects') as batch_op:
        batch_op.add_column(
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        )

    op.execute('UPDATE projects SET updated_at = created_at')

    with op.batch_alter_table('projects') as batch_op:
        batch_op.alter_column('updated_at', nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('projects') as batch_op:
        batch_op.drop_column('updated_at')
