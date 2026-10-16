"""Unit tests for tenancy validation, graph naming, injectable clock, and concurrency bounding."""

from __future__ import annotations

import asyncio

import pytest

from memory_core.clock import now, now_ms, to_iso
from memory_core.db import TenantDB
from memory_core.errors import InvalidInputError
from memory_core.tenancy import graph_name, validate_tenant_id


def test_valid_tenant_ids_pass() -> None:
    """Assert valid tenant identifiers match regex and pass validation."""
    valid_ids: list[str] = ["acme", "globex", "corp_123", "tenant_a", "abc", "a" * 32]
    for tid in valid_ids:
        assert validate_tenant_id(tid) == tid


def test_invalid_tenant_ids_raise_invalid_input() -> None:
    """Assert invalid tenant ids are rejected with InvalidInputError."""
    invalid_ids: list[str] = [
        "acme; DROP",  # SQL/Cypher injection attempt
        "A",           # Uppercase not allowed
        "ac",          # Too short (< 3 chars)
        "1abc",        # Starts with digit
        "a" * 40,      # Too long (> 32 chars)
        "acme-corp",   # Hyphens not allowed
        "",            # Empty string
    ]
    for tid in invalid_ids:
        with pytest.raises(InvalidInputError):
            validate_tenant_id(tid)


def test_graph_name_mapping() -> None:
    """Assert tenant graph name maps to mem_<tenant_id>."""
    assert graph_name("acme") == "mem_acme"
    assert graph_name("globex") == "mem_globex"


def test_clock_honors_clock_now_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert clock now() and now_ms() honor frozen CLOCK_NOW env variable."""
    frozen_iso = "2026-10-16T00:00:00Z"
    monkeypatch.setenv("CLOCK_NOW", frozen_iso)

    ts = now()
    assert ts == 1792108800
    assert now_ms() == 1792108800000
    assert to_iso(ts) == "2026-10-16T00:00:00Z"


@pytest.mark.asyncio
async def test_max_inflight_concurrency_bounding() -> None:
    """Assert semaphore limits maximum inflight executions to configured limit."""
    max_limit = 5
    db = TenantDB(tenant_id="acme", max_inflight=max_limit)

    current_inflight = 0
    max_observed_inflight = 0
    lock = asyncio.Lock()

    async def worker() -> None:
        nonlocal current_inflight, max_observed_inflight
        async with db.semaphore:
            async with lock:
                current_inflight += 1
                if current_inflight > max_observed_inflight:
                    max_observed_inflight = current_inflight
            # Simulate I/O work
            await asyncio.sleep(0.01)
            async with lock:
                current_inflight -= 1

    # Launch 25 concurrent tasks against max_inflight=5
    await asyncio.gather(*[worker() for _ in range(25)])

    assert max_observed_inflight <= max_limit
    assert max_observed_inflight == max_limit
