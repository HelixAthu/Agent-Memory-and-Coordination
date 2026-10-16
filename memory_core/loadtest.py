"""Concurrency load test engine executing checks C1 through C5 under high concurrency."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable

from memory_core.coordination import claim_next, claim_task, create_task, get_state, set_state
from memory_core.db import get_tenant_db
from memory_core.errors import ConflictError, NotFoundError
from memory_core.history import append_message, create_session
from memory_core.recall import recall
from memory_core.schema import ensure_tenant


def _calc_latencies(times_ms: list[float]) -> dict[str, float]:
    """Calculate p50, p95, p99 latencies in milliseconds."""
    if not times_ms:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
    sorted_ms = sorted(times_ms)
    n = len(sorted_ms)
    p50_idx = int(n * 0.50)
    p95_idx = min(int(n * 0.95), n - 1)
    p99_idx = min(int(n * 0.99), n - 1)
    return {
        "p50": round(sorted_ms[p50_idx], 2),
        "p95": round(sorted_ms[p95_idx], 2),
        "p99": round(sorted_ms[p99_idx], 2),
    }


async def setup_scratch_tenant(tenant_id: str) -> None:
    """Create a clean scratch tenant graph for load testing."""
    db = await get_tenant_db(tenant_id)
    try:
        _, async_g = db._ensure_async_client()
        if db._async_client is not None:
            await db._async_client.connection.execute_command("GRAPH.CONFIG", "SET", "MAX_QUEUED_QUERIES", 1024)
    except Exception:
        pass
    await db.delete_graph()
    await db.run_rw("MERGE (t:Tenant {id: $tid})", {"tid": tenant_id})
    await ensure_tenant(tenant_id)


async def cleanup_scratch_tenant(tenant_id: str) -> None:
    """Delete the scratch tenant graph."""
    db = await get_tenant_db(tenant_id)
    await db.delete_graph()


async def run_c1(tenant_id: str, num_claimants: int = 50, task_id: str | None = None) -> dict[str, Any]:
    """C1: One OPEN task and N concurrent claims; exactly 1 succeeds, N-1 yield CONFLICT."""
    tid = task_id or f"task-load-c1-{uuid.uuid4().hex[:6]}"
    await create_task(tenant_id, "High concurrency single task", priority=10, task_id=tid)

    successes = 0
    conflicts = 0
    latencies: list[float] = []

    async def _try_claim(worker_idx: int) -> None:
        nonlocal successes, conflicts
        agent_id = f"worker-{worker_idx}"
        t0 = time.perf_counter()
        try:
            await claim_task(tenant_id, tid, agent_id)
            successes += 1
        except ConflictError:
            conflicts += 1
        finally:
            latencies.append((time.perf_counter() - t0) * 1000)

    await asyncio.gather(*[_try_claim(i) for i in range(num_claimants)])

    passed = (successes == 1) and (conflicts == num_claimants - 1)
    return {
        "id": "C1",
        "name": "Single-task atomic claim exclusivity",
        "passed": passed,
        "detail": f"{successes} claim succeeded, {conflicts} conflicts out of {num_claimants} claimants",
        "latencies": latencies,
    }


async def run_c2(
    tenant_id: str,
    num_tasks: int = 200,
    num_workers: int = 20,
    task_prefix: str = "c2",
) -> dict[str, Any]:
    """C2: M tasks and N workers calling claim_next; all tasks claimed with no duplicates."""
    for i in range(num_tasks):
        await create_task(tenant_id, f"Work item {i}", priority=(i % 10), task_id=f"t-{task_prefix}-{i:03d}")

    claimed_by_worker: dict[str, list[str]] = {f"worker-{w}": [] for w in range(num_workers)}
    latencies: list[float] = []

    async def _worker_loop(w_idx: int) -> None:
        agent_id = f"worker-{w_idx}"
        while True:
            t0 = time.perf_counter()
            try:
                task = await claim_next(tenant_id, agent_id)
                latencies.append((time.perf_counter() - t0) * 1000)
                claimed_by_worker[agent_id].append(task["id"])
            except NotFoundError:
                break

    await asyncio.gather(*[_worker_loop(w) for w in range(num_workers)])

    all_claimed = [tid for tasks in claimed_by_worker.values() for tid in tasks]
    unique_claimed = set(all_claimed)
    passed = (len(all_claimed) == num_tasks) and (len(unique_claimed) == num_tasks)
    return {
        "id": "C2",
        "name": "Multi-task work stealing via claim_next",
        "passed": passed,
        "detail": f"{len(unique_claimed)} unique tasks claimed across {num_workers} workers",
        "latencies": latencies,
        "claimed_ids": unique_claimed,
    }


async def run_c3(
    tenant_id: str,
    num_workers: int = 20,
    increments_per_worker: int = 10,
    session_id: str | None = None,
) -> dict[str, Any]:
    """C3: CAS counter incremented by N workers M times with retry on CONFLICT; ends at N*M."""
    sid = session_id or f"sess-load-c3-{uuid.uuid4().hex[:6]}"
    db = await get_tenant_db(tenant_id)
    await db.run_rw(
        "MERGE (s:Session {id: $sid}) ON CREATE SET s.tenant_id = $tid, s.status = 'OPEN', s.start_time = 0",
        {"sid": sid, "tid": tenant_id},
    )
    await set_state(tenant_id, sid, "counter", "0", 0, "init-worker")

    target_total = num_workers * increments_per_worker
    latencies: list[float] = []

    async def _incrementer(worker_idx: int) -> None:
        agent = f"worker-{worker_idx}"
        for _ in range(increments_per_worker):
            while True:
                t0 = time.perf_counter()
                st = await get_state(tenant_id, sid, "counter")
                cur_val = int(st["value"])
                cur_ver = int(st["version"])
                try:
                    await set_state(tenant_id, sid, "counter", str(cur_val + 1), cur_ver, agent)
                    latencies.append((time.perf_counter() - t0) * 1000)
                    break
                except ConflictError:
                    await asyncio.sleep(0.001)

    await asyncio.gather(*[_incrementer(w) for w in range(num_workers)])

    final_state = await get_state(tenant_id, sid, "counter")
    passed = int(final_state["value"]) == target_total
    return {
        "id": "C3",
        "name": "Shared state optimistic concurrency CAS",
        "passed": passed,
        "detail": f"Counter reached {final_state['value']} (expected {target_total})",
        "latencies": latencies,
    }


async def run_c4(
    tenant_a: str = "load_a",
    tenant_b: str = "load_b",
    num_tasks: int = 200,
    num_workers: int = 20,
    increments: int = 10,
) -> dict[str, Any]:
    """C4: Run C2 and C3 simultaneously on two independent graphs; sets of IDs are disjoint."""
    t0 = time.perf_counter()
    res_c2_a, res_c2_b, res_c3_a, res_c3_b = await asyncio.gather(
        run_c2(tenant_a, num_tasks=num_tasks, num_workers=num_workers, task_prefix="c4a"),
        run_c2(tenant_b, num_tasks=num_tasks, num_workers=num_workers, task_prefix="c4b"),
        run_c3(tenant_a, num_workers=num_workers, increments_per_worker=increments, session_id="sess-load-c4a"),
        run_c3(tenant_b, num_workers=num_workers, increments_per_worker=increments, session_id="sess-load-c4b"),
    )
    wall_ms = (time.perf_counter() - t0) * 1000

    disjoint = res_c2_a["claimed_ids"].isdisjoint(res_c2_b["claimed_ids"])
    passed = res_c2_a["passed"] and res_c2_b["passed"] and res_c3_a["passed"] and res_c3_b["passed"] and disjoint
    all_lats = (
        res_c2_a["latencies"]
        + res_c2_b["latencies"]
        + res_c3_a["latencies"]
        + res_c3_b["latencies"]
    )

    return {
        "id": "C4",
        "name": "Cross-tenant parallel load and partition isolation",
        "passed": passed,
        "detail": "Both tenants completed C2/C3 correctly with mutually disjoint task sets",
        "latencies": all_lats,
        "wall_ms": wall_ms,
    }


async def run_c5(
    tenant_id: str = "acme",
    num_recalls: int = 100,
    num_messages: int = 50,
) -> dict[str, Any]:
    """C5: 100 concurrent recall calls while 50 concurrent append_message calls run on one session."""
    sid = "sess-load-c5"
    db = await get_tenant_db(tenant_id)
    await db.run_rw("MATCH (s:Session {id: $sid}) DETACH DELETE s", {"sid": sid})
    await create_session(tenant_id, "user-priya", current_agent="agent-triage", session_id=sid)

    read_lats: list[float] = []
    write_lats: list[float] = []
    seqs: list[int] = []

    async def _do_recall(idx: int) -> None:
        t0 = time.perf_counter()
        await recall(
            tenant_id=tenant_id,
            user_id="user-priya",
            query="Hello, my card shows a duplicate charge again on invoice INV-1042.",
            k=2,
        )
        read_lats.append((time.perf_counter() - t0) * 1000)

    async def _do_append(idx: int) -> None:
        t0 = time.perf_counter()
        msg = await append_message(
            tenant_id=tenant_id,
            session_id=sid,
            role="user",
            text=f"Concurrent message {idx}",
        )
        write_lats.append((time.perf_counter() - t0) * 1000)
        seqs.append(msg["seq"])

    await asyncio.gather(
        *[_do_recall(i) for i in range(num_recalls)],
        *[_do_append(i) for i in range(num_messages)],
    )

    # Clean up test session
    await db.run_rw("MATCH (s:Session {id: $sid}) DETACH DELETE s", {"sid": sid})

    seqs_unique = (len(seqs) == num_messages) and (len(set(seqs)) == num_messages)
    passed = (len(read_lats) == num_recalls) and seqs_unique
    return {
        "id": "C5",
        "name": "Mixed read/write load under graph mutations",
        "passed": passed,
        "detail": f"{num_recalls} recalls succeeded concurrently with {num_messages} unique message appends",
        "read_latencies": read_lats,
        "write_latencies": write_lats,
    }


async def run_all(
    emit: Callable[[str, dict[str, Any]], Any] | None = None,
    scale_down: bool = False,
) -> dict[str, Any]:
    """Execute complete load test suite measuring ops/s and latency profiles."""
    c1_claims = 20 if scale_down else 50
    c2_tasks = 40 if scale_down else 200
    c2_workers = 5 if scale_down else 20
    c3_workers = 5 if scale_down else 20
    c3_incs = 5 if scale_down else 10
    c5_recalls = 20 if scale_down else 100
    c5_msgs = 10 if scale_down else 50

    t_start = time.perf_counter()

    # Scratch tenants
    await setup_scratch_tenant("load_a")
    await setup_scratch_tenant("load_b")

    checks: list[dict[str, Any]] = []
    read_times: list[float] = []
    write_times: list[float] = []

    try:
        # C1
        if emit:
            await emit("load_progress", {"phase": "C1", "done": 1, "total": 5, "ops_per_s": 0.0})
        res_c1 = await run_c1("load_a", num_claimants=c1_claims)
        checks.append(res_c1)
        write_times.extend(res_c1["latencies"])

        # C2
        if emit:
            await emit("load_progress", {"phase": "C2", "done": 2, "total": 5, "ops_per_s": 0.0})
        res_c2 = await run_c2("load_a", num_tasks=c2_tasks, num_workers=c2_workers)
        checks.append(res_c2)
        write_times.extend(res_c2["latencies"])

        # C3
        if emit:
            await emit("load_progress", {"phase": "C3", "done": 3, "total": 5, "ops_per_s": 0.0})
        res_c3 = await run_c3("load_a", num_workers=c3_workers, increments_per_worker=c3_incs)
        checks.append(res_c3)
        write_times.extend(res_c3["latencies"])

        # C4
        if emit:
            await emit("load_progress", {"phase": "C4", "done": 4, "total": 5, "ops_per_s": 0.0})
        res_c4 = await run_c4(
            tenant_a="load_a",
            tenant_b="load_b",
            num_tasks=c2_tasks,
            num_workers=c2_workers,
            increments=c3_incs,
        )
        checks.append(res_c4)
        write_times.extend(res_c4["latencies"])

        # C5
        if emit:
            await emit("load_progress", {"phase": "C5", "done": 5, "total": 5, "ops_per_s": 0.0})
        res_c5 = await run_c5("acme", num_recalls=c5_recalls, num_messages=c5_msgs)
        checks.append(res_c5)
        read_times.extend(res_c5["read_latencies"])
        write_times.extend(res_c5["write_latencies"])

    finally:
        await cleanup_scratch_tenant("load_a")
        await cleanup_scratch_tenant("load_b")

    total_seconds = time.perf_counter() - t_start
    total_ops = len(read_times) + len(write_times)
    ops_per_sec = round(total_ops / total_seconds, 1) if total_seconds > 0 else 0.0

    read_lat = _calc_latencies(read_times)
    write_lat = _calc_latencies(write_times)
    all_lat = _calc_latencies(read_times + write_times)

    result = {
        "checks": [
            {"id": c["id"], "name": c["name"], "passed": c["passed"], "detail": c["detail"]}
            for c in checks
        ],
        "latency": all_lat,
        "read_latency": read_lat,
        "write_latency": write_lat,
        "ops": total_ops,
        "seconds": round(total_seconds, 2),
        "ops_per_s": ops_per_sec,
    }

    if emit:
        await emit("load_result", result)

    return result
