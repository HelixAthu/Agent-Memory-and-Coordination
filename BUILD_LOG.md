# Build Log: Memory Fabric

This log tracks execution output, test results, and task completion across the build plan (T0 to T19).

---

## T0. Bootstrap

- **Commits:**
  - `chore: initialize repo with README stub, license and .gitignore`
  - `docs: add problem statement and memory graph schema`
  - `chore: add docker-compose for pinned FalkorDB`
  - `chore: scaffold python project, requirements and Makefile`
- **Acceptance Output:**
  ```bash
  $ python -c "from falkordb import FalkorDB; print(FalkorDB().select_graph('t').query('RETURN 1').result_set)"
  [[1]]
  ```
- **Pinned Docker Image Tag:** `falkordb/falkordb:v4.22.1`
- **Status:** DONE

---

## T1. FalkorDB Capability Probe

- **Commits:**
  - `chore: add falkordb capability probe`
  - `docs: record probe results and pinned image tag`
- **Acceptance Output:**
  ```text
  ==============================================================================
  Probe                     | Status | Details
  ------------------------------------------------------------------------------
  F1_async_client           | PASS   | 20 concurrent async queries succeeded
  F2_graph_isolation        | PASS   | Graphs isolated, list and delete verified
  F3_vector_index           | PASS   | returned: ['ep1', 'ep3'], scores: [0.0, 1.0]
  F4_aggregates             | PASS   | successes=2.0, users=2
  F5_write_atomicity        | PASS   | Exactly 1/50 won task claim
  F6_range_index_merge      | PASS   | Range index and MERGE ON MATCH verified
  F7_unique_constraint      | FAIL   | Unique constraint unsupported; Section 6.5 MERGE fallback enabled
  F8_list_properties        | PASS   | steps round-tripped: ['Verify charges', 'Confirm identical', 'Issue refund']
  F9_fulltext_index         | PASS   | Full-text index created and queried
  F10_throughput_info       | PASS   | 50 writes: 1 graph = 74.2ms, 2 graphs = 18.2ms
  ==============================================================================
  ```
- **Probe Summary:** Async client supported (`falkordb.asyncio`), vector index functional, write atomicity serialized, unique constraints mapped to MERGE fallback.
- **Status:** DONE

---

## T2. Core: Config, Clock, Tenancy & DB Layer

- **Commits:**
  - `feat(core): config, clock and tenant id validation`
  - `feat(core): per-tenant graph connection with pooled async client`
  - `test(core): tenancy and clock tests`
- **Acceptance Output:**
  ```bash
  $ pytest tests/test_tenancy.py
  ============================== 5 passed in 0.74s ===============================
  ```
- **Assertions:** Valid tenant IDs match pattern, SQL/Cypher injections rejected with `InvalidInputError`, graph name mapped to `mem_<tenant>`, `now()` frozen by `CLOCK_NOW`, `max_inflight` bounded by semaphore.
- **Status:** DONE

---

## T3. Embedder

- **Commits:**
  - `feat(core): tokenizer, stemmer and mock embedder`
  - `feat(core): gemini embedder behind EMBED_PROVIDER`
  - `test(core): embedder and cosine tests`
- **Acceptance Output:**
  ```bash
  $ pytest tests/test_embedder.py
  ============================== 5 passed in 0.67s ===============================
  ```
- **Assertions:** Spec stem rules asserted; tokens("INV-1042") produces ["inv", "1042"]; mock embeddings unit length; G2 cosine similarities verified (ep-p1 ≈ 0.555, ep-p3 ≈ 0.267, ep-p2 == 0.0); embedder factory verified for mock and Gemini.
- **Status:** DONE

---

## T4. Schema and Seed

- **Commits:**
  - `feat(core): schema, indexes and constraints per tenant`
  - `feat(seed): acme agents, users, entities and sessions`
  - `feat(seed): acme episodes, facts, procedures and tasks`
  - `feat(seed): globex tenant data`
  - `feat(seed): idempotent seed script with --reset`
  - `test(seed): golden counts G1`
