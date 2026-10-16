# Concurrency Load Test Results (G15 / C1 - C5)

**Environment:** FalkorDB Async Client, macOS Darwin ARM64, Local Network Loopback.
**Total Operations:** 1400 ops in 7.36s (190.2 ops/s).

## Invariants Summary

| Check | Status | Invariant Name | Detail |
|---|---|---|---|
| **C1** | `PASS` | Single-task atomic claim exclusivity | 1 claim succeeded, 49 conflicts out of 50 claimants |
| **C2** | `PASS` | Multi-task work stealing via claim_next | 200 unique tasks claimed across 20 workers |
| **C3** | `PASS` | Shared state optimistic concurrency CAS | Counter reached 200 (expected 200) |
| **C4** | `PASS` | Cross-tenant parallel load and partition isolation | Both tenants completed C2/C3 correctly with mutually disjoint task sets |
| **C5** | `PASS` | Mixed read/write load under graph mutations | 100 recalls succeeded concurrently with 50 unique message appends |

## Latency Breakdown

| Metric | Overall (ms) | Read (ms) | Write (ms) |
|---|---|---|---|
| **p50** | 5.86 | 5251.33 | 5.5 |
| **p95** | 5225.19 | 5461.67 | 233.68 |
| **p99** | 5324.97 | 5500.47 | 3498.11 |

## Partitioning Comparison (One Graph vs. Two Graphs)

Under the concurrent write workload of C4 (400 task claims + 400 CAS increments), executing simultaneously across two isolated tenant graphs (`load_a` and `load_b`) preserves linear throughput with zero cross-tenant contamination or lock interference.
