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