- **Acceptance Output:**
  ```bash
  $ make seed
  .venv/bin/python seed/seed.py
  [acme] Seeded successfully: 53 nodes, 91 edges
  [globex] Seeded successfully: 11 nodes, 15 edges

  $ pytest tests/test_seed.py
  ============================== 5 passed in 1.94s ===============================
  ```
- **Assertions:**
  - `mem_acme` G1 counts match exactly: 53 nodes (Agent 3, User 2, Entity 8, Session 5, Message 20, Episode 5, Fact 6,
    Procedure 2, Task 2) and 91 edges (HAD_SESSION 5, HAS_MESSAGE 20, NEXT 15, SUMMARIZED_AS 5, ABOUT 5, MENTIONS 11,
    INVOLVED 9, HAS_FACT 6, DERIVED_FROM 5, SUPERSEDES 1, APPLIED 2, EXPERT_IN 5, FOR_USER 2).
  - `mem_globex` G1 counts match exactly: 11 nodes (Agent 1, User 1, Entity 1, Session 1, Message 4, Episode 1, Fact 1,
    Procedure 1) and 15 edges.
  - Seeding is idempotent; repeated runs leave counts unchanged.
  - Every Fact is attached via `HAS_FACT` to exactly one User.
  - Graph export serialization sanitization strips `embedding` keys from all nodes.
- **Tag:** `v0.1-core`
- **Status:** DONE

---

## T5. History and Semantic Memory

- **Commits:**
  - `feat(history): atomic message append and history chain`
  - `feat(semantic): remember_fact with supersession and reinforcement`
  - `test(semantic): supersession and concurrency tests G4 G5 G14`
- **Acceptance Output:**
  ```bash
  $ pytest tests/test_history.py tests/test_semantic.py
  ============================== 5 passed in 1.50s ===============================
  ```
- **Assertions:**
  - G4: superseding city and prefers_channel creates new ACTIVE facts and sets old facts to SUPERSEDED with valid_to.
  - G5: reinforcing identical active fact (plan=Pro) increments confidence to 0.95 without creating a new Fact node.
  - G14: 3 concurrent message appends on a session with 4 messages assign sequence numbers {5, 6, 7} with 6 NEXT edges.
  - Concurrency: 10 concurrent remember_fact calls for a new predicate leave exactly 1 ACTIVE fact for the user.
  - InvalidInputError raised when attempting to set an unregistered predicate.
- **Status:** DONE

---

## T6. Recall and Consolidation

- **Commits:**
  - `feat(recall): hybrid vector and graph recall with scoring`
  - `test(recall): golden recall G2 G3`
  - `feat(consolidation): close_session episode creation and fact extraction`
  - `test(consolidation): golden G9`
- **Acceptance Output:**
  ```bash
  $ pytest tests/test_recall.py tests/test_consolidation.py
  ============================== 5 passed in 1.46s ===============================
  ```
- **Assertions:**
  - G2: recall for user-priya produces exact ranking [ep-p1, ep-p3, ep-p2] with ep-p3 boost=1 and ep-p1 boost=0.
  - Scores match G2 expectations: ep-p1 ≈ 0.485, ep-p3 ≈ 0.405, ep-p2 ≈ 0.087 within 0.05 tolerance.
  - Active facts returned: exactly {fact-p-plan, fact-p-channel, fact-p-city}.
  - Procedures returned: [proc-dup-charge-refund] (CANDIDATE procedure excluded).
  - G3: recall for rahul isolates rahul episodes and facts without cross-user leakage.
  - Cross-tenant isolation: globex recall returns only Dana's episode, no acme data.
  - G9: close_session creates episode ep-sess-demo-continuity with importance 0.8 (0.6 base + 0.2 handoff),
    INVOLVED {agent-triage, agent-billing}, MENTIONS {topic-billing, topic-refunds, invoice-inv-1042},
    and marks session CLOSED.
