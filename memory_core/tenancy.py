"""Tenant validation and graph naming enforcing multi-tenant isolation."""

from __future__ import annotations

import re
from memory_core.config import settings
from memory_core.errors import ForbiddenError, InvalidInputError

TENANT_ID_REGEX: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]{2,31}$")


def validate_tenant_id(tenant_id: str) -> str:
    """Validate that tenant_id matches the required regex ^[a-z][a-z0-9_]{2,31}$.

    Raises InvalidInputError if the tenant identifier is malformed.
    """
    if not isinstance(tenant_id, str) or not TENANT_ID_REGEX.match(tenant_id):
        raise InvalidInputError(
            f"Invalid tenant_id '{tenant_id}'. Must match pattern ^[a-z][a-z0-9_]{{2,31}}$ (3 to 32 chars)."
        )
    return tenant_id


def graph_name(tenant_id: str) -> str:
    """Return the physical FalkorDB graph name for the tenant (mem_<tenant_id>)."""
    valid_id = validate_tenant_id(tenant_id)
    return f"mem_{valid_id}"


def get_allowed_tenants() -> list[str]:
    """Return the list of allowed tenants configured in the environment."""
    return settings.get_allowed_tenants()


def assert_tenant_allowed(tenant_id: str) -> None:
    """Ensure tenant_id is both valid and permitted by the active tenancy configuration."""
    valid_id = validate_tenant_id(tenant_id)
    allowed = get_allowed_tenants()
    if allowed and valid_id not in allowed:
        raise ForbiddenError(f"Tenant '{valid_id}' is not in allowed tenants: {allowed}")
