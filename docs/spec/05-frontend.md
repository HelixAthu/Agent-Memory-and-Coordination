# Spec 05: Frontend (Memory Explorer and Crew Console)

- **Purpose:** Defines the React UI: layout, memory graph behavior, memory tabs, handoff animation, load-test and isolation panels, types and acceptance.
- **Read this when:** working on T15, T16.

> **File map note:** section numbers are global across the spec files. `AGENTS.md` has the index.

---

## 9. Frontend

**Types** (`src/types.ts`) mirror Sections 7.2, 8.7 and 8.8 exactly: `GraphNode`, `GraphEdge`, `AgentEvent` (discriminated union on `type`), `Fact`, `Episode`, `Procedure`, `Task`, `Handoff`.

**Auth in the UI:** a tenant switcher (acme / globex) sets the tenant and the matching demo API key (`acme-demo-key`, `globex-demo-key`) from `.env`/`VITE_*` variables; every request sends `X-API-Key`. Switching tenant clears all UI state.

**Layout (dark mode, three columns):**
- **Left (w-96):** tenant switcher, user picker, scenario buttons (`continuity`, `fact_update`, `procedure_learning`), "Reset demo data" (admin), a **Chat** panel (messages, each with an agent badge; the input sends `POST .../messages`; in `mock` mode the input is disabled and shows "Pick a scenario"), and the **Trace** feed.
- **Center:** React Flow **memory graph** for the selected user (`GET /t/{tenant}/users/{uid}/graph`).
- **Right (w-96):** Tabs: **Episodic** | **Semantic** | **Procedural** | **Coordination** | **Proof**.

**Memory graph rules:**
- Layout with dagre `rankdir=LR`: ranks by type: User, Sessions, Episodes, Facts/Procedures, Entities, Agents/Handoffs/Tasks (use `ranksep=70`, `nodesep=30`).
- Define `nodeTypes`/`edgeTypes` outside the component; memoize node components. One component per label with a colored badge: Episode (blue), Fact (green; **SUPERSEDED = grey with strikethrough label**), Procedure (purple; CANDIDATE = dashed border, ACTIVE = solid), Session, Entity, Agent, Handoff, Task, User.
- Never render embeddings. Show at most 200 nodes (server cap).
- Highlighting is driven only by events: `memory_visit` (pulse ring on `node_ids`, animated edges on `edge_keys`); `recall_result` (glow intensity = score; show the score as a small label); `fact_update` (**superseded fact fades to grey while the new fact slides in with a `SUPERSEDES` edge**); `handoff` (an animated edge from the source Agent to the target Agent; the `CARRIES` items pulse once); `procedure_event kind=promoted` (border turns solid and a "promoted" badge appears for 3 s); `session_closed` (new Episode node appears with its edges).
- Edge id format `<src>|<REL>|<dst>`.

**Tabs:**
- *Episodic:* timeline of episodes (date, summary, importance bar, status badge; ARCHIVED shown dimmed); clicking an episode highlights it in the graph.
- *Semantic:* table of ACTIVE facts with confidence; a "Show history" toggle (`include_history=true`) expands each predicate into its supersession chain with `valid_from`/`valid_to`.
- *Procedural:* list of procedures with status, steps, `successes`/`failures`, distinct users; a candidate's progress bar toward promotion (successes/2 and users/2).
- *Coordination:* tasks (status, claimed_by, version), handoffs (status timeline PENDING to ACCEPTED to COMPLETED with the carried item counts), shared state entries.
- *Proof:* two cards. **Isolation:** button "Run isolation check" (`GET /t/{tenant}/isolation-check`) shows each check with pass/fail. **Concurrency:** button "Run load test" (admin) shows live ops/s, a latency table (p50/p95/p99), and the invariant checks C1 to C5 with pass/fail.

**Replay toggle:** loads `/replays/{scenario}` and feeds the same reducer at 600 ms per event (works with no backend session).

**Acceptance (no manual browser needed):** `npm run build` and `npx tsc --noEmit` succeed; Vitest reducer tests feed the recorded `replays/continuity.jsonl` and assert: the handoff status reached COMPLETED; an `Episode` node `ep-sess-demo-continuity` exists at the end; `recall_result.episodes[0].id == "ep-p1"`. Feeding `replays/fact_update.jsonl` asserts `fact-p-city` ends SUPERSEDED and a new ACTIVE `city` fact exists. Feeding `replays/procedure_learning.jsonl` asserts a `procedure_event` of kind `promoted` for `proc-vpn-token-reset`.
