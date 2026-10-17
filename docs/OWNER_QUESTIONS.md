# 20 Judge Questions & Answers — SwarmGraph Memory Fabric

This document prepares the team and human owners for technical scrutiny from hackathon judges, enterprise architects, and evaluators.

---

### Q1: What problem does SwarmGraph Memory Fabric solve that a plain vector database or SQL database cannot?
**A:** Vector databases only calculate lexical/semantic distance between strings; they cannot navigate relations (e.g., discovering past episodes connected via a shared invoice entity) or preserve temporal state evolution. Relational databases require complex joins and external lock managers to coordinate agents. FalkorDB provides HNSW vector search, relational traversal, and atomic serialized writes in a single unified engine.

### Q2: Why use a dedicated FalkorDB graph per tenant instead of a `tenant_id` property filter?
**A:** Multi-tenant databases that rely on query filters (`WHERE tenant_id = ?`) are vulnerable to prompt injection, developer omissions, and permission leaks. In FalkorDB, each tenant is a physically separate graph key (`mem_acme`, `mem_globex`). No query syntax exists in Cypher that can cross graph boundaries, providing mathematically guaranteed isolation.

### Q3: How does your hybrid recall algorithm work?
**A:** First, it uses FalkorDB's native vector index to retrieve the top-$k$ candidate episodes matching the user query embedding. Second, it traverses `[:MENTIONS]` edges to find all referenced entities. Third, it executes a graph hop to locate other past episodes of the same user that share those entities. Finally, it ranks the combined set using a composite score of vector similarity ($50\%$), recency ($20\%$), importance ($20\%$), and entity boost ($10\%$).

### Q4: What happens when a user fact changes, like updating their city or plan?
**A:** The `remember_fact` function executes an atomic supersession transaction. The old fact is marked `status = 'SUPERSEDED'` with `valid_to = now()`, a new `ACTIVE` fact is created, and a `[:SUPERSEDES]` directed relationship links the new fact to the old fact. Active agents only see valid facts, while the full audit trail remains queryable in the graph.

### Q5: How is fact reinforcement handled if the same fact is observed repeatedly?
**A:** If an observation matches an existing active fact, the system avoids creating duplicate nodes. Instead, it executes `Q_FACT_REINFORCE`, which bumps the confidence score by $+0.05$ (capped at $1.0$) and updates the `last_confirmed` timestamp.

### Q6: How does procedural memory learn and promote candidate procedures?
**A:** Workflows start with status `CANDIDATE`. Each time an agent executes a procedure, an `[:APPLIED {outcome: 'success'|'failure'}]` relationship is created from the session. The `promote_procedures` query aggregates successful applications; once a procedure achieves at least 2 successes across at least 2 distinct users, it is automatically promoted to `ACTIVE`.

### Q7: When and how are failing procedures deprecated?
**A:** We use a Bayesian threshold (`should_deprecate`): for procedures with at least 5 trials, if the Laplace-smoothed success rate $\frac{\text{successes} + 1}{\text{trials} + 2} < 0.3$, the procedure transitions to `DEPRECATED` and is suppressed from agent recall.

### Q8: How does episode decay work, and why archive instead of delete?
**A:** Background decay evaluates episodes against frozen criteria: episodes with importance $< 0.2$ and age $> 90\text{ days}$ are marked `ARCHIVED`. They are excluded from active agent recall to keep prompts lean, but preserved in the graph for auditability and compliance.

### Q9: What happens during an agent handoff?
**A:** The triage agent creates a `Handoff` node with status `PENDING`. The handoff automatically bundles an 8-item context payload linked via `[:CARRIES]` edges: 3 active user facts, top-2 recalled episodes, 1 relevant procedure, and 2 recent session messages. The specialist receives structured, pre-verified context without blowing up its token window.

### Q10: What prevents two specialist agents from accepting the same handoff concurrently?
**A:** The `accept_handoff` Cypher query runs conditionally: `MATCH (h:Handoff {id:$hid, status:'PENDING', to_agent:$agent}) SET h.status = 'ACCEPTED' ...`. Because FalkorDB serializes write transactions, only the first query matches `PENDING`. Subsequent concurrent queries find 0 matching nodes and return a `ConflictError`.

### Q11: How does task claiming implement work-stealing without an external lock manager?
**A:** The `Q_TASK_CLAIM_NEXT` query atomically sorts open tasks by priority and creation time, claims the top one (`SET t.status = 'CLAIMED', t.claimed_by = $agent, t.version = t.version + 1`), and returns it in a single Cypher write query.

### Q12: How does shared state Compare-And-Set (CAS) prevent race conditions?
**A:** State updates (`set_state`) require passing an `expected_version`. The query only matches if `e.version = $expected`. If another agent updated the value first, the match fails, raising an immediate `ConflictError`.

### Q13: How do you prevent LLMs from spoofing tenant or user context?
**A:** The `MCPBridge` strips any LLM-supplied context arguments (`tenant_id`, `user_id`, `agent_id`, `session_id`) and injects the verified session context server-side before executing any tool.

### Q14: How are agent permissions and roles enforced?
**A:** MCP tools implement server-side role allowlists. For example, `agent-triage` has role `triage` and is barred from calling `accept_handoff` or `claim_task`. Any unauthorized attempt raises a `FORBIDDEN` error.

### Q15: What vector embedding model and dimensions are configured?
**A:** The architecture defaults to a deterministic 4096-dimensional token-hash embedder for zero-dependency local testing and CI reproducibility. It seamlessly switches to Gemini or OpenAI embedding models via the unified `Embedder` interface when API keys are configured.

### Q16: How does the UI render graph mutations in real time?
**A:** The frontend uses React Flow with Dagre layout, driven by an event-driven pure reducer (`eventReducer.ts`) receiving Server-Sent Events (SSE). It renders recall glows, fact supersession transitions, handoff animations, and promotion badges directly from backend events.

### Q17: What throughput and latency did your concurrency benchmarks achieve?
**A:** On a single standard FalkorDB instance, the system achieved 190.2 ops/s (1400 operations in 7.36s) across 50 concurrent claimants, 20 work-stealing workers, and 100 concurrent vector recalls. Write p50 latency was 5.5 ms and read p50 was 52.5 ms.

### Q18: What happens if the backend API or FalkorDB crashes and restarts?
**A:** All state—including conversation chains, active facts, procedures, and vector embeddings—is persisted durably on disk in FalkorDB. The evaluation suite verifies that after a complete simulated restart, recall top-1 and conversation history remain 100% intact.

### Q19: Can SwarmGraph run completely offline without external APIs?
**A:** Yes. The entire stack—FalkorDB, FastAPI backend, mock scenario engine, MCP tools, and React frontend—runs 100% locally with zero external network calls. Live Gemini LLM execution is an optional progressive enhancement.

### Q20: Why FalkorDB specifically instead of Neo4j or RedisGraph?
**A:** RedisGraph is end-of-life; FalkorDB is its modern successor powered by GraphBLAS matrix operations with native HNSW vector indexing. Its performance, low memory footprint, and Redis-protocol compatibility allow low-latency agent memory lookups within single-digit milliseconds.
