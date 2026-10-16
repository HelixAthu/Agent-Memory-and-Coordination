"""Persistent conversation message history with atomic sequence assignment and chain linking."""

from __future__ import annotations

import uuid
from typing import Any

from memory_core.clock import now
from memory_core.db import TenantDB, get_tenant_db
from memory_core.errors import NotFoundError
from memory_core.queries import Q_MSG_APPEND, Q_MSG_LINK, Q_MSG_LIST, Q_SESSION_CREATE


async def create_session(
    tenant_id: str,
    user_id: str,
    current_agent: str,
    session_id: str | None = None,
) -> str:
    """Create a new session in OPEN status attached to the specified user."""
    db: TenantDB = await get_tenant_db(tenant_id)
    sid: str = session_id or f"sess-{uuid.uuid4().hex[:8]}"
    ts: int = now()

    # Verify user exists
    user_check: list[Any] = await db.run_ro(
        "MATCH (u:User {id: $uid}) RETURN u.id",
        {"uid": user_id},
    )
    if not user_check:
        raise NotFoundError(f"User '{user_id}' does not exist in tenant '{tenant_id}'")

    await db.run_rw(
        Q_SESSION_CREATE,
        {
            "uid": user_id,
            "sid": sid,
            "ts": ts,
            "agent": current_agent,
        },
    )
    return sid


async def append_message(
    tenant_id: str,
    session_id: str,
    role: str,
    text: str,
    agent_id: str | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Atomically append a message to a session, assigning sequence and linking to previous."""
    db: TenantDB = await get_tenant_db(tenant_id)
    mid: str = message_id or f"msg-{session_id}-{uuid.uuid4().hex[:6]}"
    ts: int = now()

    res: list[Any] = await db.run_rw(
        Q_MSG_APPEND,
        {
            "sid": session_id,
            "mid": mid,
            "role": role,
            "agent": agent_id or "",
            "text": text,
            "ts": ts,
        },
    )
    if not res:
        raise NotFoundError(f"Session '{session_id}' not found in tenant '{tenant_id}'")

    seq: int = int(res[0][0])

    # Link with previous message in the chain if seq > 1
    if seq > 1:
        await db.run_rw(
            Q_MSG_LINK,
            {
                "sid": session_id,
                "prev": seq - 1,
                "mid": mid,
            },
        )

    return {
        "id": mid,
        "session_id": session_id,
        "seq": seq,
        "role": role,
        "agent_id": agent_id,
        "text": text,
        "ts": ts,
    }


async def get_messages(
    tenant_id: str,
    session_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Retrieve message history for a session in chronological order (oldest first)."""
    db: TenantDB = await get_tenant_db(tenant_id)
    limit_int: int = max(1, min(int(limit), 200))
    query: str = Q_MSG_LIST.replace("{LIMIT}", str(limit_int))

    rows: list[Any] = await db.run_ro(query, {"sid": session_id})
    messages: list[dict[str, Any]] = [
        {
            "seq": row[0],
            "role": row[1],
            "agent_id": row[2] if row[2] else None,
            "text": row[3],
            "ts": row[4],
        }
        for row in rows
    ]
    # Reverse DESC results from FalkorDB query to restore oldest-first order
    messages.reverse()
    return messages
