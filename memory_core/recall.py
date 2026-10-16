"""Hybrid vector and graph recall with multidimensional scoring and procedure retrieval."""

from __future__ import annotations

from typing import Any

from memory_core.clock import now as get_now
from memory_core.db import TenantDB, get_tenant_db
from memory_core.embedder import cosine, get_embedder
from memory_core.queries import (
    Q_EP_ENTITIES,
    Q_EP_RELATED,
    Q_EP_VEC,
    Q_FACTS_ACTIVE,
    Q_PROC_STATS,
    Q_PROC_VEC,
)


async def recall(
    tenant_id: str,
    user_id: str,
    query: str,
    k: int = 3,
    now_ts: int | None = None,
) -> dict[str, Any]:
    """Retrieve episodes, semantic facts, and procedures relevant to user query using hybrid recall."""
    db: TenantDB = await get_tenant_db(tenant_id)
    embedder = get_embedder()
    current_time: int = now_ts if now_ts is not None else get_now()
    qv: list[float] = embedder.embed(query)

    # 1. Episode candidate generation via vector index
    vec_k: int = max(k * 5, 10)
    vec_rows: list[Any] = await db.run_ro(
        Q_EP_VEC,
        {"uid": user_id, "k": vec_k, "qv": qv},
    )

    candidates: dict[str, dict[str, Any]] = {}
    for row in vec_rows:
        eid: str = str(row[0])
        summary: str = str(row[1])
        importance: float = float(row[2])
        ts: int = int(row[3])
        emb: list[float] = [float(x) for x in row[4]] if row[4] else []
        sim: float = cosine(qv, emb)
        candidates[eid] = {
            "id": eid,
            "summary": summary,
            "importance": importance,
            "ts": ts,
            "sim": sim,
            "via": [],
            "boost": 0,
        }

    # 2. Graph hop via shared entities of top-1 vector candidate
    if candidates:
        top1_id: str = max(candidates.keys(), key=lambda eid: candidates[eid]["sim"])
        ent_rows: list[Any] = await db.run_ro(Q_EP_ENTITIES, {"eid": top1_id})
        top1_entities: set[str] = {str(r[0]) for r in ent_rows}

        if top1_entities:
            # Check existing candidates for shared entities with top1
            for cand_id, cand in candidates.items():
                if cand_id == top1_id:
                    continue
                cand_ent_res: list[Any] = await db.run_ro(Q_EP_ENTITIES, {"eid": cand_id})
                cand_entities: set[str] = {str(r[0]) for r in cand_ent_res}
                shared: set[str] = cand_entities & top1_entities
                if shared:
                    cand["boost"] = 1
                    cand["via"] = sorted(shared)

            # Discover additional candidates connected via shared entities
            exclude_ids: list[str] = list(candidates.keys())
            related_rows: list[Any] = await db.run_ro(
                Q_EP_RELATED,
                {
                    "uid": user_id,
                    "entities": sorted(top1_entities),
                    "exclude": exclude_ids,
                },
            )
            for row in related_rows:
                rel_id: str = str(row[0])
                rel_summary: str = str(row[1])
                rel_importance: float = float(row[2])
                rel_ts: int = int(row[3])
                rel_emb: list[float] = [float(x) for x in row[4]] if row[4] else []
                rel_sim: float = cosine(qv, rel_emb)
                via: list[str] = sorted(str(x) for x in row[5]) if row[5] else []
                candidates[rel_id] = {
                    "id": rel_id,
                    "summary": rel_summary,
                    "importance": rel_importance,
                    "ts": rel_ts,
                    "sim": rel_sim,
                    "via": via,
                    "boost": 1,
                }

    # 3. Score and rank episode candidates
    scored_episodes: list[dict[str, Any]] = []
    for cand in candidates.values():
        ts = cand["ts"]
        age_days: float = max(0.0, float(current_time - ts) / 86400.0)
        recency: float = 0.5 ** (age_days / 14.0)
        sim = cand["sim"]
        importance = cand["importance"]
        boost = cand["boost"]

        score: float = 0.65 * sim + 0.10 * recency + 0.15 * importance + 0.10 * boost
        scored_episodes.append(
            {
                "id": cand["id"],
                "summary": cand["summary"],
                "score": round(score, 4),
                "components": {
                    "sim": round(sim, 4),
                    "recency": round(recency, 4),
                    "importance": round(importance, 4),
                    "boost": boost,
                },
                "via": cand["via"],
                "ts": ts,
            }
        )

    # Sort descending by score, tie-break by ts descending
    scored_episodes.sort(key=lambda x: (x["score"], x["ts"]), reverse=True)
    top_episodes: list[dict[str, Any]] = [
        {
            "id": ep["id"],
            "summary": ep["summary"],
            "score": ep["score"],
            "components": ep["components"],
            "via": ep["via"],
        }
        for ep in scored_episodes[:k]
    ]

    # 4. Facts: all ACTIVE facts of the user (max 10) ordered by confidence desc, predicate asc
    fact_rows: list[Any] = await db.run_ro(Q_FACTS_ACTIVE, {"uid": user_id})
    raw_facts: list[dict[str, Any]] = [
        {
            "id": str(r[0]),
            "predicate": str(r[1]),
            "object": str(r[2]),
            "confidence": round(float(r[3]), 4),
            "valid_from": int(r[4]),
        }
        for r in fact_rows
    ]
    raw_facts.sort(key=lambda f: (-f["confidence"], f["predicate"]))
    facts: list[dict[str, Any]] = raw_facts[:10]

    # 5. Procedures: top-2 ACTIVE procedures with pscore > 0 and sim > 0
    proc_rows: list[Any] = await db.run_ro(
        Q_PROC_VEC,
        {"statuses": ["ACTIVE"], "k": 5, "qv": qv},
    )
    scored_procedures: list[dict[str, Any]] = []
    for row in proc_rows:
        pid: str = str(row[0])
        name: str = str(row[1])
        trigger: str = str(row[2])
        steps: list[str] = list(row[3]) if row[3] else []
        status: str = str(row[4])
        origin: str = str(row[5])
        emb = [float(x) for x in row[6]] if row[6] else []
        sim = cosine(qv, emb)
        if sim == 0.0:
            continue

        stats_res: list[Any] = await db.run_ro(Q_PROC_STATS, {"pid": pid})
        successes: int = int(stats_res[0][1] or 0) if stats_res else 0
        failures: int = int(stats_res[0][2] or 0) if stats_res else 0
        conf: float = float(successes + 1) / float(successes + failures + 2)
        pscore: float = 0.7 * sim + 0.3 * conf

        if pscore > 0:
            scored_procedures.append(
                {
                    "id": pid,
                    "name": name,
                    "trigger": trigger,
                    "steps": steps,
                    "status": status,
                    "origin": origin,
                    "score": round(pscore, 4),
                    "successes": successes,
                    "failures": failures,
                }
            )

    scored_procedures.sort(key=lambda p: p["score"], reverse=True)
    procedures: list[dict[str, Any]] = scored_procedures[:2]

    # 6. Build visit graph nodes and edge keys for UI envelope
    node_ids: list[str] = (
        [ep["id"] for ep in top_episodes]
        + [f["id"] for f in facts]
        + [p["id"] for p in procedures]
    )

    edge_keys: list[str] = []
    if len(node_ids) > 1:
        edge_res: list[Any] = await db.run_ro(
            "MATCH (a)-[r]->(b) WHERE a.id IN $ids AND b.id IN $ids RETURN a.id, type(r), b.id",
            {"ids": node_ids},
        )
        edge_keys = [f"{row[0]}|{row[1]}|{row[2]}" for row in edge_res]

    return {
        "episodes": top_episodes,
        "facts": facts,
        "procedures": procedures,
        "visit": {
            "node_ids": node_ids,
            "edge_keys": edge_keys,
        },
    }


