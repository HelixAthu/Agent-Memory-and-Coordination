# Technical Explainer: SwarmGraph Memory Fabric

This document provides a plain-language yet deep technical walkthrough of the **SwarmGraph Memory Fabric**, explaining its core architecture, memory systems, coordination protocols, and design choices.

---

## 1. Why a Graph per Tenant (`mem_<tenant_id>`)

In multi-tenant AI systems, storing multiple tenants in a single database using row-level filters (`WHERE tenant_id = ?`) introduces major security risks. LLM-generated queries or prompt injection can easily bypass filter clauses.

In SwarmGraph Memory Fabric:
* Every tenant is allocated a **physically distinct FalkorDB graph key** (`mem_acme`, `mem_globex`).
* Queries are issued directly against that key via `get_tenant_db(tenant_id)`.
* Cypher queries **never accept or interpolate tenant identifiers**—there is literally no query syntax that can jump database boundaries.
* Even if an attacker injects Cypher or overrides tool arguments, the database client will strictly execute inside the pre-bound tenant graph.

---

## 2. The Three Memory Types & How Each Updates

### 2.1 Episodic Memory (Past Interactions)
* **Storage**: Closed sessions are consolidated into `Episode` nodes via `close_session()`. Each episode contains a summary, importance score ($0.0$ to $1.0$), timestamp, and a 4096-dimensional embedding.
* **Retrieval**: Retrieved via `recall()` using hybrid scoring:
  $$\text{Score} = 0.5 \times \text{CosineSimilarity} + 0.2 \times \text{Recency} + 0.2 \times \text{Importance} + 0.1 \times \text{EntityBoost}$$
* **Decay & Cleanup**: Managed by `decay()` (`memory_core.procedural.decay`). Episodes with $\text{importance} < 0.2$ and age $> 90\text{ days}$ automatically transition to status `ARCHIVED` and are excluded from future recall candidates.

### 2.2 Semantic Memory (Evolving User Facts)
* **Storage**: Stored as discrete predicate-object tuples on `Fact` nodes (e.g. `(u:User)-[:HAS_FACT]->(f:Fact)`).
* **Updates & Supersession**: Managed by `remember_fact()` (`memory_core.semantic.remember_fact`):
  * When a new fact for an existing predicate arrives (e.g. city moves from Mumbai to Pune), `Q_FACT_CLOSE_OLD` conditionally updates the existing active fact to `status = 'SUPERSEDED'` with `valid_to = now`.
  * A new active fact is created and linked via `(new)-[:SUPERSEDES]->(old)`.
  * If the exact same fact is observed again, `remember_fact` calls `Q_FACT_REINFORCE` to bump confidence by $+0.05$ (capped at $1.0$) rather than creating duplicates.
* **Auditability**: LLM agents only see `ACTIVE` facts, but queries can inspect the complete temporal history with `valid_from` and `valid_to`.

### 2.3 Procedural Memory (Runbooks & Organizational Workflows)
* **Storage**: Stored as `Procedure` nodes containing triggers, step sequences, and status (`CANDIDATE`, `ACTIVE`, `DEPRECATED`).
* **Learning & Promotion**:
  * Agent executions record outcomes using `record_procedure_outcome()` (`memory_core.procedural.record_outcome`), creating `(s:Session)-[:APPLIED {outcome: 'success'|'failure'}]->(p:Procedure)`.
  * Candidate procedures are evaluated by `promote_procedures()` (`memory_core.procedural.promote_procedures`). Once a procedure achieves at least 2 successes across at least 2 distinct users, it is promoted to `ACTIVE`.
  * Procedures with high failure rates are deprecated via Bayesian evaluation (`should_deprecate`).

---

## 3. Why Conditional Writes Act as Locks

In distributed multi-agent systems, coordinating task assignment and shared state typically requires external lock managers like Redis with Redlock.

FalkorDB executes write queries with serial isolation. We leverage this to execute **Compare-And-Set (CAS)** directly inside Cypher:

1. **Atomic Task Claiming (`claim_task`, `claim_next`)**:
   ```cypher
   MATCH (t:Task {id:$id, status:'OPEN'})
   SET t.status = 'CLAIMED', t.claimed_by = $agent, t.version = t.version + 1
   RETURN t.id AS id, t.version AS version
   ```
   If 50 agents race to claim the same task simultaneously, only the first transaction finds `status: 'OPEN'`. The other 49 match 0 nodes and return an empty result, which our client converts to `ConflictError` ("Task already claimed").

2. **Shared Session State (`set_state`)**:
   ```cypher
   MATCH (e:StateEntry {id:$eid, version:$expected})
   SET e.value = $value, e.version = e.version + 1, e.updated_by = $agent
   RETURN e.version AS version
   ```
   If another agent modified the entry in the interim, `version` no longer matches `$expected`. Zero rows update, and a `ConflictError` is raised.

---

## 4. Hybrid Recall: Combining Vector Index with Graph Traversal

Pure vector search struggles when relevant memories do not share semantic keywords with the current query.

In `recall()` (`memory_core.recall.recall`):
1. **Candidate Generation**: Vector index search (`Q_EP_VEC`) queries the FalkorDB HNSW vector index for the top-$k$ episodes matching the query embedding.
2. **Entity Discovery**: The system extracts all entity nodes referenced by candidate episodes via `[:MENTIONS]` edges (`Q_EP_ENTITIES`).
3. **Graph Hop**: Using `Q_EP_RELATED`, the graph traverses from those entities to find other episodes for the same user that mention the same entities (`[:MENTIONS]->(x:Entity)<-[:MENTIONS]-(other:Episode)`).
4. **Scoring & Fusion**: Results are merged and re-ranked in Python using composite cosine similarity, recency, importance, and entity boost.

---

## 5. The Handoff Protocol

When a triage agent delegates a customer to a specialist agent:
1. **Creation (`create_handoff`)**:
   * Creates a `Handoff` node in state `PENDING`.
   * Automatically gathers and attaches an **8-item context bundle** via `[:CARRIES]` edges: the user's active facts, top-2 recalled episodes, relevant active procedures, and prior session messages.
2. **Acceptance (`accept_handoff`)**:
   * Atomically transitions the handoff from `PENDING` to `ACCEPTED`.
   * Verifies that the accepting agent matches the designated specialist role (forbidden agents are rejected).
   * Switches the active session agent to the specialist (`current_agent`).
3. **Completion (`complete_handoff`)**:
   * Marks the handoff `COMPLETED` and attaches the resolution summary.

---

## 6. Architecture Decisions & Probe Fallbacks

During initial platform validation, probe scripts identified specific FalkorDB features:
* **FalkorDB Vector Indexing**: Probe F3 confirmed native vector queries (`CALL db.idx.vector.queryNodes`) and cosine metric.
* **StateEntry Constraints (Fallback F7)**: FalkorDB does not currently support `CREATE CONSTRAINT ... IS UNIQUE` on non-node properties. We implemented the spec's documented fallback: `MERGE (e:StateEntry {id: $eid}) ON CREATE SET ...` in `queries.py` to prevent duplicate state entries.
* **Connection Pooling**: Implemented `TenantDB` with an internal semaphore to bound inflight concurrent queries and prevent socket saturation under load.