- **Status:** DONE

---

## T7. Procedural Memory and Decay

- **Commits:**
  - `feat(procedural): outcomes, promotion, deprecation and decay`
  - `test(procedural): promotion and decay goldens G6 G10`
- **Acceptance Output:**
  ```bash
  $ pytest tests/test_procedural.py
  ============================== 3 passed in 0.52s ===============================
  ```
- **Assertions:**
  - `should_deprecate` truth table asserted: (0, 5) and (1, 4) deprecate; (3, 2) and (0, 4) do not.
  - G6: `decay()` archives exactly `ep-r2` (importance 0.1 < 0.2 and age 135 days > 90); archived episodes never appear in recall.
  - G10: `proc-vpn-token-reset` is initially CANDIDATE with 1 success from 1 user (Priya); after recording success in a Rahul session, `promote_procedures()` promotes it to ACTIVE and returns `['proc-vpn-token-reset']`; second call returns `[]`.
  - CANDIDATE procedures are excluded from default recall but included in `find_procedures(include_candidates=True)`.
- **Status:** DONE

---

## T8. Coordination

- **Commits:**
  - `feat(coord): task claiming and shared-state CAS`
  - `feat(coord): routing and handoff protocol`
  - `test(coord): goldens G7 G8 G11 G12`
- **Acceptance Output:**
  ```bash
  $ pytest tests/test_coordination.py
  ============================== 4 passed in 1.26s ===============================
  ```
- **Assertions:**
  - G7: load-aware routing returns correct specialist agents for all topics; unknown topic returns NotFoundError.
  - G8: handoff carries exactly 8 elements (3 facts, 2 episodes, 1 procedure, 2 messages); state machine enforces PENDING -> ACCEPTED -> COMPLETED; unauthorized accept returns ForbiddenError; second accept returns ConflictError; 10 concurrent accepts produce exactly 1 success and 9 ConflictError.
  - G11: claiming task-001 succeeds with version 2; second claim yields ConflictError; claim_next returns NotFoundError when no OPEN tasks remain.
  - G12: shared state CAS handles version increments and conflicts; 20 concurrent CAS increments successfully terminate with counter value 20.
- **Tag:** `v0.2-memory`
- **Status:** DONE

---

## T9. MCP Server

- **Commits:**
  - `feat(mcp): server skeleton, context checks and envelope`
  - `feat(mcp): memory read tools`
  - `feat(mcp): memory write and coordination tools`
  - `feat(mcp): role allowlists and server-side enforcement`
  - `test(mcp): tool contracts, schema simplicity and isolation G13`
- **Acceptance Output:**
  ```bash
  $ pytest tests/test_mcp_tools.py tests/test_schema_simple.py tests/test_isolation.py
  ============================== 9 passed in 5.61s ===============================
  ```
- **Assertions:**
  - MCP server exposes all 16 memory and coordination tools with standardized envelopes.
  - Every tool description includes "Use when:" and "Do not use when:".
  - Schema simplifier removes context fields, inlines `$ref`, flattens `anyOf [X, null]`, and passes `assert_simple_schema`.
  - G13 verified: agent-triage calling `accept_handoff` yields FORBIDDEN; malicious tenant IDs yield INVALID_INPUT; session ownership mismatch yields FORBIDDEN; Rahul recall never returns Priya data.
  - 20 parallel `recall_memory` calls over a single stdio MCP session all succeed.
- **Status:** DONE

---

## T10. LLM Adapter & Schema Simplifier

- **Commits:**
  - `fc5cc8c` `feat(llm): provider-neutral interface and tool schema simplifier`
  - `ebdcd38` `feat(llm): gemini session with thought-signature handling`
  - `0117048` `chore: gemini probe script`
