"""document_registry table

Revision ID: 008_document_registry
Revises: 007_service_catalog
Create Date: 2026-06-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_document_registry"
down_revision: Union[str, None] = "007_service_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_registry",
        sa.Column("doc_id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("namespace", sa.String(length=100), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_indexed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.org_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("doc_id"),
        sa.UniqueConstraint("org_id", "document_id", name="uq_document_registry_org_doc"),
    )
    op.create_index(
        op.f("ix_document_registry_org_id"), "document_registry", ["org_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_registry_org_id"), table_name="document_registry")
    op.drop_table("document_registry")