async def find_procedures(
    tenant_id: str,
    situation: str,
    include_candidates: bool = False,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Find matching procedures for a situation text, optionally including candidates."""
    db: TenantDB = await get_tenant_db(tenant_id)
    embedder = get_embedder()
    qv: list[float] = embedder.embed(situation)

    statuses: list[str] = ["ACTIVE", "CANDIDATE"] if include_candidates else ["ACTIVE"]
    proc_rows: list[Any] = await db.run_ro(
        Q_PROC_VEC,
        {"statuses": statuses, "k": max(limit * 2, 5), "qv": qv},
    )

    results: list[dict[str, Any]] = []
    for row in proc_rows:
        pid: str = str(row[0])
        name: str = str(row[1])
        trigger: str = str(row[2])
        steps: list[str] = list(row[3]) if row[3] else []
        status: str = str(row[4])
        origin: str = str(row[5])
        emb: list[float] = [float(x) for x in row[6]] if row[6] else []
        sim: float = cosine(qv, emb)

        stats_res: list[Any] = await db.run_ro(Q_PROC_STATS, {"pid": pid})
        successes: int = int(stats_res[0][1] or 0) if stats_res else 0
        failures: int = int(stats_res[0][2] or 0) if stats_res else 0
        conf: float = float(successes + 1) / float(successes + failures + 2)
        pscore: float = 0.7 * sim + 0.3 * conf + (0.1 if status == "ACTIVE" else 0.0)

        results.append(
            {
                "id": pid,
                "name": name,
                "trigger": trigger,
                "steps": steps,
                "status": status,
                "origin": origin,
                "score": round(pscore, 4),
                "successes": successes,
                "failures": failures,
            }
        )

    results.sort(key=lambda p: p["score"], reverse=True)
    return results[:limit]
