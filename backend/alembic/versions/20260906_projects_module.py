"""add projects.module column

Revision ID: 20260906_projects_module
Revises: 20260905_fire_orders_pipeline
Create Date: 2026-09-05

Additive only. Safe if column/index already exist on live DB.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260906_projects_module"
down_revision = "20260905_fire_orders_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "projects" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("projects")}
    if "module" not in cols:
        op.add_column(
            "projects",
            sa.Column(
                "module",
                sa.String(length=32),
                nullable=False,
                server_default="agro",
            ),
        )
    indexes = {ix["name"] for ix in insp.get_indexes("projects") if ix.get("name")}
    # Re-inspect after potential add
    insp = inspect(bind)
    indexes = {ix["name"] for ix in insp.get_indexes("projects") if ix.get("name")}
    if "ix_projects_module" not in indexes:
        op.create_index("ix_projects_module", "projects", ["module"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "projects" not in insp.get_table_names():
        return
    indexes = {ix["name"] for ix in insp.get_indexes("projects") if ix.get("name")}
    if "ix_projects_module" in indexes:
        op.drop_index("ix_projects_module", table_name="projects")
    cols = {c["name"] for c in insp.get_columns("projects")}
    if "module" in cols:
        op.drop_column("projects", "module")
