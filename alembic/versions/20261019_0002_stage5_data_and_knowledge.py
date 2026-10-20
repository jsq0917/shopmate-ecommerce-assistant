"""Stage 5: catalog, order and knowledge/ingestion tables.

Revision ID: 20261019_0002
Revises: 20261018_0001
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261019_0002"
down_revision: str | None = "20261018_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, tuple[str, ...]] = {
    "user_role": ("shopper", "support", "admin"),
    "product_status": ("draft", "active", "archived"),
    "variant_status": ("active", "inactive", "discontinued"),
    "order_status": (
        "created",
        "paid",
        "processing",
        "shipped",
        "delivered",
        "completed",
        "cancelled",
    ),
    "order_item_status": ("active", "cancelled", "returned"),
    "shipment_status": (
        "pending",
        "picked_up",
        "in_transit",
        "out_for_delivery",
        "delivered",
        "exception",
    ),
    "knowledge_base_status": ("active", "archived"),
    "knowledge_doc_type": (
        "policy",
        "faq",
        "manual",
        "warranty",
        "invoice",
        "shipping",
        "other",
    ),
    "knowledge_document_status": ("draft", "active", "archived"),
    "parse_status": ("pending", "processing", "ready", "failed", "withdrawn"),
    "ingestion_status": ("queued", "running", "succeeded", "failed"),
}


def _enum(name: str) -> postgresql.ENUM:
    """Return a reference to an enum type created by :func:`upgrade`."""
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "shops",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("locale", sa.String(16), nullable=False, server_default="zh-CN"),
        sa.Column("currency", sa.CHAR(3), nullable=False, server_default=sa.text("'CNY'")),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default=sa.text("true")),
        *_timestamps(),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("email_ci", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", _enum("user_role"), nullable=False, server_default=sa.text("'shopper'")),
        sa.Column("display_name_masked", sa.String(120), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("shop_id", "id", name="uq_users_shop_id_id"),
    )
    op.create_index(
        "uq_users_shop_email",
        "users",
        ["shop_id", sa.text("lower(email_ci)")],
        unique=True,
    )
    op.create_index(
        "ix_users_shop_role_active",
        "users",
        ["shop_id", "role"],
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("brand", sa.String(120), nullable=True),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column(
            "attributes_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status", _enum("product_status"), nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("shop_id", "id", name="uq_products_shop_id_id"),
    )
    op.create_index(
        "ix_products_shop_status_category",
        "products",
        ["shop_id", "status", "category"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "product_variants",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column(
            "attributes_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("price_cents", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False, server_default=sa.text("'CNY'")),
        sa.Column(
            "status", _enum("variant_status"), nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["shop_id", "product_id"],
            ["products.shop_id", "products.id"],
            name="fk_variants_product_same_shop",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("shop_id", "id", name="uq_variants_shop_id_id"),
        sa.UniqueConstraint("shop_id", "sku", name="uq_variants_shop_sku"),
        sa.CheckConstraint("price_cents >= 0", name="ck_variants_price_non_negative"),
    )
    op.create_index(
        "ix_variants_product_status", "product_variants", ["shop_id", "product_id", "status"]
    )

    op.create_table(
        "inventory",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("variant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("warehouse_code", sa.String(40), nullable=False),
        sa.Column("available_qty", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reserved_qty", sa.Integer, nullable=False, server_default="0"),
        sa.Column("source_system", sa.String(32), nullable=False, server_default="mock_oms"),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["shop_id", "variant_id"],
            ["product_variants.shop_id", "product_variants.id"],
            name="fk_inventory_variant_same_shop",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("available_qty >= 0", name="ck_inventory_available_non_negative"),
        sa.CheckConstraint("reserved_qty >= 0", name="ck_inventory_reserved_non_negative"),
        sa.UniqueConstraint(
            "shop_id", "variant_id", "warehouse_code", name="uq_inventory_variant_warehouse"
        ),
    )
    op.create_index(
        "ix_inventory_variant_updated", "inventory", ["shop_id", "variant_id", "updated_at"]
    )

    op.create_table(
        "promotions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column(
            "rule_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.CheckConstraint("ends_at > starts_at", name="ck_promotions_window"),
    )
    op.create_index(
        "ix_promotions_shop_time", "promotions", ["shop_id", "status", "starts_at", "ends_at"]
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_no", sa.String(40), nullable=False),
        sa.Column(
            "status", _enum("order_status"), nullable=False, server_default=sa.text("'created'")
        ),
        sa.Column("total_cents", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False, server_default=sa.text("'CNY'")),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipping_address_masked", sa.String(240), nullable=True),
        sa.Column("source_system", sa.String(32), nullable=False, server_default="mock_oms"),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["shop_id", "user_id"],
            ["users.shop_id", "users.id"],
            name="fk_orders_user_same_shop",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("shop_id", "id", name="uq_orders_shop_id_id"),
        sa.UniqueConstraint("shop_id", "id", "user_id", name="uq_orders_shop_id_user_id"),
        sa.UniqueConstraint("shop_id", "order_no", name="uq_orders_shop_order_no"),
        sa.CheckConstraint("total_cents >= 0", name="ck_orders_total_non_negative"),
    )
    op.create_index("ix_orders_shop_user_placed", "orders", ["shop_id", "user_id", "placed_at"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("variant_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("sku_snapshot", sa.String(80), nullable=False),
        sa.Column("title_snapshot", sa.String(240), nullable=False),
        sa.Column("category_snapshot", sa.String(120), nullable=False),
        sa.Column(
            "is_returnable_snapshot", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger, nullable=False),
        sa.Column("line_total_cents", sa.BigInteger, nullable=False),
        sa.Column(
            "status", _enum("order_item_status"), nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["shop_id", "order_id"],
            ["orders.shop_id", "orders.id"],
            name="fk_order_items_order_same_shop",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("shop_id", "id", "order_id", name="uq_order_items_shop_id_order_id"),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        sa.CheckConstraint("unit_price_cents >= 0", name="ck_order_items_unit_price"),
        sa.CheckConstraint("line_total_cents >= 0", name="ck_order_items_line_total"),
    )
    op.create_index("ix_order_items_order", "order_items", ["shop_id", "order_id"])
    op.create_index("ix_order_items_user_window", "order_items", ["shop_id", "delivered_at"])

    op.create_table(
        "shipments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("carrier", sa.String(80), nullable=False),
        sa.Column("tracking_no_masked", sa.String(80), nullable=False),
        sa.Column("tracking_no_hash", sa.LargeBinary, nullable=True),
        sa.Column(
            "status", _enum("shipment_status"), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_system", sa.String(32), nullable=False, server_default="mock_oms"),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["shop_id", "order_id"],
            ["orders.shop_id", "orders.id"],
            name="fk_shipments_order_same_shop",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("shop_id", "id", name="uq_shipments_shop_id_id"),
    )
    op.create_index(
        "ix_shipments_order_updated", "shipments", ["shop_id", "order_id", "updated_at"]
    )

    op.create_table(
        "shipment_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("shipment_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sequence_no", sa.Integer, nullable=False),
        sa.Column("status", _enum("shipment_status"), nullable=False),
        sa.Column("description", sa.String(240), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["shop_id", "shipment_id"],
            ["shipments.shop_id", "shipments.id"],
            name="fk_shipment_events_shipment_same_shop",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("shop_id", "shipment_id", "sequence_no", name="uq_shipment_events_seq"),
    )

    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("locale", sa.String(16), nullable=False, server_default="zh-CN"),
        sa.Column("region", sa.String(8), nullable=False, server_default="CN"),
        sa.Column(
            "status",
            _enum("knowledge_base_status"),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name="fk_knowledge_bases_shop", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("shop_id", "id", name="uq_knowledge_bases_shop_id_id"),
        sa.UniqueConstraint("shop_id", "name", name="uq_knowledge_base_name"),
    )

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("doc_type", _enum("knowledge_doc_type"), nullable=False),
        sa.Column("locale", sa.String(16), nullable=False, server_default="zh-CN"),
        sa.Column("region", sa.String(8), nullable=False, server_default="CN"),
        sa.Column(
            "status",
            _enum("knowledge_document_status"),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("current_version_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["shop_id", "knowledge_base_id"],
            ["knowledge_bases.shop_id", "knowledge_bases.id"],
            name="fk_documents_kb_same_shop",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("shop_id", "id", name="uq_documents_shop_id_id"),
    )
    op.create_index(
        "ix_documents_scope",
        "knowledge_documents",
        ["shop_id", "knowledge_base_id", "status"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "knowledge_versions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("source_uri", sa.Text, nullable=False),
        sa.Column("source_filename", sa.String(240), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("content_hash", sa.LargeBinary, nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "parse_status",
            _enum("parse_status"),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("failure_message_safe", sa.Text, nullable=True),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["shop_id", "document_id"],
            ["knowledge_documents.shop_id", "knowledge_documents.id"],
            name="fk_versions_document_same_shop",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("shop_id", "id", name="uq_versions_shop_id_id"),
        sa.UniqueConstraint(
            "shop_id", "document_id", "version", name="uq_versions_document_version"
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_versions_effective_window",
        ),
    )
    op.create_index(
        "ix_versions_effective",
        "knowledge_versions",
        ["shop_id", "parse_status", "effective_from", "effective_to"],
    )
    op.create_foreign_key(
        "fk_documents_current_version",
        "knowledge_documents",
        "knowledge_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("parent_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column(
            "heading_path",
            postgresql.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("page_no", sa.Integer, nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("content_hash", sa.LargeBinary, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "metadata_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *_timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["shop_id", "version_id"],
            ["knowledge_versions.shop_id", "knowledge_versions.id"],
            name="fk_chunks_version_same_shop",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("chunk_index >= 0", name="ck_chunks_index_non_negative"),
        sa.CheckConstraint("page_no IS NULL OR page_no > 0", name="ck_chunks_page_positive"),
        sa.CheckConstraint("token_count >= 0", name="ck_chunks_token_non_negative"),
        sa.UniqueConstraint("shop_id", "version_id", "chunk_index", name="uq_chunks_version_index"),
    )
    op.create_index(
        "ix_chunks_retrieval_scope",
        "knowledge_chunks",
        ["shop_id", "knowledge_base_id", "version_id"],
        postgresql_where=sa.text("is_enabled AND deleted_at IS NULL"),
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shop_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            _enum("ingestion_status"),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message_safe", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["shop_id", "version_id"],
            ["knowledge_versions.shop_id", "knowledge_versions.id"],
            name="fk_jobs_version_same_shop",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("attempt_count > 0", name="ck_jobs_attempt_positive"),
    )
    op.create_index("ix_ingestion_status", "ingestion_jobs", ["shop_id", "status", "created_at"])


def downgrade() -> None:
    op.drop_table("ingestion_jobs")
    op.drop_table("knowledge_chunks")
    op.drop_constraint("fk_documents_current_version", "knowledge_documents", type_="foreignkey")
    op.drop_table("knowledge_versions")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_bases")
    op.drop_table("shipment_events")
    op.drop_table("shipments")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("promotions")
    op.drop_table("inventory")
    op.drop_table("product_variants")
    op.drop_table("products")
    op.drop_table("users")
    op.drop_table("shops")

    bind = op.get_bind()
    for name in reversed(list(ENUMS)):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
