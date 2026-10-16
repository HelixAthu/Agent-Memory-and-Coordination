"""Idempotent seed script provisioning schema, nodes, and relationships for acme and globex."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory_core.db import TenantDB, get_tenant_db
from memory_core.embedder import get_embedder
from memory_core.schema import ensure_tenant
from memory_core.tenancy import validate_tenant_id

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed")

DATA_DIR = Path(__file__).resolve().parent / "data"


async def seed_tenant(tenant_id: str, reset: bool = False) -> dict[str, Any]:
    """Provision schema and seed tenant graph with canonical nodes and edges.

    Returns dictionary containing node and relationship counts.
    """
    valid_id = validate_tenant_id(tenant_id)
    db: TenantDB = await get_tenant_db(valid_id)
    embedder = get_embedder()

    if reset:
        logger.info("[%s] Resetting tenant graph...", valid_id)
        await db.delete_graph()

    await ensure_tenant(valid_id, db=db)

    json_file = DATA_DIR / f"{valid_id}.json"
    if not json_file.exists():
        raise FileNotFoundError(f"Seed data file not found: {json_file}")

    with open(json_file, "r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    # 1. Agents
    for a in data.get("agents", []):
        await db.run_rw(
            "MERGE (a:Agent {id: $id}) "
            "SET a.name = $name, a.role = $role, a.status = $status",
            a,
        )

    # 2. Users
    for u in data.get("users", []):
        await db.run_rw(
            "MERGE (u:User {id: $id}) SET u.name = $name",
            u,
        )

    # 3. Entities
    for e in data.get("entities", []):
        await db.run_rw(
            "MERGE (x:Entity {id: $id}) "
            "SET x.name = $name, x.type = $type, x.keywords = $keywords",
            e,
        )

    # 4. EXPERT_IN relationships
    for exp in data.get("expert_in", []):
        await db.run_rw(
            "MATCH (a:Agent {id: $agent_id}), (t:Entity {id: $topic_id}) "
            "MERGE (a)-[:EXPERT_IN]->(t)",
            exp,
        )

    # 5. Sessions & HAD_SESSION
    for s in data.get("sessions", []):
        await db.run_rw(
            "MATCH (u:User {id: $user_id}) "
            "MERGE (s:Session {id: $id}) "
            "SET s.user_id = $user_id, s.status = $status, s.started_at = $started_at, "
            "s.ended_at = $ended_at, s.outcome = $outcome, s.current_agent = $current_agent, "
            "s.msg_count = $msg_count "
            "MERGE (u)-[:HAD_SESSION]->(s)",
            s,
        )

    # 6. Messages & HAS_MESSAGE & NEXT chains
    for m in data.get("messages", []):
        await db.run_rw(
            "MATCH (s:Session {id: $session_id}) "
            "MERGE (msg:Message {id: $id}) "
            "SET msg.session_id = $session_id, msg.seq = $seq, msg.role = $role, "
            "msg.agent_id = $agent_id, msg.text = $text, msg.ts = $ts "
            "MERGE (s)-[:HAS_MESSAGE]->(msg)",
            m,
        )

    # Connect NEXT chains per session
    for s in data.get("sessions", []):
        sid = s["id"]
        res = await db.run_ro(
            "MATCH (s:Session {id: $sid})-[:HAS_MESSAGE]->(m:Message) "
            "RETURN m.id AS id, m.seq AS seq ORDER BY m.seq ASC",
            {"sid": sid},
        )
        for i in range(len(res) - 1):
            await db.run_rw(
                "MATCH (m1:Message {id: $id1}), (m2:Message {id: $id2}) "
                "MERGE (m1)-[:NEXT]->(m2)",
                {"id1": res[i][0], "id2": res[i + 1][0]},
            )

    # 7. Episodes with embeddings, SUMMARIZED_AS, ABOUT, MENTIONS, INVOLVED
    for ep in data.get("episodes", []):
        emb = embedder.embed(ep["summary"])
        await db.run_rw(
            "MATCH (s:Session {id: $session_id}), (u:User {id: s.user_id}) "
            "MERGE (e:Episode {id: $id}) "
            "SET e.summary = $summary, e.outcome = $outcome, e.importance = $importance, "
            "e.ts = $ts, e.status = $status, e.embedding = vecf32($emb) "
            "MERGE (s)-[:SUMMARIZED_AS]->(e) "
            "MERGE (e)-[:ABOUT]->(u)",
            {
                "id": ep["id"],
                "session_id": ep["session_id"],
                "summary": ep["summary"],
                "outcome": ep["outcome"],
                "importance": ep["importance"],
                "ts": ep["ts"],
                "status": ep["status"],
                "emb": emb,
            },
        )
        for mention_id in ep.get("mentions", []):
            await db.run_rw(
                "MATCH (e:Episode {id: $eid}), (x:Entity {id: $xid}) "
                "MERGE (e)-[:MENTIONS]->(x)",
                {"eid": ep["id"], "xid": mention_id},
            )
        for involved_id in ep.get("involved", []):
            await db.run_rw(
                "MATCH (e:Episode {id: $eid}), (a:Agent {id: $aid}) "
                "MERGE (e)-[:INVOLVED]->(a)",
                {"eid": ep["id"], "aid": involved_id},
            )

    # 8. Facts with embeddings, HAS_FACT, DERIVED_FROM, SUPERSEDES
    for f_item in data.get("facts", []):
        emb_text = f"{f_item['predicate']} {f_item['object']}"
        emb = embedder.embed(emb_text)
        await db.run_rw(
            "MATCH (u:User {id: $user_id}) "
            "MERGE (f:Fact {id: $id}) "
            "SET f.predicate = $predicate, f.object = $object, f.confidence = $confidence, "
            "f.status = $status, f.valid_from = $valid_from, f.valid_to = $valid_to, "
            "f.last_confirmed = $valid_from, f.embedding = vecf32($emb) "
            "MERGE (u)-[:HAS_FACT]->(f)",
            {
                "id": f_item["id"],
                "user_id": f_item["user_id"],
                "predicate": f_item["predicate"],
                "object": f_item["object"],
                "confidence": f_item["confidence"],
                "status": f_item["status"],
                "valid_from": f_item["valid_from"],
                "valid_to": f_item["valid_to"],
                "emb": emb,
            },
        )
        if f_item.get("derived_from"):
            await db.run_rw(
                "MATCH (f:Fact {id: $fid}), (s:Session {id: $sid}) "
                "MERGE (f)-[:DERIVED_FROM]->(s)",
                {"fid": f_item["id"], "sid": f_item["derived_from"]},
            )

    for sup in data.get("supersedes", []):
        await db.run_rw(
            "MATCH (n:Fact {id: $new_id}), (o:Fact {id: $old_id}) "
            "MERGE (n)-[:SUPERSEDES]->(o)",
            sup,
        )

    # 9. Procedures with embeddings & APPLIED relationships
    for p_item in data.get("procedures", []):
        emb = embedder.embed(p_item["trigger"])
        await db.run_rw(
            "MERGE (p:Procedure {id: $id}) "
            "SET p.name = $name, p.trigger = $trigger, p.steps = $steps, "
            "p.status = $status, p.origin = $origin, p.embedding = vecf32($emb)",
            {
                "id": p_item["id"],
                "name": p_item["name"],
                "trigger": p_item["trigger"],
                "steps": p_item["steps"],
                "status": p_item["status"],
                "origin": p_item["origin"],
                "emb": emb,
            },
        )

    for app in data.get("applied", []):
        await db.run_rw(
            "MATCH (s:Session {id: $session_id}), (p:Procedure {id: $procedure_id}) "
            "MERGE (s)-[r:APPLIED]->(p) "
            "SET r.outcome = $outcome, r.ts = $ts",
            app,
        )

    # 10. Tasks & FOR_USER relationships
    for t_item in data.get("tasks", []):
        await db.run_rw(
            "MERGE (t:Task {id: $id}) "
            "SET t.title = $title, t.status = $status, t.priority = $priority, "
            "t.claimed_by = $claimed_by, t.version = $version, t.created_at = $created_at",
            {
                "id": t_item["id"],
                "title": t_item["title"],
                "status": t_item["status"],
                "priority": t_item["priority"],
                "claimed_by": t_item["claimed_by"],
                "version": t_item["version"],
                "created_at": t_item["created_at"],
            },
        )
        if t_item.get("user_id"):
            await db.run_rw(
                "MATCH (t:Task {id: $tid}), (u:User {id: $uid}) "
                "MERGE (t)-[:FOR_USER]->(u)",
                {"tid": t_item["id"], "uid": t_item["user_id"]},
            )

    # Fetch verification counts
    total_nodes_res = await db.run_ro("MATCH (n) RETURN count(n) AS cnt")
    total_edges_res = await db.run_ro("MATCH ()-[r]->() RETURN count(r) AS cnt")
    node_count = total_nodes_res[0][0] if total_nodes_res else 0
    edge_count = total_edges_res[0][0] if total_edges_res else 0

    logger.info("[%s] Seeded successfully: %d nodes, %d edges", valid_id, node_count, edge_count)
    return {"nodes": node_count, "edges": edge_count}


async def seed_all(reset: bool = False) -> None:
    """Seed all configured tenants."""
    for tid in ["acme", "globex"]:
        await seed_tenant(tid, reset=reset)


def main() -> None:
    """CLI entrypoint parsing --reset flag and triggering seed_all."""
    parser = argparse.ArgumentParser(description="Seed FalkorDB graphs for Memory Fabric.")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate tenant graphs before seeding.")
    args = parser.parse_args()

    asyncio.run(seed_all(reset=args.reset))


if __name__ == "__main__":
    main()
