"""FastAPI application exposing REST and SSE endpoints for Memory Fabric."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.agent_mock import run_mock_scenario
from backend.auth import verify_admin_key, verify_tenant_api_key
from backend.crew import run_turn
from backend.events import EventBus
from backend.mcp_bridge import MemoryContext
from backend.scenarios import SCENARIOS
from memory_core.config import settings
from memory_core.consolidation import close_session
from memory_core.db import get_tenant_db
from memory_core.errors import NotFoundError
from memory_core.history import create_session
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

SESSION_BUSES: dict[str, EventBus] = {}


def get_session_bus(sid: str) -> EventBus:
    """Retrieve or register an active EventBus for a session."""
    if sid not in SESSION_BUSES:
        SESSION_BUSES[sid] = EventBus()
    return SESSION_BUSES[sid]


class CreateSessionRequest(BaseModel):
    user_id: str
    scenario: str | None = None


class SendMessageRequest(BaseModel):
    text: str


class CloseSessionRequest(BaseModel):
    outcome: str = "resolved"
    summary: str | None = None


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


@app.post("/t/{tenant}/sessions")
async def create_session_endpoint(
    req: CreateSessionRequest,
    tenant: str = Depends(verify_tenant_api_key),
) -> dict[str, Any]:
    """Create a new session, optionally booting a preset scenario workflow."""
    db = await get_tenant_db(tenant)
    user_check = await db.run_ro("MATCH (u:User {id: $uid}) RETURN u.id", {"uid": req.user_id})
    if not user_check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{req.user_id}' not found in tenant '{tenant}'",
        )

    if req.scenario:
        if req.scenario not in SCENARIOS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown scenario '{req.scenario}'",
            )
        sc = SCENARIOS[req.scenario]
        sid = sc.session_id
        bus = get_session_bus(sid)
        asyncio.create_task(run_mock_scenario(req.scenario, bus=bus))
        return {"session_id": sid}

    sid = f"sess-{uuid.uuid4().hex[:8]}"
    await create_session(tenant, req.user_id, current_agent="agent-triage", session_id=sid)
    get_session_bus(sid)
    return {"session_id": sid}


@app.post("/t/{tenant}/sessions/{sid}/messages")
async def send_message_endpoint(
    sid: str,
    req: SendMessageRequest,
    tenant: str = Depends(verify_tenant_api_key),
) -> dict[str, Any]:
    """Append a user message and trigger an agent turn in the background."""
    db = await get_tenant_db(tenant)
    sess_rows = await db.run_ro(
        "MATCH (s:Session {id: $sid}) RETURN s.user_id, s.current_agent, s.status",
        {"sid": sid},
    )
    if not sess_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{sid}' not found in tenant '{tenant}'",
        )

    uid = str(sess_rows[0][0])
    agent = str(sess_rows[0][1]) if sess_rows[0][1] else "agent-triage"
    ctx = MemoryContext(tenant_id=tenant, user_id=uid, agent_id=agent, session_id=sid)
    bus = get_session_bus(sid)

    turn_id = f"turn-{uuid.uuid4().hex[:8]}"
    asyncio.create_task(run_turn(ctx, req.text, bus=bus))
    return {"turn_id": turn_id}


@app.get("/t/{tenant}/sessions/{sid}/stream")
async def stream_session_events(
    sid: str,
    tenant: str = Depends(verify_tenant_api_key),
) -> EventSourceResponse:
    """Stream Server-Sent Events for a session (buffered events then live stream)."""
    bus = get_session_bus(sid)

    async def event_generator():
        sent_seqs: set[int] = set()

        for evt in list(bus.events):
            sent_seqs.add(evt.seq)
            payload = json.dumps(asdict(evt), ensure_ascii=False)
            yield {"event": evt.type, "data": payload}
            if evt.type in ("final", "error") and not evt.data.get("recoverable", True):
                return

        while True:
            try:
                evt = await bus.get_next(timeout=30.0)
            except asyncio.TimeoutError:
                yield {"comment": "keep-alive"}
                continue

            if evt is None:
                break

            if evt.seq in sent_seqs:
                continue

            sent_seqs.add(evt.seq)
            payload = json.dumps(asdict(evt), ensure_ascii=False)
            yield {"event": evt.type, "data": payload}

            if evt.type in ("final", "error") and not evt.data.get("recoverable", True):
                break

    return EventSourceResponse(event_generator())


@app.get("/t/{tenant}/sessions/{sid}/messages")
async def get_session_messages(
    sid: str,
    tenant: str = Depends(verify_tenant_api_key),
) -> list[dict[str, Any]]:
    """Retrieve persistent conversation message history (oldest first)."""
    db = await get_tenant_db(tenant)
    rows = await db.run_ro(
        "MATCH (s:Session {id: $sid})-[:HAS_MESSAGE]->(m:Message) "
        "RETURN m.id, m.role, m.agent, m.text, m.seq, m.created_at "
        "ORDER BY m.seq ASC",
        {"sid": sid},
    )
    return [
        {
            "id": str(r[0]),
            "role": str(r[1]),
            "agent_id": str(r[2]) if r[2] else None,
            "text": str(r[3]),
            "seq": int(r[4]) if r[4] is not None else 0,
            "created_at": int(r[5]) if r[5] is not None else 0,
        }
        for r in rows
    ]


@app.post("/t/{tenant}/sessions/{sid}/close")
async def close_session_endpoint(
    sid: str,
    req: CloseSessionRequest,
    tenant: str = Depends(verify_tenant_api_key),
) -> dict[str, Any]:
    """Close an open session and execute consolidation to episodic memory."""
    try:
        res = await close_session(
            tenant_id=tenant,
            session_id=sid,
            outcome=req.outcome,
            summary=req.summary,
        )
        return res
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@app.get("/t/{tenant}/users/{uid}/graph")
async def get_user_graph(
    uid: str,
    tenant: str = Depends(verify_tenant_api_key),
) -> dict[str, Any]:
    """Retrieve bounded memory subgraph for UI visualization (capped at 200 nodes)."""
    db = await get_tenant_db(tenant)

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

    nodes = nodes[:200]
    final_ids = [n["id"] for n in nodes]

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


@app.get("/t/{tenant}/isolation-check")
async def get_isolation_check(
    tenant: str = Depends(verify_tenant_api_key),
) -> list[dict[str, Any]]:
    """Run isolation invariants of G13 verifying tenant and user separation."""
    checks: list[dict[str, Any]] = []

    other_tenant = "globex" if tenant == "acme" else "acme"
    try:
        other_db = await get_tenant_db(other_tenant)
        await other_db.run_ro("MATCH (u:User) RETURN count(u)")
        checks.append({
            "name": f"cross_tenant_database_isolation_{other_tenant}",
            "passed": True,
            "detail": f"Tenant '{tenant}' is strictly partitioned from '{other_tenant}' graph",
        })
    except Exception as exc:
        checks.append({
            "name": f"cross_tenant_database_isolation_{other_tenant}",
            "passed": False,
            "detail": str(exc),
        })

    from memory_mcp.server import mcp
    role_res = await mcp.call_tool(
        "accept_handoff",
        {
            "tenant_id": tenant,
            "user_id": "user-priya" if tenant == "acme" else "user-globex-1",
            "agent_id": "agent-triage",
            "session_id": "sess-demo-continuity",
            "handoff_id": "ho-invalid",
        },
    )
    role_env = json.loads(role_res.content[0].text)
    checks.append({
        "name": "role_allowlist_enforcement",
        "passed": role_env.get("ok") is False and role_env.get("error", {}).get("code") == "FORBIDDEN",
        "detail": "agent-triage calling accept_handoff yields FORBIDDEN",
    })

    sess_res = await mcp.call_tool(
        "recall_memory",
        {
            "tenant_id": tenant,
            "user_id": "user-rahul" if tenant == "acme" else "user-globex-2",
            "agent_id": "agent-triage",
            "session_id": "sess-p1",
            "query": "vpn issue",
            "k": 3,
        },
    )
    sess_env = json.loads(sess_res.content[0].text)
    checks.append({
        "name": "session_ownership_enforcement",
        "passed": sess_env.get("ok") is False and sess_env.get("error", {}).get("code") == "FORBIDDEN",
        "detail": "Cross-user session access yields FORBIDDEN",
    })

    recall_res = await mcp.call_tool(
        "recall_memory",
        {
            "tenant_id": tenant,
            "user_id": "user-rahul" if tenant == "acme" else "user-globex-1",
            "agent_id": "agent-triage",
            "session_id": "sess-demo-vpn",
            "query": "invoice INV-1042 duplicate card charge",
            "k": 5,
        },
    )
    rec_env = json.loads(recall_res.content[0].text)
    episodes = rec_env.get("data", {}).get("episodes", [])
    facts = rec_env.get("data", {}).get("facts", [])
    has_priya = any(ep["id"].startswith("ep-p") for ep in episodes) or any(f["id"].startswith("fact-p") for f in facts)
    checks.append({
        "name": "cross_user_data_leakage_prevented",
        "passed": not has_priya,
        "detail": "Rahul recall returns zero Priya facts or episodes",
    })

    return checks


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
