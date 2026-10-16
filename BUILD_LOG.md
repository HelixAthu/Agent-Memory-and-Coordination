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



