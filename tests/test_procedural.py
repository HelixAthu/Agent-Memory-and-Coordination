"""Unit and golden tests for procedural promotion, deprecation, and decay (G6, G10)."""

from __future__ import annotations

from typing import Any

import pytest

from memory_core.db import TenantDB, get_tenant_db
from memory_core.procedural import (
    decay,
    find_procedures,
    promote_procedures,
    record_outcome,
    should_deprecate,
)
from memory_core.recall import recall
from seed.seed import seed_tenant

FROZEN_NOW: int = 1792108800  # 2026-10-16T00:00:00Z


def test_should_deprecate_truth_table() -> None:
    """Verify should_deprecate pure evaluation against the spec truth table."""
    # (0, 5) -> 0+5=5, (0+1)/(5+2) = 1/7 = 0.1428 < 0.3 -> True (deprecate)
    assert should_deprecate(0, 5) is True

    # (1, 4) -> 1+4=5, (1+1)/(5+2) = 2/7 = 0.2857 < 0.3 -> True (deprecate)
    assert should_deprecate(1, 4) is True

    # (3, 2) -> 3+2=5, (3+1)/(5+2) = 4/7 = 0.5714 >= 0.3 -> False (do not deprecate)
    assert should_deprecate(3, 2) is False

    # (0, 4) -> 0+4=4 < 5 -> False (insufficient trials to deprecate)
    assert should_deprecate(0, 4) is False


@pytest.mark.asyncio
async def test_g6_decay() -> None:
    """Verify G6: decay archives exactly ep-r2 and archived episodes are omitted from recall."""
    await seed_tenant("acme", reset=True)
    db: TenantDB = await get_tenant_db("acme")

    # 1. Run decay at frozen time
    archived_ids: list[str] = await decay("acme", now_ts=FROZEN_NOW)
    assert archived_ids == ["ep-r2"], f"Expected ['ep-r2'] to be decayed, got {archived_ids}"

    # 2. Verify in graph that ep-r2 is ARCHIVED and all others remain ACTIVE
    r2_status: list[Any] = await db.run_ro(
        "MATCH (e:Episode {id: 'ep-r2'}) RETURN e.status",
    )
    assert r2_status[0][0] == "ARCHIVED"

    other_statuses: list[Any] = await db.run_ro(
        "MATCH (e:Episode) WHERE e.id <> 'ep-r2' RETURN DISTINCT e.status",
    )
    assert len(other_statuses) == 1 and other_statuses[0][0] == "ACTIVE"

    # 3. Verify archived episode never appears in recall for Rahul
    res: dict[str, Any] = await recall(
        tenant_id="acme",
        user_id="user-rahul",
        query="How do I get invoice PDFs formatted?",
        k=5,
        now_ts=FROZEN_NOW,
    )
    returned_ep_ids = [ep["id"] for ep in res["episodes"]]
    assert "ep-r2" not in returned_ep_ids, f"Archived episode ep-r2 appeared in recall: {returned_ep_ids}"


@pytest.mark.asyncio
async def test_g10_procedure_promotion() -> None:
    """Verify G10: learned procedure is promoted after reaching threshold and subsequent calls return empty."""
    await seed_tenant("acme", reset=True)
    db: TenantDB = await get_tenant_db("acme")

    proc_id = "proc-vpn-token-reset"

    # 1. Initially CANDIDATE with 1 success from 1 user (user-priya via sess-p2)
    init_promoted: list[str] = await promote_procedures("acme")
    assert init_promoted == [], f"Expected no promotions initially, got {init_promoted}"

    # Verify procedure status is still CANDIDATE
    status_res1: list[Any] = await db.run_ro(
        "MATCH (p:Procedure {id: $pid}) RETURN p.status",
        {"pid": proc_id},
    )
    assert status_res1[0][0] == "CANDIDATE"

    # Verify CANDIDATE is excluded from recall but included by find_procedures(include_candidates=True)
    recall_res = await recall(
        tenant_id="acme",
        user_id="user-rahul",
        query="vpn login failing token expired reset",
        k=3,
        now_ts=FROZEN_NOW,
    )
    assert proc_id not in [p["id"] for p in recall_res["procedures"]]

    procs_with_cand = await find_procedures(
        "acme",
        "vpn login failing token expired reset",
        include_candidates=True,
    )
    assert proc_id in [p["id"] for p in procs_with_cand]

    # 2. Record success in a Rahul session (sess-r1)
    await record_outcome("acme", "sess-r1", proc_id, "success")

    # 3. Now 2 successes from 2 distinct users; promote_procedures returns [proc-vpn-token-reset]
    promoted = await promote_procedures("acme")
    assert promoted == [proc_id], f"Expected [{proc_id}], got {promoted}"

    # Status in database is now ACTIVE
    status_res2: list[Any] = await db.run_ro(
        "MATCH (p:Procedure {id: $pid}) RETURN p.status",
        {"pid": proc_id},
    )
    assert status_res2[0][0] == "ACTIVE"

    # 4. Calling promote_procedures a second time returns []
    second_promoted = await promote_procedures("acme")
    assert second_promoted == [], f"Expected empty list on second call, got {second_promoted}"
