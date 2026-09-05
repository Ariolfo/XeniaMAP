"""add fire_orders pipeline columns (project/process/firms)

Revision ID: 20260905_fire_orders_pipeline
Revises: 20260904_fire_orders
Create Date: 2026-09-05

Additive only: does not rewrite 20260904_fire_orders.
Aligns ORM FireOrder fields missing from the initial create_table.
Safe on DBs that already have the columns (e.g. patched manually).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260905_fire_orders_pipeline"
down_revision = "20260904_fire_orders"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("project_id", sa.Column("project_id", sa.Integer(), nullable=True)),
    ("results_root", sa.Column("results_root", sa.String(length=1024), nullable=True)),
    ("process_task_id", sa.Column("process_task_id", sa.String(length=255), nullable=True)),
    ("process_message", sa.Column("process_message", sa.Text(), nullable=True)),
    ("process_manifest", sa.Column("process_manifest", sa.JSON(), nullable=True)),
    ("firms_task_id", sa.Column("firms_task_id", sa.String(length=255), nullable=True)),
    ("firms_message", sa.Column("firms_message", sa.Text(), nullable=True)),
    ("firms_manifest", sa.Column("firms_manifest", sa.JSON(), nullable=True)),
)


def _table_names(bind) -> set[str]:
    return set(inspect(bind).get_table_names())


def _existing_columns(bind) -> set[str]:
    insp = inspect(bind)
    if "fire_orders" not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns("fire_orders")}


def _existing_indexes(bind) -> set[str]:
    insp = inspect(bind)
    if "fire_orders" not in insp.get_table_names():
        return set()
    return {ix["name"] for ix in insp.get_indexes("fire_orders") if ix.get("name")}


def _existing_fks(bind) -> set[str]:
    insp = inspect(bind)
    if "fire_orders" not in insp.get_table_names():
        return set()
    return {fk["name"] for fk in insp.get_foreign_keys("fire_orders") if fk.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    if "fire_orders" not in _table_names(bind):
        # Previous revision should have created the table; avoid recreating here.
        return

    cols = _existing_columns(bind)
    for name, column in _COLUMNS:
        if name not in cols:
            op.add_column("fire_orders", column)

    cols = _existing_columns(bind)
    indexes = _existing_indexes(bind)
    if "project_id" in cols and "ix_fire_orders_project_id" not in indexes:
        op.create_index("ix_fire_orders_project_id", "fire_orders", ["project_id"])

    fks = _existing_fks(bind)
    if "project_id" in cols and "fire_orders_project_id_fkey" not in fks:
        op.create_foreign_key(
            "fire_orders_project_id_fkey",
            "fire_orders",
            "projects",
            ["project_id"],
            ["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    cols = _existing_columns(bind)
    if not cols:
        return

    fks = _existing_fks(bind)
    if "fire_orders_project_id_fkey" in fks:
        op.drop_constraint("fire_orders_project_id_fkey", "fire_orders", type_="foreignkey")

    indexes = _existing_indexes(bind)
    if "ix_fire_orders_project_id" in indexes:
        op.drop_index("ix_fire_orders_project_id", table_name="fire_orders")

    for name, _ in reversed(_COLUMNS):
        if name in cols:
            op.drop_column("fire_orders", name)
