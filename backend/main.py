"""FastAPI application exposing REST and SSE endpoints for Memory Fabric."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.auth import verify_admin_key, verify_tenant_api_key
from memory_core.config import settings
from memory_core.db import get_tenant_db
from seed.seed import seed_tenant

app = FastAPI(
    title="Memory Fabric API",
    version="0.3.0",
    description="Multi-agent memory, coordination and graph persistence service.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _clean_props(props: dict[str, Any] | None) -> dict[str, Any]:
    """Strip embedding or other sensitive binary vectors from properties."""
    if not props:
        return {}
    return {k: v for k, v in props.items() if k != "embedding"}


@app.get("/health")
async def health() -> dict[str, Any]:
    """Public healthcheck endpoint listing permitted tenants."""
    return {
        "ok": True,
        "tenants": settings.get_allowed_tenants(),
    }


@app.get("/t/{tenant}/users")
async def list_users(
    tenant: str = Depends(verify_tenant_api_key),
) -> list[dict[str, Any]]:
    """List all registered users for the tenant."""
    db = await get_tenant_db(tenant)
    rows = await db.run_ro("MATCH (u:User) RETURN u.id, u.name, u.role ORDER BY u.id")
    return [
        {"id": str(r[0]), "name": str(r[1]), "role": str(r[2]) if len(r) > 2 and r[2] else "customer"}
        for r in rows
    ]


@app.get("/t/{tenant}/users/{uid}/graph")
async def get_user_graph(
    uid: str,
    tenant: str = Depends(verify_tenant_api_key),
) -> dict[str, Any]:
    """Retrieve bounded memory subgraph for UI visualization (capped at 200 nodes)."""
    db = await get_tenant_db(tenant)

    # 1. Verify user exists
    user_rows = await db.run_ro(
        "MATCH (u:User {id: $uid}) RETURN u.id, properties(u)",
        {"uid": uid},
    )
    if not user_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{uid}' not found in tenant '{tenant}'",
        )

    nodes: list[dict[str, Any]] = [
        {"id": uid, "label": "User", "props": _clean_props(user_rows[0][1])}
    ]
    node_ids: set[str] = {uid}

    # 2. Gather user sessions, facts, episodes
    sess_rows = await db.run_ro(
        "MATCH (u:User {id: $uid})-[:HAD_SESSION]->(s:Session) RETURN s.id, properties(s)",
        {"uid": uid},
    )
    for r in sess_rows:
        sid, props = str(r[0]), _clean_props(r[1])
        if sid not in node_ids:
            nodes.append({"id": sid, "label": "Session", "props": props})
            node_ids.add(sid)

    fact_rows = await db.run_ro(
        "MATCH (u:User {id: $uid})-[:HAS_FACT]->(f:Fact) RETURN f.id, properties(f)",
        {"uid": uid},
    )
    for r in fact_rows:
        fid, props = str(r[0]), _clean_props(r[1])
        if fid not in node_ids:
            nodes.append({"id": fid, "label": "Fact", "props": props})
            node_ids.add(fid)

    ep_rows = await db.run_ro(
        "MATCH (e:Episode)-[:ABOUT]->(u:User {id: $uid}) RETURN e.id, properties(e)",
        {"uid": uid},
    )
    for r in ep_rows:
        eid, props = str(r[0]), _clean_props(r[1])
        if eid not in node_ids:
            nodes.append({"id": eid, "label": "Episode", "props": props})
            node_ids.add(eid)

    # 3. Gather agents and procedures
    agent_rows = await db.run_ro("MATCH (a:Agent) RETURN a.id, properties(a)")
    for r in agent_rows:
        aid, props = str(r[0]), _clean_props(r[1])
        if aid not in node_ids:
            nodes.append({"id": aid, "label": "Agent", "props": props})
            node_ids.add(aid)

    proc_rows = await db.run_ro("MATCH (p:Procedure) RETURN p.id, properties(p)")
    for r in proc_rows:
        pid, props = str(r[0]), _clean_props(r[1])
        if pid not in node_ids:
            nodes.append({"id": pid, "label": "Procedure", "props": props})
            node_ids.add(pid)

    # Cap nodes at 200
    nodes = nodes[:200]
    final_ids = [n["id"] for n in nodes]

    # 4. Fetch edges between these nodes
    edge_rows = await db.run_ro(
        "MATCH (a)-[r]->(b) WHERE a.id IN $ids AND b.id IN $ids "
        "RETURN a.id, type(r), b.id, properties(r)",
        {"ids": final_ids},
    )

    edges: list[dict[str, Any]] = [
        {
            "id": f"{r[0]}-{r[1]}-{r[2]}",
            "source": str(r[0]),
            "target": str(r[2]),
            "type": str(r[1]),
            "props": _clean_props(r[3]),
        }
        for r in edge_rows
    ]

    return {"nodes": nodes, "edges": edges}


@app.get("/t/{tenant}/users/{uid}/facts")
async def get_user_facts(
    uid: str,
    include_history: bool = Query(default=False),
    tenant: str = Depends(verify_tenant_api_key),
) -> list[dict[str, Any]]:
    """Retrieve semantic memory facts for a user."""
    db = await get_tenant_db(tenant)
    if include_history:
        cypher = (
            "MATCH (u:User {id: $uid})-[:HAS_FACT]->(f:Fact) "
            "RETURN f.id, f.predicate, f.object, f.status, f.confidence, f.valid_from, f.valid_to "
            "ORDER BY f.predicate ASC, f.valid_from DESC"
        )
    else:
        cypher = (
            "MATCH (u:User {id: $uid})-[:HAS_FACT]->(f:Fact {status: 'ACTIVE'}) "
            "RETURN f.id, f.predicate, f.object, f.status, f.confidence, f.valid_from, f.valid_to "
            "ORDER BY f.predicate ASC"
        )

    rows = await db.run_ro(cypher, {"uid": uid})
    return [
        {
            "id": str(r[0]),
            "predicate": str(r[1]),
            "object": str(r[2]),
            "status": str(r[3]),
            "confidence": float(r[4]) if r[4] is not None else 1.0,
            "valid_from": int(r[5]) if r[5] is not None else 0,
            "valid_to": int(r[6]) if r[6] is not None else None,
        }
        for r in rows
    ]


@app.get("/t/{tenant}/users/{uid}/episodes")
async def get_user_episodes(
    uid: str,
    tenant: str = Depends(verify_tenant_api_key),
) -> list[dict[str, Any]]:
    """Retrieve episodic memories for a user (ACTIVE and ARCHIVED)."""
    db = await get_tenant_db(tenant)
    rows = await db.run_ro(
        "MATCH (e:Episode)-[:ABOUT]->(u:User {id: $uid}) "
        "RETURN e.id, e.summary, e.importance, e.status, e.created_at "
        "ORDER BY e.created_at DESC",
        {"uid": uid},
    )
    return [
        {
            "id": str(r[0]),
            "summary": str(r[1]),
            "importance": float(r[2]) if r[2] is not None else 0.5,
            "status": str(r[3]),
            "created_at": int(r[4]) if r[4] is not None else 0,
        }
        for r in rows
    ]


@app.get("/t/{tenant}/procedures")
async def list_procedures(
    tenant: str = Depends(verify_tenant_api_key),
) -> list[dict[str, Any]]:
    """Retrieve procedural memory routines with success metrics and status."""
    db = await get_tenant_db(tenant)
    rows = await db.run_ro(
        "MATCH (p:Procedure) "
        "RETURN p.id, p.name, p.situation, p.steps, p.successes, p.failures, p.status "
        "ORDER BY p.id ASC",
    )
    return [
        {
            "id": str(r[0]),
            "name": str(r[1]),
            "situation": str(r[2]),
            "steps": list(r[3]) if isinstance(r[3], (list, tuple)) else str(r[3]).split(", "),
            "successes": int(r[4]) if r[4] is not None else 0,
            "failures": int(r[5]) if r[5] is not None else 0,
            "status": str(r[6]),
        }
        for r in rows
    ]


@app.get("/t/{tenant}/tasks")
async def list_tasks(
    tenant: str = Depends(verify_tenant_api_key),
) -> list[dict[str, Any]]:
    """Retrieve coordination task board ordered by priority."""
    db = await get_tenant_db(tenant)
    rows = await db.run_ro(
        "MATCH (t:Task) "
        "RETURN t.id, t.title, t.status, t.priority, t.claimed_by, t.version "
        "ORDER BY t.priority DESC, t.id ASC",
    )
    return [
        {
            "id": str(r[0]),
            "title": str(r[1]),
            "status": str(r[2]),
            "priority": int(r[3]) if r[3] is not None else 0,
            "claimed_by": str(r[4]) if r[4] else None,
            "version": int(r[5]) if r[5] is not None else 1,
        }
        for r in rows
    ]


@app.get("/t/{tenant}/handoffs")
async def list_handoffs(
    tenant: str = Depends(verify_tenant_api_key),
) -> list[dict[str, Any]]:
    """Retrieve multi-agent handoff log ordered newest first."""
    db = await get_tenant_db(tenant)
    rows = await db.run_ro(
        "MATCH (h:Handoff) "
        "RETURN h.id, h.status, h.reason, h.from_agent, h.to_agent, h.session_id, h.created_at "
        "ORDER BY h.created_at DESC",
    )
    return [
        {
            "id": str(r[0]),
            "status": str(r[1]),
            "reason": str(r[2]),
            "from_agent": str(r[3]),
            "to_agent": str(r[4]),
            "session_id": str(r[5]),
            "created_at": int(r[6]) if r[6] is not None else 0,
        }
        for r in rows
    ]


@app.post("/admin/reset")
async def admin_reset(
    _: None = Depends(verify_admin_key),
) -> dict[str, Any]:
    """Re-seed all permitted tenants to initial clean golden state."""
    tenants = settings.get_allowed_tenants()
    for tid in tenants:
        await seed_tenant(tid, reset=True)
    return {"ok": True, "reset_tenants": tenants}


@app.get("/replays/{scenario}")
async def get_replay(scenario: str) -> FileResponse:
    """Serve recorded headless scenario execution replay."""
    path = Path("replays") / f"{scenario}.jsonl"
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay for scenario '{scenario}' not found",
        )
    return FileResponse(path, media_type="application/x-ndjson")
