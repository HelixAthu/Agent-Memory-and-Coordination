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
