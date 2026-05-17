"""T097: phases table, drop projects.status.

Revision ID: d82c9915c172
Revises: 97a7c34eaf3b
Create Date: 2026-05-17 21:05:38.089565

Структура: создаём таблицу `phases`, бэкфиллим 6 строк (по канониче-
скому порядку CONCEPT §4.3) для каждого существующего проекта в
status `pending`, после чего удаляем колонку `projects.status`
(теперь это `@computed_field` в domain).

SQLite DROP COLUMN поддерживается с 3.35 (2021), но используем
`op.batch_alter_table` для совместимости с любым SQLite-окружением.

Имена фаз вписаны хардкодом — миграция immutable, не должна
ломаться при дальнейшем редактировании `PhaseName` enum.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd82c9915c172'
down_revision: str | Sequence[str] | None = '97a7c34eaf3b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_PHASE_NAMES_BACKFILL: tuple[str, ...] = (
    'schematic',
    'simulation',
    'pcb',
    'magnetics',
    'enclosure',
    'documentation',
)


def upgrade() -> None:
    op.create_table(
        'phases',
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['project_id'], ['projects.id'], ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('project_id', 'name'),
    )

    projects_table = sa.table('projects', sa.column('id', sa.Uuid()))
    phases_table = sa.table(
        'phases',
        sa.column('project_id', sa.Uuid()),
        sa.column('name', sa.String(32)),
        sa.column('status', sa.String(32)),
        sa.column('started_at', sa.DateTime(timezone=True)),
        sa.column('completed_at', sa.DateTime(timezone=True)),
    )
    connection = op.get_bind()
    project_ids = connection.execute(sa.select(projects_table.c.id)).scalars().all()
    if project_ids:
        op.bulk_insert(
            phases_table,
            [
                {
                    'project_id': pid,
                    'name': pname,
                    'status': 'pending',
                    'started_at': None,
                    'completed_at': None,
                }
                for pid in project_ids
                for pname in _PHASE_NAMES_BACKFILL
            ],
        )

    with op.batch_alter_table('projects') as batch_op:
        batch_op.drop_column('status')


def downgrade() -> None:
    with op.batch_alter_table('projects') as batch_op:
        batch_op.add_column(
            sa.Column(
                'status',
                sa.VARCHAR(length=32),
                nullable=False,
                server_default='idea',
            ),
        )
    op.drop_table('phases')
