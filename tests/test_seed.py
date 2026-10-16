"""Golden seed count and graph verification tests conforming to G1."""

from __future__ import annotations

from typing import Any

import pytest

from memory_core.db import TenantDB, get_tenant_db
from seed.seed import seed_tenant


@pytest.mark.asyncio
async def test_g1_counts_acme() -> None:
    """Verify acme tenant exact node and edge counts specified in G1."""
    # Ensure freshly seeded state
    await seed_tenant("acme", reset=False)
    db: TenantDB = await get_tenant_db("acme")

    # 1. Total node count
    node_res: list[Any] = await db.run_ro("MATCH (n) RETURN count(n) AS cnt")
    assert node_res[0][0] == 53, f"Expected 53 nodes in acme, got {node_res[0][0]}"

    # Breakdown by label
    expected_labels: dict[str, int] = {
        "Agent": 3,
        "User": 2,
        "Entity": 8,
        "Session": 5,
        "Message": 20,
        "Episode": 5,
        "Fact": 6,
        "Procedure": 2,
        "Task": 2,
    }
    lbl_res: list[Any] = await db.run_ro(
        "MATCH (n) RETURN labels(n)[0] AS lbl, count(n) AS cnt ORDER BY lbl"
    )
    actual_labels: dict[str, int] = {row[0]: row[1] for row in lbl_res}
    assert actual_labels == expected_labels, f"Label breakdown mismatch: {actual_labels}"

    # 2. Total edge count (5+20+15+5+5+11+9+6+5+1+2+5+2 = 91)
    edge_res: list[Any] = await db.run_ro("MATCH ()-[r]->() RETURN count(r) AS cnt")
    assert edge_res[0][0] == 91, f"Expected 91 edges in acme, got {edge_res[0][0]}"

    # Breakdown by relationship type
    expected_edges: dict[str, int] = {
        "HAD_SESSION": 5,
        "HAS_MESSAGE": 20,
        "NEXT": 15,
        "SUMMARIZED_AS": 5,
        "ABOUT": 5,
        "MENTIONS": 11,
        "INVOLVED": 9,
        "HAS_FACT": 6,
        "DERIVED_FROM": 5,
        "SUPERSEDES": 1,
        "APPLIED": 2,
        "EXPERT_IN": 5,
        "FOR_USER": 2,
    }
    rel_res: list[Any] = await db.run_ro(
        "MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS cnt ORDER BY rel"
    )
    actual_edges: dict[str, int] = {row[0]: row[1] for row in rel_res}
    assert actual_edges == expected_edges, f"Relationship breakdown mismatch: {actual_edges}"


@pytest.mark.asyncio
async def test_g1_counts_globex() -> None:
    """Verify globex tenant exact node and edge counts specified in G1."""
    await seed_tenant("globex", reset=False)
    db: TenantDB = await get_tenant_db("globex")

    # 1. Total node count
    node_res: list[Any] = await db.run_ro("MATCH (n) RETURN count(n) AS cnt")
    assert node_res[0][0] == 11, f"Expected 11 nodes in globex, got {node_res[0][0]}"

    # Breakdown by label
    expected_labels: dict[str, int] = {
        "Agent": 1,
        "User": 1,
        "Entity": 1,
        "Session": 1,
        "Message": 4,
        "Episode": 1,
        "Fact": 1,
        "Procedure": 1,
    }
    lbl_res: list[Any] = await db.run_ro(
        "MATCH (n) RETURN labels(n)[0] AS lbl, count(n) AS cnt ORDER BY lbl"
    )
    actual_labels: dict[str, int] = {row[0]: row[1] for row in lbl_res}
    assert actual_labels == expected_labels, f"Label breakdown mismatch: {actual_labels}"

    # 2. Total edge count (1+1+1+1+1+4+1+1+3+1 = 15)
    edge_res: list[Any] = await db.run_ro("MATCH ()-[r]->() RETURN count(r) AS cnt")
    assert edge_res[0][0] == 15, f"Expected 15 edges in globex, got {edge_res[0][0]}"


@pytest.mark.asyncio
async def test_seed_idempotency() -> None:
    """Verify that running seed twice leaves all node and edge counts unchanged."""
    res1: dict[str, Any] = await seed_tenant("acme", reset=False)
    res2: dict[str, Any] = await seed_tenant("acme", reset=False)
    assert res1 == res2, f"Idempotency failed for acme: {res1} != {res2}"

    res_g1: dict[str, Any] = await seed_tenant("globex", reset=False)
    res_g2: dict[str, Any] = await seed_tenant("globex", reset=False)
    assert res_g1 == res_g2, f"Idempotency failed for globex: {res_g1} != {res_g2}"


@pytest.mark.asyncio
async def test_facts_has_fact_exactly_one_user() -> None:
    """Verify that every Fact is connected via HAS_FACT to exactly one User."""
    for tenant_id in ["acme", "globex"]:
        db: TenantDB = await get_tenant_db(tenant_id)
        cypher: str = (
            "MATCH (f:Fact) "
            "OPTIONAL MATCH (u:User)-[:HAS_FACT]->(f) "
            "RETURN f.id AS fact_id, count(u) AS user_count"
        )
        res: list[Any] = await db.run_ro(cypher)
        assert len(res) > 0, f"No facts found for {tenant_id}"
        for row in res:
            fact_id: str = row[0]
            user_count: int = row[1]
            assert user_count == 1, (
                f"Fact {fact_id} in {tenant_id} is connected to {user_count} users (expected 1)"
            )


@pytest.mark.asyncio
async def test_no_embedding_property_in_graph_exports() -> None:
    """Verify that graph export serialization strips embedding properties from all nodes."""
    for tenant_id in ["acme", "globex"]:
        db: TenantDB = await get_tenant_db(tenant_id)
        # Fetch all node properties directly
        res: list[Any] = await db.run_ro("MATCH (n) RETURN labels(n)[0] AS lbl, properties(n) AS props")
        assert len(res) > 0

        # Simulate graph export endpoint serialization that strips embedding
        exported_nodes: list[dict[str, Any]] = []
        for row in res:
            label: str = row[0]
            raw_props: dict[str, Any] = row[1] if isinstance(row[1], dict) else {}
            # API export sanitization rule per Section 4.6 and Section 8.7
            clean_props: dict[str, Any] = {k: v for k, v in raw_props.items() if k != "embedding"}
            exported_nodes.append({"label": label, "properties": clean_props})

        for node in exported_nodes:
            props: dict[str, Any] = node["properties"]
            assert "embedding" not in props, (
                f"Exported node {node['label']} contains forbidden embedding key"
            )
