"""Coordination primitives: task management, atomic claiming, and optimistic shared state (CAS)."""

from __future__ import annotations

import re
import uuid
from typing import Any

from memory_core.clock import now as get_now
from memory_core.clock import now_ms as get_now_ms
from memory_core.db import TenantDB, get_tenant_db
from memory_core.errors import ConflictError, InvalidInputError, NotFoundError
from memory_core.queries import (
    Q_STATE_CAS,
    Q_STATE_GET,
    Q_TASK_CLAIM,
    Q_TASK_CLAIM_NEXT,
    Q_TASK_CREATE,
    Q_TASK_DONE,
    Q_TASK_LINK_USER,
)

KEY_REGEX: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


# ---------------------------------------------------------------------------
# 1. Task Operations
# ---------------------------------------------------------------------------


async def create_task(
    tenant_id: str,
    title: str,
    priority: int = 1,
    user_id: str | None = None,
    task_id: str | None = None,
) -> str:
    """Create a new coordination task in OPEN status."""
    db: TenantDB = await get_tenant_db(tenant_id)
    tid: str = task_id or f"task-{uuid.uuid4().hex[:8]}"
    ts_ms: int = get_now_ms()

    await db.run_rw(
        Q_TASK_CREATE,
        {
            "id": tid,
            "title": title,
            "prio": int(priority),
            "ts": ts_ms,
        },
    )

    if user_id:
        await db.run_rw(
            Q_TASK_LINK_USER,
            {"id": tid, "uid": user_id},
        )

    return tid


async def claim_task(
    tenant_id: str,
    task_id: str,
    agent_id: str,
) -> int:
    """Atomically claim an OPEN task for an agent, incrementing version."""
    db: TenantDB = await get_tenant_db(tenant_id)
    res: list[Any] = await db.run_rw(
        Q_TASK_CLAIM,
        {"id": task_id, "agent": agent_id},
    )
    if res:
        return int(res[0][1])

    # Inspect failure reason
    check_res: list[Any] = await db.run_ro(
        "MATCH (t:Task {id: $id}) RETURN t.status, t.version",
        {"id": task_id},
    )
    if not check_res:
        raise NotFoundError(f"Task '{task_id}' not found in tenant '{tenant_id}'")

    current_status: str = str(check_res[0][0])
    current_version: int = int(check_res[0][1])
    raise ConflictError(
        f"Task '{task_id}' cannot be claimed: status is '{current_status}' (expected 'OPEN')",
        current_version=current_version,
    )


async def claim_next(
    tenant_id: str,
    agent_id: str,
) -> dict[str, Any]:
    """Atomically pick and claim the highest priority OPEN task."""
    db: TenantDB = await get_tenant_db(tenant_id)
    res: list[Any] = await db.run_rw(
        Q_TASK_CLAIM_NEXT,
        {"agent": agent_id},
    )
    if not res:
        raise NotFoundError("No open tasks available to claim")

    return {
        "id": str(res[0][0]),
        "title": str(res[0][1]),
        "version": int(res[0][2]),
    }


async def complete_task(
    tenant_id: str,
    task_id: str,
    agent_id: str,
) -> None:
    """Mark a CLAIMED task as DONE by the claiming agent."""
    db: TenantDB = await get_tenant_db(tenant_id)
    res: list[Any] = await db.run_rw(
        Q_TASK_DONE,
        {"id": task_id, "agent": agent_id},
    )
    if not res:
        check_res: list[Any] = await db.run_ro(
            "MATCH (t:Task {id: $id}) RETURN t.status, t.claimed_by",
            {"id": task_id},
        )
        if not check_res:
            raise NotFoundError(f"Task '{task_id}' not found in tenant '{tenant_id}'")
        raise ConflictError(
            f"Cannot complete task '{task_id}': status='{check_res[0][0]}', claimed_by='{check_res[0][1]}'"
        )


# ---------------------------------------------------------------------------
# 2. Shared State (Optimistic Concurrency Control / CAS)
# ---------------------------------------------------------------------------


def _validate_state_key(key: str) -> None:
    """Ensure state key matches lowercase snake_case identifier constraint."""
    if not KEY_REGEX.match(key):
        raise InvalidInputError(
            f"Invalid state key '{key}'. Must match pattern '^[a-z][a-z0-9_]{{0,31}}$'"
        )


async def get_state(
    tenant_id: str,
    session_id: str,
    key: str,
) -> dict[str, Any]:
    """Retrieve the value and version of a session state entry."""
    _validate_state_key(key)
    db: TenantDB = await get_tenant_db(tenant_id)
    res: list[Any] = await db.run_ro(
        Q_STATE_GET,
        {"sid": session_id, "key": key},
    )
    if not res:
        raise NotFoundError(f"State key '{key}' not found for session '{session_id}'")

    return {
        "value": str(res[0][0]),
        "version": int(res[0][1]),
    }


async def set_state(
    tenant_id: str,
    session_id: str,
    key: str,
    value: str,
    expected_version: int,
    agent_id: str,
) -> int:
    """Atomically create or update a shared session state entry with version checking."""
    _validate_state_key(key)
    if len(value) > 2000:
        raise InvalidInputError("State value exceeds maximum length of 2000 characters")

    db: TenantDB = await get_tenant_db(tenant_id)
    eid: str = f"st-{session_id}-{key}"
    ts: int = get_now()

    if expected_version == 0:
        # Atomic creation via MERGE with ON CREATE per Section 6.5 fallback
        create_cypher: str = (
            "MATCH (s:Session {id: $sid}) "
            "MERGE (e:StateEntry {id: $eid}) "
            "ON CREATE SET e.key = $key, e.value = $value, e.version = 1, "
            "              e.updated_by = $agent, e.updated_at = $ts "
            "MERGE (s)-[:HAS_STATE]->(e) "
            "RETURN e.version AS version, e.value AS value"
        )
        res: list[Any] = await db.run_rw(
            create_cypher,
            {
                "sid": session_id,
                "eid": eid,
                "key": key,
                "value": value,
                "agent": agent_id,
                "ts": ts,
            },
        )
        if not res:
            raise NotFoundError(f"Session '{session_id}' not found in tenant '{tenant_id}'")

        actual_version: int = int(res[0][0])
        actual_value: str = str(res[0][1])
        if actual_version != 1 or actual_value != value:
            raise ConflictError(
                f"State entry '{key}' already exists with version {actual_version}",
                current_version=actual_version,
            )
        return 1

    # Update existing state with CAS
    res = await db.run_rw(
        Q_STATE_CAS,
        {
            "eid": eid,
            "expected": expected_version,
            "value": value,
            "agent": agent_id,
            "ts": ts,
        },
    )
    if res:
        return int(res[0][0])

    # Inspect current state to report conflict
    current_res: list[Any] = await db.run_ro(
        "MATCH (e:StateEntry {id: $eid}) RETURN e.version",
        {"eid": eid},
    )
    if not current_res:
        raise NotFoundError(f"State key '{key}' not found for session '{session_id}'")

    current_ver: int = int(current_res[0][0])
    raise ConflictError(
        f"CAS mismatch for key '{key}': expected {expected_version}, found {current_ver}",
        current_version=current_ver,
    )
