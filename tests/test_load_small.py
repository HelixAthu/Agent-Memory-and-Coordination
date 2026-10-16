"""Fast unit tests for concurrency load invariants C1, C2, and C3 (scaled down)."""

from __future__ import annotations

import pytest

from memory_core.loadtest import cleanup_scratch_tenant, run_c1, run_c2, run_c3, setup_scratch_tenant


@pytest.fixture(autouse=True)
async def scratch_tenant_fixture():
    """Ensure a clean scratch tenant before and after tests."""
    tenant = "load_test_unit"
    await setup_scratch_tenant(tenant)
    yield tenant
    await cleanup_scratch_tenant(tenant)


@pytest.mark.asyncio
async def test_c1_small(scratch_tenant_fixture: str):
    """Verify C1: 20 claimants compete for 1 task; exactly 1 succeeds, 19 yield CONFLICT."""
    res = await run_c1(scratch_tenant_fixture, num_claimants=20)
    assert res["passed"] is True, res["detail"]


@pytest.mark.asyncio
async def test_c2_small(scratch_tenant_fixture: str):
    """Verify C2: 40 tasks claimed by 5 concurrent workers; 0 duplicates, all 40 claimed."""
    res = await run_c2(scratch_tenant_fixture, num_tasks=40, num_workers=5)
    assert res["passed"] is True, res["detail"]


@pytest.mark.asyncio
async def test_c3_small(scratch_tenant_fixture: str):
    """Verify C3: 5 workers x 5 CAS increments reach exactly 25 with optimistic retries."""
    res = await run_c3(scratch_tenant_fixture, num_workers=5, increments_per_worker=5)
    assert res["passed"] is True, res["detail"]
