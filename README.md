# Memory Fabric: Shared Memory & Coordination Layer for AI Agents

Memory Fabric is a shared memory and coordination infrastructure built on FalkorDB, exposed to autonomous agent crews via the Model Context Protocol (MCP).

## Problem Statement

Autonomous multi-agent swarms operating in enterprise environments face critical coordination challenges:
1. **Context Amnesia Across Sessions**: LLM context windows evaporate when a session ends. Traditional key-value stores cannot model why a decision was reached, who was involved, or how past incidents connect to current problems.
2. **Fact Evolution & Stale Knowledge**: User preferences, plans, and technical configurations change over time. Overwriting facts discards audit trails, while keeping conflicting facts causes hallucinations.
3. **Fragmented Agent Handoffs**: When a triage agent transfers a customer to a specialist, either full conversation dumps overwhelm the specialist or lossy summaries omit key facts.
4. **Tenant Isolation Vulnerabilities**: Shared multi-tenant databases relying on SQL `WHERE tenant_id = ?` risk prompt injection and accidental data leakage.

## Memory Graph Schema

Memory Fabric solves this by maintaining **one dedicated FalkorDB graph per tenant** (`mem_<tenant_id>`), partitioning knowledge into three interconnected graph structures:

### Node Types

| Label | Purpose | Key Properties |
|---|---|---|
| `User` | Customer profile | `id, name` |
| `Agent` | Autonomous crew member | `id, name, role ('triage'\|'specialist'), status` |
| `Entity` | Domain knowledge nodes | `id, name, type ('topic'\|'product'\|'invoice'), keywords` |
| `Session` | Interaction boundary | `id, user_id, status ('OPEN'\|'CLOSED'), started_at, msg_count` |
| `Message` | Ordered conversation log | `id, session_id, seq, role, agent_id, text, ts` |
| `Episode` | Episodic memory | `id, summary, outcome, importance, ts, status, embedding` |
| `Fact` | Semantic memory | `id, predicate, object, confidence, status, valid_from, valid_to` |
| `Procedure` | Procedural memory | `id, name, trigger, steps, status ('ACTIVE'\|'CANDIDATE'\|'DEPRECATED')` |
| `Task` | Shared work queue | `id, title, status ('OPEN'\|'CLAIMED'\|'DONE'), priority, claimed_by` |
| `Handoff` | Inter-agent transfer | `id, status ('PENDING'\|'ACCEPTED'\|'COMPLETED'), reason, carries` |
| `StateEntry` | Coordination CAS state | `id, key, value, version, updated_by, updated_at` |

### Relationships & Provenance

```
(User)-[:HAD_SESSION]->(Session)-[:HAS_MESSAGE]->(Message)-[:NEXT]->(Message)
(Session)-[:SUMMARIZED_AS]->(Episode)-[:ABOUT]->(User)
(Episode)-[:MENTIONS]->(Entity)
(Episode)-[:INVOLVED]->(Agent)
(User)-[:HAS_FACT]->(Fact)-[:SUPERSEDES]->(Fact)
(Fact)-[:DERIVED_FROM]->(Session)
(Session)-[:APPLIED {outcome}]->(Procedure)
(Agent)-[:EXPERT_IN]->(Entity)
(Agent)-[:HANDED_OFF]->(Handoff)-[:TO]->(Agent)
(Handoff)-[:CARRIES]->(Fact|Episode|Procedure|Message)
(Session)-[:HAS_STATE]->(StateEntry)
```

## Hackathon Track
- **Graph Hacks 2026**: *Agent Memory and Coordination*
