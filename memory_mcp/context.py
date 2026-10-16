"""Context validation enforcing multi-tenant isolation, agent authorization, and session ownership."""

from __future__ import annotations

from typing import Any

from memory_core.config import settings
from memory_core.db import TenantDB, get_tenant_db
from memory_core.errors import ForbiddenError, InvalidInputError, NotFoundError
from memory_core.tenancy import validate_tenant_id
from memory_mcp.allowlist import is_tool_allowed


async def validate_context(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
    tool_name: str | None = None,
) -> str:
    """Validate invocation context and agent permissions, returning the agent's verified role."""
    # 1. Tenant validation: syntax and configured tenant allowlist
    valid_tenant = validate_tenant_id(tenant_id)
    if valid_tenant not in settings.tenants_list:
        raise InvalidInputError(f"Tenant '{valid_tenant}' is not among configured tenants")

    db: TenantDB = await get_tenant_db(valid_tenant)

    # 2. Agent existence and role allowlist enforcement
    agent_res: list[Any] = await db.run_ro(
        "MATCH (a:Agent {id: $aid}) RETURN a.role",
        {"aid": agent_id},
    )
    if not agent_res:
        raise ForbiddenError(f"Agent '{agent_id}' not found in tenant '{valid_tenant}'")

    role: str = str(agent_res[0][0])

    if tool_name is not None and not is_tool_allowed(role, tool_name):
        raise ForbiddenError(
            f"Agent '{agent_id}' (role '{role}') is forbidden from calling tool '{tool_name}'"
        )

    # 3. User existence
    user_res: list[Any] = await db.run_ro(
        "MATCH (u:User {id: $uid}) RETURN u.id",
        {"uid": user_id},
    )
    if not user_res:
        raise NotFoundError(f"User '{user_id}' not found in tenant '{valid_tenant}'")

    # 4. Session ownership
    if session_id:
        sess_res: list[Any] = await db.run_ro(
            "MATCH (s:Session {id: $sid}) RETURN s.user_id",
            {"sid": session_id},
        )
        if sess_res:
            session_owner: str = str(sess_res[0][0])
            if session_owner != user_id:
                raise ForbiddenError(
                    f"Session '{session_id}' belongs to user '{session_owner}', not caller '{user_id}'"
                )

    return role