- **Acceptance Output:**
  ```bash
  $ pytest tests/test_llm_gemini.py
  ============================== 5 passed in 0.94s ===============================
  ```
- **Assertions:**
  - Provider-neutral LLMSession, ToolCall, TurnResult interfaces with FakeLLMClient.
  - Tool schema simplifier flattens definitions, handles anyOf/allOf, and strips context fields.
  - GeminiClient handles thought signatures with round-trip thought recovery.
  - Standalone probe script with replay fallback tested.
- **Status:** DONE

---

## T11. Agent Event Bus, Bridge & Mock Scenarios

- **Commits:**
  - `af5e045` `feat(agent): event bus and bridge with context injection`
  - `feat(agent): scripted mock scenarios`
- **Acceptance Output:**
  ```bash
  $ pytest tests/test_agent_mock.py
  ============================== 6 passed in 1.83s ===============================
  ```
- **Assertions:**
  - EventBus emits and collects structured events with subscribers and log sinks.
  - MCPBridge dispatches tool calls, hides non-allowlisted tools per role, and injects context envelopes.
  - Scripted mock agent runner executes all 3 core scenarios: continuity, fact_update, procedure_learning.
  - Goldens G2, G4, G8, G9, G10 verified end-to-end via event bus and tenant graph assertions.
  - Headless script generates replays for continuity, fact_update, and procedure_learning.
- **Status:** DONE

---

## T12. Live Agent Loop (Gemini)

- **Commits:**
  - `feat(agent): crew runner with handoff chaining`
  - `feat(agent): live gemini turn loop and prompts`
- **Acceptance Output:**
  ```bash
  $ pytest tests/test_agent_live.py
  ============================== 5 passed in 0.81s ===============================
  ```
- **Assertions:**
  - Turn loop enforces maximum 10-call tool cap and repeated tool call abort.
  - Tool execution errors fed back to model with `is_error=True`.
  - Handoff chaining initiates specialist turn automatically upon `create_handoff`.
  - Specialized event emissions verified.
  - *Note on Gemini Live Run:* Tested with stubbed and mock LLM clients; live Gemini execution skipped when `GEMINI_API_KEY` is unset.
- **Status:** DONE

---

## T13. API Gateway & Realtime Streaming

- **Commits:**
  - `feat(api): tenant api keys and routes`
  - `feat(api): sessions, messages and sse stream`
  - `test(api): end to end scenario, 403 isolation and restart persistence` (Tag: `v0.3-agents`)
- **Acceptance Output:**
  ```bash
  $ pytest tests/test_api.py
  ============================== 6 passed in 2.14s ===============================
  ```
- **Assertions:**
  - Tenant API key verification: `/t/acme/...` with acme key passes, globex returns 403.
  - Server-Sent Events (SSE) stream emits real-time events for session turns.
  - Admin endpoints (`/admin/reset`, `/admin/loadtest`) require `X-Admin-Key`.
  - Durability across restart verified: sessions and messages persist cleanly.
- **Status:** DONE

---

## T14. Concurrency Load Test & Invariants

- **Commits:**
  - `feat(load): concurrency load test and invariants`
  - `docs: record load results`
- **Acceptance Output:**
  ```bash
  $ python scripts/load_test.py
  Total Operations: 1400 ops in 7.36s (190.2 ops/s)
  C1 Single-task atomic claim exclusivity: PASS
  C2 Multi-task work stealing via claim_next: PASS
  C3 Shared state optimistic concurrency CAS: PASS
  C4 Cross-tenant parallel load and partition isolation: PASS
  C5 Mixed read/write load under graph mutations: PASS
  ```
- **Assertions:** Real load numbers recorded in `evals/load_results.md`.
- **Status:** DONE

---

## T15. Frontend Scaffold & Graph Rendering

- **Commits:**
  - `chore(web): scaffold vite, tailwind and shadcn`
  - `feat(web): tenant switcher and memory graph rendering`
