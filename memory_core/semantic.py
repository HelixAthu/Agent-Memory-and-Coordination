"""Semantic memory layer managing user facts, supersession, reinforcement, and provenance."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from memory_core.clock import now
from memory_core.db import TenantDB, get_tenant_db
from memory_core.embedder import get_embedder
from memory_core.errors import ConflictError, InvalidInputError, NotFoundError
from memory_core.queries import (
    Q_FACT_ACTIVE_ONE,
    Q_FACT_CLOSE_OLD,
    Q_FACT_CREATE,
    Q_FACT_HISTORY,
    Q_FACT_LINK_SOURCE,
    Q_FACT_LINK_SUPERSEDES,
    Q_FACT_REINFORCE,
    Q_FACTS_ACTIVE,
)

ALLOWED_PREDICATES: set[str] = {"plan", "prefers_channel", "city"}

_fact_locks: dict[tuple[str, str, str], asyncio.Lock] = {}
_global_fact_lock: asyncio.Lock = asyncio.Lock()


async def _get_fact_lock(tenant_id: str, user_id: str, predicate: str) -> asyncio.Lock:
    """Retrieve or initialize an asyncio.Lock for a specific tenant, user, and predicate."""
    key = (tenant_id, user_id, predicate)
    if key not in _fact_locks:
        async with _global_fact_lock:
            if key not in _fact_locks:
                _fact_locks[key] = asyncio.Lock()
    return _fact_locks[key]


def normalize_object(predicate: str, obj: str) -> str:
    """Normalize object casing according to predicate conventions."""
    cleaned: str = obj.strip()
    if predicate in ("city", "plan"):
        return cleaned.capitalize()
    if predicate == "prefers_channel":
        return cleaned.lower()
    return cleaned


async def remember_fact(
    tenant_id: str,
    user_id: str,
    predicate: str,
    object_: str,
    confidence: float = 0.8,
    session_id: str | None = None,
    max_attempts: int = 10,
) -> dict[str, Any]:
    """Store, reinforce, or supersede a semantic user fact using conditional CAS queries."""
    if predicate not in ALLOWED_PREDICATES:
        raise InvalidInputError(
            f"Invalid predicate '{predicate}'. Allowed predicates: {sorted(ALLOWED_PREDICATES)}"
        )

    lock = await _get_fact_lock(tenant_id, user_id, predicate)
    async with lock:
        return await _remember_fact_inner(
            tenant_id=tenant_id,
            user_id=user_id,
            predicate=predicate,
            object_=object_,
            confidence=confidence,
            session_id=session_id,
            max_attempts=max_attempts,
        )


async def _remember_fact_inner(
    tenant_id: str,
    user_id: str,
    predicate: str,
    object_: str,
    confidence: float = 0.8,
    session_id: str | None = None,
    max_attempts: int = 10,
) -> dict[str, Any]:


    db: TenantDB = await get_tenant_db(tenant_id)
    embedder = get_embedder()

    # Verify user exists
    user_check: list[Any] = await db.run_ro(
        "MATCH (u:User {id: $uid}) RETURN u.id",
        {"uid": user_id},
    )
    if not user_check:
        raise NotFoundError(f"User '{user_id}' does not exist in tenant '{tenant_id}'")

    norm_obj: str = normalize_object(predicate, object_)

    for _ in range(max_attempts):
        active_res: list[Any] = await db.run_ro(
            Q_FACT_ACTIVE_ONE,
            {"uid": user_id, "pred": predicate},
        )
        active = active_res[0] if active_res else None

        # 1. Reinforcement if identical object already active
        if active is not None and str(active[1]).lower() == norm_obj.lower():
            active_id: str = str(active[0])
            ts: int = now()
            reinf_res: list[Any] = await db.run_rw(
                Q_FACT_REINFORCE,
                {"fid": active_id, "ts": ts},
            )
            reinf_conf: float = round(float(reinf_res[0][0]), 4) if reinf_res else confidence
            return {
                "action": "reinforced",
                "fact_id": active_id,
                "confidence": reinf_conf,
            }

        # 2. Supersession: conditionally close the old fact
        old_fact_id: str | None = None
        if active is not None:
            old_fact_id = str(active[0])
            ts = now()
            close_res: list[Any] = await db.run_rw(
                Q_FACT_CLOSE_OLD,
                {"old_id": old_fact_id, "ts": ts},
            )
            if not close_res:
                # Concurrent transaction modified or closed this fact; retry loop
                continue

        # 3. Create new fact node with embedding
        new_fact_id: str = f"fact-{uuid.uuid4().hex[:8]}"
        ts = now()
        emb_text: str = f"{predicate} {norm_obj}"
        emb: list[float] = embedder.embed(emb_text)

        await db.run_rw(
            Q_FACT_CREATE,
            {
                "uid": user_id,
                "fid": new_fact_id,
                "pred": predicate,
                "obj": norm_obj,
                "conf": confidence,
                "ts": ts,
                "emb": emb,
            },
        )

        if old_fact_id is not None:
            await db.run_rw(
                Q_FACT_LINK_SUPERSEDES,
                {"new_id": new_fact_id, "old_id": old_fact_id},
            )

        if session_id:
            await db.run_rw(
                Q_FACT_LINK_SOURCE,
                {"fid": new_fact_id, "sid": session_id},
            )

        return {
            "action": "superseded" if old_fact_id else "created",
            "fact_id": new_fact_id,
            "old_fact_id": old_fact_id,
            "confidence": confidence,
        }

    raise ConflictError(
        f"Failed to update fact for predicate '{predicate}' after {max_attempts} attempts due to concurrency"
    )


async def get_profile(tenant_id: str, user_id: str) -> list[dict[str, Any]]:
    """Retrieve active facts forming the user's semantic profile."""
    db: TenantDB = await get_tenant_db(tenant_id)
    rows: list[Any] = await db.run_ro(Q_FACTS_ACTIVE, {"uid": user_id})
    return [
        {
            "id": row[0],
            "predicate": row[1],
            "object": row[2],
            "confidence": round(float(row[3]), 4),
            "valid_from": row[4],
        }
        for row in rows
    ]


async def get_history(tenant_id: str, user_id: str, predicate: str) -> list[dict[str, Any]]:
    """Retrieve full history (active and superseded) for a specific predicate."""
    if predicate not in ALLOWED_PREDICATES:
        raise InvalidInputError(
            f"Invalid predicate '{predicate}'. Allowed predicates: {sorted(ALLOWED_PREDICATES)}"
        )
    db: TenantDB = await get_tenant_db(tenant_id)
    rows: list[Any] = await db.run_ro(
        Q_FACT_HISTORY,
        {"uid": user_id, "pred": predicate},
    )
    return [
        {
            "id": row[0],
            "object": row[1],
            "status": row[2],
            "valid_from": row[3],
            "valid_to": row[4],
        }
        for row in rows
    ]
