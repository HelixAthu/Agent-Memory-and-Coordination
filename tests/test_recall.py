"""Unit and golden recall tests asserting G2, G3, isolation, and procedure finding."""

from __future__ import annotations

from typing import Any

import pytest

from memory_core.recall import find_procedures, recall
from seed.seed import seed_tenant

Q1: str = "Hello, my card shows a duplicate charge again on invoice INV-1042."
FROZEN_NOW: int = 1792108800  # 2026-10-16T00:00:00Z


@pytest.mark.asyncio
async def test_g2_recall_priya() -> None:
    """Verify G2: hybrid recall for user-priya produces exact ranking, boosts, facts, and procedures."""
    await seed_tenant("acme", reset=True)

    res: dict[str, Any] = await recall(
        tenant_id="acme",
        user_id="user-priya",
        query=Q1,
        k=3,
        now_ts=FROZEN_NOW,
    )

    episodes = res["episodes"]
    facts = res["facts"]
    procedures = res["procedures"]

    # 1. Episodes ranking and IDs
    ep_ids = [ep["id"] for ep in episodes]
    assert ep_ids == ["ep-p1", "ep-p3", "ep-p2"], f"Expected [ep-p1, ep-p3, ep-p2], got {ep_ids}"

    # 2. Components and boosts
    p1 = episodes[0]
    p3 = episodes[1]
    p2 = episodes[2]

    assert p1["components"]["boost"] == 0, f"Expected ep-p1 boost 0, got {p1['components']['boost']}"
    assert p3["components"]["boost"] == 1, f"Expected ep-p3 boost 1, got {p3['components']['boost']}"
    assert p2["components"]["boost"] == 0, f"Expected ep-p2 boost 0, got {p2['components']['boost']}"

    # 3. Approximate scores (tolerance 0.05)
    assert abs(p1["score"] - 0.485) <= 0.05, f"ep-p1 score {p1['score']} outside tolerance of 0.485"
    assert abs(p3["score"] - 0.405) <= 0.05, f"ep-p3 score {p3['score']} outside tolerance of 0.405"
    assert abs(p2["score"] - 0.087) <= 0.05, f"ep-p2 score {p2['score']} outside tolerance of 0.087"

    # 4. Facts: exactly the ACTIVE facts for Priya
    fact_ids = {f["id"] for f in facts}
    assert fact_ids == {"fact-p-plan", "fact-p-channel", "fact-p-city"}, f"Facts mismatch: {fact_ids}"

    # 5. Procedures: proc-dup-charge-refund (CANDIDATE procedure excluded from recall)
    proc_ids = [p["id"] for p in procedures]
    assert proc_ids == ["proc-dup-charge-refund"], f"Procedures mismatch: {proc_ids}"

    # 6. Negative assertions: no cross-user or cross-tenant IDs
    all_returned_ids = (
        [ep["id"] for ep in episodes]
        + [f["id"] for f in facts]
        + [p["id"] for p in procedures]
    )
    for rid in all_returned_ids:
        assert not rid.startswith("ep-r"), f"Cross-user episode leaked: {rid}"
        assert not rid.startswith("fact-r"), f"Cross-user fact leaked: {rid}"
        assert not rid.startswith("ep-d"), f"Cross-tenant episode leaked: {rid}"
        assert not rid.startswith("fact-d"), f"Cross-tenant fact leaked: {rid}"


@pytest.mark.asyncio
async def test_g3_recall_rahul() -> None:
    """Verify G3: recall for user-rahul isolates rahul's data without leaking priya's."""
    await seed_tenant("acme", reset=False)

    res: dict[str, Any] = await recall(
        tenant_id="acme",
        user_id="user-rahul",
        query=Q1,
        k=3,
        now_ts=FROZEN_NOW,
    )

    ep_ids = [ep["id"] for ep in res["episodes"]]
    # Episodes only from rahul
    for eid in ep_ids:
        assert eid in {"ep-r1", "ep-r2"}, f"Unexpected episode for rahul: {eid}"
        assert not eid.startswith("ep-p"), f"Leaked Priya's episode to Rahul: {eid}"

    fact_ids = {f["id"] for f in res["facts"]}
    assert fact_ids == {"fact-r-plan", "fact-r-channel"}, f"Rahul facts mismatch: {fact_ids}"


@pytest.mark.asyncio
async def test_cross_tenant_isolation() -> None:
    """Verify that recalling under globex only returns globex nodes and never acme nodes."""
    await seed_tenant("globex", reset=False)

    res: dict[str, Any] = await recall(
        tenant_id="globex",
        user_id="user-dana",
        query=Q1,
        k=3,
        now_ts=FROZEN_NOW,
    )

    ep_ids = [ep["id"] for ep in res["episodes"]]
    assert ep_ids == ["ep-d1"], f"Expected ['ep-d1'] for Dana, got {ep_ids}"
    fact_ids = [f["id"] for f in res["facts"]]
    assert fact_ids == ["fact-d-channel"], f"Expected ['fact-d-channel'], got {fact_ids}"


@pytest.mark.asyncio
async def test_find_procedures_candidate_flag() -> None:
    """Verify find_procedures includes CANDIDATE procedures when requested with boost for ACTIVE."""
    await seed_tenant("acme", reset=False)

    situation = "vpn login failing token expired reset"
    # 1. Without candidates: only ACTIVE procedures
    active_procs = await find_procedures("acme", situation, include_candidates=False)
    for p in active_procs:
        assert p["status"] == "ACTIVE"

    # 2. With candidates: proc-vpn-token-reset (CANDIDATE) is returned
    all_procs = await find_procedures("acme", situation, include_candidates=True)
    p_ids = [p["id"] for p in all_procs]
    assert "proc-vpn-token-reset" in p_ids
