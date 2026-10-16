"""Tenant schema, range index, vector index, and constraint provisioning."""

from __future__ import annotations

import logging
from typing import Any

from memory_core.config import settings
from memory_core.db import TenantDB, get_tenant_db
from memory_core.tenancy import validate_tenant_id

logger: logging.Logger = logging.getLogger("memory_core.schema")

INDEXED_LABELS: list[str] = [
    "User",
    "Agent",
    "Entity",
    "Session",
    "Message",
    "Episode",
    "Fact",
    "Procedure",
    "Task",
    "Handoff",
    "StateEntry",
]

PROPERTY_INDEXES: list[tuple[str, str]] = [
    ("Session", "user_id"),
    ("Task", "status"),
    ("Handoff", "status"),
    ("Handoff", "to_agent"),
]

VECTOR_INDEX_LABELS: list[str] = [
    "Episode",
    "Fact",
    "Procedure",
]


async def ensure_tenant(tenant_id: str, dim: int | None = None, db: TenantDB | None = None) -> None:
    """Ensure range indexes, vector indexes, and schema constraints exist for the tenant graph."""
    valid_id = validate_tenant_id(tenant_id)
    target_db: TenantDB = db or await get_tenant_db(valid_id)
    vector_dim: int = int(dim or settings.embed_dim)

    # 1. Range indexes on id for all labels
    for label in INDEXED_LABELS:
        cypher = f"CREATE INDEX FOR (n:{label}) ON (n.id)"
        try:
            await target_db.run_rw(cypher)
            logger.debug("[%s] Created range index on %s.id", valid_id, label)
        except Exception as e:
            # Index already exists or duplicate; continue
            logger.debug("[%s] Range index on %s.id existed or skipped: %s", valid_id, label, e)

    # 2. Specific property range indexes
    for label, prop in PROPERTY_INDEXES:
        cypher = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
        try:
            await target_db.run_rw(cypher)
            logger.debug("[%s] Created property index on %s.%s", valid_id, label, prop)
        except Exception as e:
            logger.debug("[%s] Index on %s.%s existed or skipped: %s", valid_id, label, prop, e)

    # 3. Vector indexes for Episode, Fact, Procedure
    for label in VECTOR_INDEX_LABELS:
        cypher = (
            f"CREATE VECTOR INDEX FOR (n:{label}) ON (n.embedding) "
            f"OPTIONS {{dimension: {vector_dim}, similarityFunction: 'cosine'}}"
        )
        try:
            await target_db.run_rw(cypher)
            logger.info("[%s] Created vector index for %s (dim=%d, cosine)", valid_id, label, vector_dim)
        except Exception as e:
            logger.debug("[%s] Vector index for %s existed or skipped: %s", valid_id, label, e)
