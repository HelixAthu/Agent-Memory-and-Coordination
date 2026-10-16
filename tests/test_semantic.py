"""Unit and concurrency tests for semantic memory facts, supersession, reinforcement (G4, G5)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from memory_core.db import TenantDB, get_tenant_db
from memory_core.errors import InvalidInputError
from memory_core.semantic import get_history, get_profile, remember_fact
from seed.seed import seed_tenant


@pytest.mark.asyncio
async def test_g4_fact_supersession() -> None:
    """Verify G4: supersession updates old facts to SUPERSEDED and creates new ACTIVE facts."""
    # Reset to pristine seed state
    await seed_tenant("acme", reset=True)
    db: TenantDB = await get_tenant_db("acme")

    # 1. Update city to Pune
    res_city: dict[str, Any] = await remember_fact(
        tenant_id="acme",
        user_id="user-priya",
        predicate="city",
        object_="Pune",
    )
    assert res_city["action"] == "superseded"
    assert res_city["old_fact_id"] == "fact-p-city"

    # 2. Update prefers_channel to chat
    res_channel: dict[str, Any] = await remember_fact(
        tenant_id="acme",
        user_id="user-priya",
        predicate="prefers_channel",
        object_="chat",
    )
    assert res_channel["action"] == "superseded"
    assert res_channel["old_fact_id"] == "fact-p-channel"

    # 3. Check active facts for Priya (exactly 3: plan=Pro, prefers_channel=chat, city=Pune)
    profile: list[dict[str, Any]] = await get_profile("acme", "user-priya")
    assert len(profile) == 3, f"Expected 3 active facts, got {len(profile)}: {profile}"
    profile_dict = {f["predicate"]: f["object"] for f in profile}
    assert profile_dict == {
        "city": "Pune",
        "plan": "Pro",
        "prefers_channel": "chat",
    }

    # 4. Check history for prefers_channel (3 entries: chat ACTIVE, email SUPERSEDED, phone SUPERSEDED)
    chan_hist: list[dict[str, Any]] = await get_history("acme", "user-priya", "prefers_channel")
    assert len(chan_hist) == 3
    assert chan_hist[0]["object"] == "chat" and chan_hist[0]["status"] == "ACTIVE"
    assert chan_hist[1]["object"] == "email" and chan_hist[1]["status"] == "SUPERSEDED"
    assert chan_hist[2]["object"] == "phone" and chan_hist[2]["status"] == "SUPERSEDED"

    # 5. Check history for city ([Pune ACTIVE, Mumbai SUPERSEDED])
    city_hist: list[dict[str, Any]] = await get_history("acme", "user-priya", "city")
    assert len(city_hist) == 2
    assert city_hist[0]["object"] == "Pune" and city_hist[0]["status"] == "ACTIVE"
    assert city_hist[1]["object"] == "Mumbai" and city_hist[1]["status"] == "SUPERSEDED"

    # 6. Verify SUPERSEDES edge in database
    edge_res: list[Any] = await db.run_ro(
        "MATCH (n:Fact {id: $nid})-[:SUPERSEDES]->(o:Fact {id: 'fact-p-city'}) RETURN count(n)",
        {"nid": res_city["fact_id"]},
    )
    assert edge_res[0][0] == 1


@pytest.mark.asyncio
async def test_g5_reinforcement() -> None:
    """Verify G5: identical active fact triggers reinforcement without creating new node."""
    await seed_tenant("acme", reset=True)
    db: TenantDB = await get_tenant_db("acme")

    # Initial fact count
    init_facts_res: list[Any] = await db.run_ro("MATCH (f:Fact) RETURN count(f)")
    init_count: int = init_facts_res[0][0]

    # Reinforce existing plan=Pro for user-priya
    res: dict[str, Any] = await remember_fact(
        tenant_id="acme",
        user_id="user-priya",
        predicate="plan",
        object_="Pro",
    )
    assert res["action"] == "reinforced"
    assert res["fact_id"] == "fact-p-plan"
    assert abs(res["confidence"] - 0.95) < 0.001

    # Fact count should remain unchanged
    after_facts_res: list[Any] = await db.run_ro("MATCH (f:Fact) RETURN count(f)")
    assert after_facts_res[0][0] == init_count == 6


@pytest.mark.asyncio
async def test_predicate_validation_and_concurrency() -> None:
    """Verify invalid predicate rejection and 10 concurrent fact updates leaving 1 active fact."""
    await seed_tenant("acme", reset=False)
    db: TenantDB = await get_tenant_db("acme")

    # 1. Unknown predicate is rejected with InvalidInputError
    with pytest.raises(InvalidInputError):
        await remember_fact(
            tenant_id="acme",
            user_id="user-priya",
            predicate="unknown_pred",
            object_="Test",
        )

    # 2. 10 concurrent fact updates with different objects
    cities: list[str] = [f"City{i}" for i in range(10)]
    coros = [
        remember_fact(
            tenant_id="acme",
            user_id="user-rahul",
            predicate="city",
            object_=c,
        )
        for c in cities
    ]
    await asyncio.gather(*coros, return_exceptions=True)

    # Assert exactly one ACTIVE city fact for user-rahul
    active_city_res: list[Any] = await db.run_ro(
        "MATCH (u:User {id: 'user-rahul'})-[:HAS_FACT]->(f:Fact {predicate: 'city', status: 'ACTIVE'}) "
        "RETURN count(f)",
    )
    assert active_city_res[0][0] == 1, (
        f"Expected exactly 1 active city fact for user-rahul, got {active_city_res[0][0]}"
    )