- **Acceptance Output:**
  ```bash
  $ npm run build && npx tsc --noEmit
  ✓ built in 2.00s
  ```
- **Assertions:**
  - React 18, Vite, Tailwind CSS, Lucide icons, and React Flow configured.
  - Dagre LR hierarchy ranks User -> Sessions -> Episodes -> Facts/Procedures -> Entities -> Agents.
  - Tenant switcher toggles between Acme and Globex graphs.
- **Status:** DONE

---

## T16. Streaming UI, Tabs, Proof & Replay Mode

- **Commits:**
  - `feat(web): event reducer and sse hook with tests`
  - `feat(web): chat panel and trace feed`
  - `feat(web): graph highlighting for recall, supersession and handoff`
  - `feat(web): memory tabs`
  - `feat(web): proof tab for isolation and load test`
  - `feat(web): replay mode` (Tag: `v0.4-ui`)
- **Acceptance Output:**
  ```bash
  $ npx vitest run
  ✓ src/__tests__/eventReducer.test.ts (4)
    ✓ Memory Event Reducer
      ✓ initializes clean memory state
      ✓ processes replays/continuity.jsonl to exact acceptance criteria
      ✓ processes replays/fact_update.jsonl to exact acceptance criteria
      ✓ processes replays/procedure_learning.jsonl to exact acceptance criteria
  Test Files 1 passed (1)
  ```
- **Assertions:**
  - Pure event reducer processes all recorded headless replay files.
  - Replay toggle loads scenarios and plays events at 600ms per event without backend session.
  - Graph highlights recall glows, supersession transitions, handoff animations, and promotion badges.
- **Status:** DONE

---

## T17. Evaluation Harness & Baselines

- **Commits:**
  - `feat(evals): scenario harness, ablation and results`
- **Acceptance Output:**
  ```bash
  $ python evals/run_evals.py
  [PASS] Memory Correctness: Top-1=ep-p1, Facts=3, Decayed=1
  [PASS] Handoff Integrity: Carried=8/8, Exactly-1 accept (1 win, 9 conflicts)
  [PASS] Tenant & User Isolation: 0 cross-tenant leaks, 0 cross-user leaks
  [PASS] Concurrency Invariants: C1=True, C2=True, C3=True, C4=True, C5=True (ops/s: 270.6)
  [PASS] Tool Selection & Allowlist: Called 10 expected tools, triage accept blocked with FORBIDDEN
  [PASS] Persistence across Restart: Top-1 episode persisted as ep-sess-demo-continuity
  [PASS] Latency (Recall & Query): p50: 50.70 ms, p95: 70.67 ms
  ```
- **Assertions:**
  - `evals/scenarios.yaml`, `evals/run_evals.py`, `evals/ablation.py`, `evals/results.md` generated.
  - 100% test pass on mock harness; ablation baseline handles missing API key gracefully.
- **Status:** DONE

---

## T18. Documentation, CI & Full-Stack Compose

- **Commits:**
  - `docs: query reference with golden results`
  - `docs: readme with graph model, memory types and ai disclosure`
  - `chore: github actions ci`
  - `chore: dockerfiles and full-stack compose`
- **Acceptance Output:**
  - GitHub Actions CI workflow in `.github/workflows/ci.yml` with FalkorDB service container.
  - Full-stack `docker-compose.yml` with backend, frontend, and FalkorDB.
  - Query reference in `docs/queries.md` with all Cypher queries documented.
- **Status:** DONE

---

## T19. Owner Handoff & Release

- **Commits:**
  - `docs: explainer, owner questions and demo script`
  - `docs: add demo video link` (Tag: `v1.0`)
- **Acceptance Output:**
  - Technical explainer in `docs/EXPLAINER.md` referencing real function names.
  - 20 judge questions and model answers in `docs/OWNER_QUESTIONS.md`.
  - 3-minute timed walkthrough script in `docs/demo_script.md`.
- **Status:** DONE

