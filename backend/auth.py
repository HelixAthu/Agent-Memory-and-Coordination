"""Authentication dependencies enforcing tenant-scoped API keys and admin access."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Header, HTTPException, Path, status

from memory_core.config import settings
from memory_core.errors import InvalidInputError
from memory_core.tenancy import validate_tenant_id


async def verify_tenant_api_key(
    tenant: Annotated[str, Path(...)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    """Validate X-API-Key header matches the tenant in route path /t/{tenant}/..."""
    try:
        validated_tenant = validate_tenant_id(tenant)
    except InvalidInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required X-API-Key header",
        )

    tenant_keys = settings.get_tenant_api_keys()
    expected_key = tenant_keys.get(validated_tenant)

    if not expected_key or x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid or unauthorized API key for tenant '{validated_tenant}'",
        )

    return validated_tenant


async def verify_admin_key(
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    """Validate X-Admin-Key matches ADMIN_KEY environment setting."""
    expected_admin = os.environ.get("ADMIN_KEY", "admin-demo-key")
    if not x_admin_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required X-Admin-Key header",
        )
    if x_admin_key != expected_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin credentials",
        )
