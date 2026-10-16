"""Procedural memory layer managing outcomes, promotion, deprecation, and episodic decay.

Implements Bayesian Laplace-smoothed confidence scoring (successes + 1) / (total + 2)
for procedure promotion and deprecation criteria.
"""

from __future__ import annotations

from typing import Any

from memory_core.clock import now as get_now
from memory_core.db import TenantDB, get_tenant_db
from memory_core.errors import InvalidInputError, NotFoundError
from memory_core.queries import (
    Q_DECAY,
    Q_PROC_OUTCOME,
    Q_PROC_PROMOTABLE,
    Q_PROC_SET_STATUS,
    Q_PROC_STATS,
)
from memory_core.recall import find_procedures

__all__ = [
    "decay",
    "deprecate_procedures",
    "find_procedures",
    "promote_procedures",
    "record_outcome",
    "should_deprecate",
]


def should_deprecate(successes: int, failures: int) -> bool:
    """Evaluate whether a learned procedure meets deprecation criteria.

    Criteria: at least 5 total trials and Laplace-smoothed confidence < 0.3.
    """
    total: int = successes + failures
    if total < 5:
        return False
    conf: float = float(successes + 1) / float(total + 2)
    return conf < 0.3


async def record_outcome(
    tenant_id: str,
    session_id: str,
    procedure_id: str,
    outcome: str,
    ts: int | None = None,
) -> None:
    """Record procedural execution outcome ('success' or 'failure') for a session."""
    if outcome not in ("success", "failure"):
        raise InvalidInputError(f"Invalid outcome '{outcome}'. Expected 'success' or 'failure'")

    db: TenantDB = await get_tenant_db(tenant_id)
    exec_ts: int = ts if ts is not None else get_now()

    res: list[Any] = await db.run_rw(
        Q_PROC_OUTCOME,
        {
            "sid": session_id,
            "pid": procedure_id,
            "outcome": outcome,
            "ts": exec_ts,
        },
    )
    if not res:
        raise NotFoundError(
            f"Failed to record outcome: session '{session_id}' or procedure '{procedure_id}' not found"
        )


async def promote_procedures(
    tenant_id: str,
    min_successes: int = 2,
    min_users: int = 2,
) -> list[str]:
    """Promote qualifying CANDIDATE procedures to ACTIVE status."""
    db: TenantDB = await get_tenant_db(tenant_id)
    promotable_rows: list[Any] = await db.run_ro(
        Q_PROC_PROMOTABLE,
        {
            "min_successes": min_successes,
            "min_users": min_users,
        },
    )

    promoted: list[str] = []
    for row in promotable_rows:
        pid: str = str(row[0])
        res = await db.run_rw(
            Q_PROC_SET_STATUS,
            {
                "pid": pid,
                "from_status": "CANDIDATE",
                "to_status": "ACTIVE",
            },
        )
        if res:
            promoted.append(pid)

    return promoted


async def deprecate_procedures(tenant_id: str) -> list[str]:
    """Deprecate low-performing learned procedures that fail the confidence threshold."""
    db: TenantDB = await get_tenant_db(tenant_id)
    proc_rows: list[Any] = await db.run_ro(
        "MATCH (p:Procedure {status: 'ACTIVE', origin: 'learned'}) RETURN p.id AS id"
    )

    deprecated: list[str] = []
    for row in proc_rows:
        pid: str = str(row[0])
        stats_rows: list[Any] = await db.run_ro(Q_PROC_STATS, {"pid": pid})
        if not stats_rows:
            continue
        successes: int = int(stats_rows[0][1] or 0)
        failures: int = int(stats_rows[0][2] or 0)

        if should_deprecate(successes, failures):
            await db.run_rw(
                "MATCH (p:Procedure {id: $pid}) SET p.status = 'DEPRECATED'",
                {"pid": pid},
            )
            deprecated.append(pid)

    return deprecated


async def decay(
    tenant_id: str,
    now_ts: int | None = None,
    min_imp: float = 0.2,
    days: int = 90,
) -> list[str]:
    """Archive inactive low-importance episodes older than the cutoff threshold."""
    db: TenantDB = await get_tenant_db(tenant_id)
    current_time: int = now_ts if now_ts is not None else get_now()
    cutoff: int = current_time - (days * 86400)

    rows: list[Any] = await db.run_rw(
        Q_DECAY,
        {
            "min_imp": min_imp,
            "cutoff": cutoff,
        },
    )
    return [str(r[0]) for r in rows]
