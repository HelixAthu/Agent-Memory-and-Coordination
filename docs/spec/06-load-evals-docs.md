# Spec 06: Load test, evals, README requirements, demo script

- **Purpose:** Defines the concurrency load test, evaluation metrics (including the no-memory ablation), README content and the demo script.
- **Read this when:** working on T14, T17, T18, T19.

> **File map note:** section numbers are global across the spec files. `AGENTS.md` has the index.

---

## 10. Load test and evals

### 10.1 Load test (`scripts/load_test.py`, also callable as `memory_core.loadtest.run_all(emit)`)
Runs in-process against `memory_core` services (what the MCP tools wrap), using `asyncio.gather` with the pooled async client, and uses **separate scratch tenants** `load_a` and `load_b` (created by `ensure_tenant`, deleted at the end) so seed data is untouched. Checks (G15):
- **C1** one task, 50 concurrent claims: exactly 1 success, 49 `CONFLICT`.
- **C2** 200 tasks, 20 workers calling `claim_next` until `NOT_FOUND`: exactly 200 successes, no duplicate task ids, per-worker counts sum to 200.
- **C3** CAS counter: 20 workers x 10 increments with retry on `CONFLICT`: final value 200.
- **C4** run C2 and C3 on `load_a` and `load_b` simultaneously: each correct; the set of ids in one graph is disjoint from the other.
- **C5** 100 concurrent `recall` calls (against `mem_acme`) while 50 `append_message` calls run on one session: all succeed; also assert the resulting seq values are unique.
Also measure and report: total operations, wall seconds, ops/s, latency p50/p95/p99 of reads and of writes separately, and **the same write workload on 1 graph versus split across 2 graphs** (report honestly whichever is faster; do not claim a speedup you did not measure). Output: a `load_result` event, and `evals/load_results.md`.

### 10.2 Evals (`evals/`)
`scenarios.yaml` lists the scenarios (`continuity`, `fact_update`, `procedure_learning`, `isolation`, `tool_allowlist`) with expected outcomes taken from `docs/spec/01-data.md` Section 3. `run_evals.py` runs each in mock mode (1 run) and, when `GEMINI_API_KEY` is set and `--live` is passed, in live mode (default 5 runs each). Metrics:

| Metric | Method |
|---|---|
| Memory correctness | `recall` top-1 episode, fact sets, supersession history match G2 to G6 |
| Handoff integrity | G8 state machine; exactly-once accept under 10 concurrent accepts |
| Isolation | 0 cross-tenant and 0 cross-user leaks across all checks in G13 |
| Concurrency | C1 to C5 pass |
| Tool selection (live) | the set of tools called per scenario matches the expected set (order-insensitive); no tool outside the role allowlist is attempted |
| Persistence | after a simulated backend restart (new process, same FalkorDB), recall returns the same top-1 and the history is intact |
| Latency | p50/p95 of recall and of an end-to-end turn |

**Memory ablation baseline** (`evals/ablation.py`, live mode only, needs a key): run the `continuity` scenario twice, once normally and once with `recall_memory`, `get_user_profile` and `find_procedure` returning empty results. Score each final conversation with simple string checks (does an agent message mention the earlier INV-1042 refund? does it avoid asking the customer to repeat their plan? does it follow the refund procedure steps?). Record honestly in `evals/results.md`, including if the difference is small.

Write results to `evals/results.md` as a Markdown table.

## 11. README requirements and demo script

### 11.1 README sections, in order
Pitch + screenshot/GIF placeholder; **why the graph is load-bearing** (table below); architecture diagram (Mermaid); **graph data model** (tables from Section 1); **memory types** (episodic, semantic, procedural: how each is stored, retrieved, updated); **queries and algorithms the product depends on** (link to `docs/queries.md` and inline the top 5: Q-EP-VEC, Q-EP-RELATED, Q-FACT-CLOSE-OLD, Q-PROC-PROMOTABLE, Q-TASK-CLAIM-NEXT); **multi-tenancy and isolation** (graph per tenant, context injection, allowlists, API keys); **concurrency model** (atomic conditional writes, CAS, results of the load test with real numbers); MCP tools table; setup (exact commands); demo scenarios; eval results; **AI assistance disclosure**; limitations (synthetic data, rule-based extraction, mock embedder default, any fallback used); track entered: *Agent Memory and Coordination*.

### 11.2 "Why the graph is load-bearing" table (put in README)

| Capability | How FalkorDB does it | Why a flat store or plain vector DB fails |
|---|---|---|
| Hybrid recall | Vector index finds candidates; graph hop (`MENTIONS` entities) pulls related episodes the vector search missed | Pure vector search cannot follow shared entities; it needs a second system |
| Memory that changes over time | `SUPERSEDES` chains keep history; only ACTIVE facts are recalled | Overwriting rows loses history; append-only stores cannot answer "what was true then" cheaply |
| Procedural learning | Promotion rule counts distinct users over `APPLIED` edges with one aggregation query | Needs a join across sessions, users and outcomes |
| Handoffs | Context bundle assembled by traversal and stored as `CARRIES` edges; atomic state transitions | Chat history alone cannot carry structured, auditable context |
| Routing | Load-aware match over `EXPERT_IN` and `CLAIMED` tasks in one query | Needs a separate scheduler |
| Tenant isolation | Graph per tenant: there is no query that can cross the boundary | Row-level filters can be forgotten in a single query |
| Coordination state | Conditional writes in one query act as locks/CAS | Needs Redis locks plus a database |

### 11.3 Demo script (`docs/demo_script.md`, about 3 minutes)
0:00 problem: agents forget between sessions and cannot coordinate; show the memory graph for Priya (3 past episodes, facts, procedures). 0:25 run `continuity`: triage recalls the August duplicate charge and her preferences (glow with scores), the second episode reached through the graph hop, then hands off to Billing (animated edge, 8 carried items). 1:10 Billing accepts, follows the refund procedure, resolves; a new episode node appears; open the Procedural tab. 1:35 run `fact_update`: "I moved to Pune and prefer chat": old facts fade to grey, new ones slide in; show history. 1:55 run `procedure_learning` with Rahul: the candidate procedure becomes ACTIVE (progress bar completes). 2:15 Proof tab: isolation check (switch to Globex, same words, different memory, acme key gets 403) and the load test (200 tasks, exactly-once claims, real latency numbers). 2:50 close: graph per tenant, atomic writes, memory as a service over MCP.
