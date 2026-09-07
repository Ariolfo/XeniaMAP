"""create fire_orders

Revision ID: 20260904_fire_orders
Revises: 20260714_landing_texts
Create Date: 2026-09-04

Idempotent: safe if table already created by infrastructure/postgres/init.sql.
Pipeline columns may already exist (init ships full shape); 20260905 fills gaps.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260904_fire_orders"
down_revision = "20260714_landing_texts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "fire_orders" in insp.get_table_names():
        return

    op.create_table(
        "fire_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("request_name", sa.String(length=255), nullable=False),
        sa.Column("department", sa.String(length=255), nullable=True),
        sa.Column("applicant_name", sa.String(length=255), nullable=False),
        sa.Column("applicant_email", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("applicant_phone", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("geometry_geojson", sa.JSON(), nullable=False),
        sa.Column("pre_start", sa.Date(), nullable=False),
        sa.Column("pre_end", sa.Date(), nullable=False),
        sa.Column("post_start", sa.Date(), nullable=False),
        sa.Column("post_end", sa.Date(), nullable=False),
        sa.Column("max_cloud_cover", sa.Integer(), nullable=False, server_default="95"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pendiente"),
        sa.Column("download_task_id", sa.String(length=255), nullable=True),
        sa.Column("download_message", sa.Text(), nullable=True),
        sa.Column("download_manifest", sa.JSON(), nullable=True),
        sa.Column("data_root", sa.String(length=1024), nullable=True),
        sa.Column("source_key", sa.String(length=255), nullable=True),
        sa.Column("extra_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("source_key", name="uq_fire_orders_source_key"),
    )
    op.create_index("ix_fire_orders_tenant_id", "fire_orders", ["tenant_id"])
    op.create_index("ix_fire_orders_status", "fire_orders", ["status"])
    op.create_index("ix_fire_orders_source_key", "fire_orders", ["source_key"])
    op.create_index("ix_fire_orders_created_by_user_id", "fire_orders", ["created_by_user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "fire_orders" not in insp.get_table_names():
        return
    indexes = {ix["name"] for ix in insp.get_indexes("fire_orders") if ix.get("name")}
    for name in (
        "ix_fire_orders_created_by_user_id",
        "ix_fire_orders_source_key",
        "ix_fire_orders_status",
        "ix_fire_orders_tenant_id",
    ):
        if name in indexes:
            op.drop_index(name, table_name="fire_orders")
    op.drop_table("fire_orders")
