# Spec 03: MCP tools

- **Purpose:** Defines the 16 MCP memory and coordination tools: names, inputs, outputs, the response envelope, context injection and role allowlists.
- **Read this when:** working on T9, T11, T12.

> **File map note:** section numbers (for example "Section 2.3", "G2", "Q-RECALL") are global across the spec files. `AGENTS.md` has the index that says which file holds which section.

---

## 7. MCP tools

### 7.1 Context fields (hidden from the LLM)
Every tool function has four required leading parameters, `tenant_id`, `user_id`, `agent_id`, `session_id` (the **context fields**), followed by its own parameters. The runtime (`backend/mcp_bridge.py`) injects the context fields into every call. They are **removed from the tool schema shown to the LLM**. If the LLM supplies a context field anyway, the bridge **overwrites** it with the bound value (and logs a `warning` event).

Server-side checks on every call (defense in depth, in `memory_mcp/context.py`):
1. `tenant_id` must be in env `TENANTS` and match the regex (else `INVALID_INPUT`).
2. `agent_id` must exist in the tenant graph; its `role` determines the allowlist below (else `FORBIDDEN`).
3. `user_id` must exist in the tenant graph (else `NOT_FOUND`); the `session_id` must belong to that user (else `FORBIDDEN`).

### 7.2 Response envelope (all tools)
```json
{"ok": true, "data": {...},
 "visit": {"kind": "recall|write|handoff|task|state", "node_ids": [...], "edge_keys": [...]},
 "evidence": {"query_ids": ["Q-EP-VEC", "..."], "graph": "mem_acme", "ms": 12.3}}
```
Error: `{"ok": false, "error": {"code": "NOT_FOUND|INVALID_INPUT|FORBIDDEN|CONFLICT|DB_ERROR", "message": "...", "details": {...}}}`. `details` carries e.g. `current_version`. The envelope is returned as a JSON string in one text content item. Each tool description must contain two sentences starting `Use when:` and `Do not use when:`. Input models must not use `Optional` or unions (use defaults). **Never put `tenant_id` or the graph name into text the LLM can read except in `evidence.graph` (stripped before sending tool results to the LLM; the UI still receives it).**

### 7.3 Tools (LLM-visible parameters only; context fields omitted)

| # | Tool | LLM-visible input | `data` |
|---|---|---|---|
| 1 | `get_user_profile` | `include_history: bool=false` | `{facts:[{id,predicate,object,confidence}], history?:{predicate:[...]}}` |
| 2 | `recall_memory` | `query: str`, `k: int=3 (1..5)` | `{episodes:[{id,summary,score,components,via}], facts:[...], procedures:[{id,name,steps,score}]}` (Section 5.2) |
| 3 | `remember_fact` | `predicate: str (enum plan\|prefers_channel\|city)`, `object: str`, `confidence: float=0.8` | `{action:'created'\|'reinforced'\|'superseded', fact_id, old_fact_id}` |
| 4 | `find_procedure` | `situation: str`, `include_candidates: bool=true` | `{procedures:[{id,name,steps,status,successes,failures,score}]}` |
| 5 | `record_procedure_outcome` | `procedure_id: str`, `outcome: str (enum success\|failure)` | `{procedure_id, outcome, successes, failures, success_users}` |
| 6 | `route_to_specialist` | `topic_id: str` | `{candidates:[{id,name,load}]}` |
| 7 | `create_handoff` | `to_agent_id: str`, `reason: str` | `{handoff_id, carries:{fact,episode,procedure,message}, carries_total}` |
| 8 | `get_pending_handoffs` | none | `{handoffs:[{id,reason,from_agent,session_id}]}` |
| 9 | `accept_handoff` | `handoff_id: str` | `{handoff_id, status:'ACCEPTED', bundle:[{kind,id,...}]}` |
| 10 | `complete_handoff` | `handoff_id: str`, `outcome: str (enum resolved\|escalated)`, `summary: str` | `{handoff_id, status:'COMPLETED'}` |
| 11 | `create_task` | `title: str`, `priority: int=1 (1..5)` | `{task_id}` (linked `FOR_USER` the context user) |
| 12 | `claim_next_task` | none | `{task_id, title, version}` |
| 13 | `complete_task` | `task_id: str` | `{task_id, status:'DONE'}` |
| 14 | `get_shared_state` | `key: str` | `{key, value, version}` |
| 15 | `set_shared_state` | `key: str`, `value: str`, `expected_version: int=0` | `{key, version}` or `CONFLICT` with `details.current_version` |
| 16 | `close_session` | `outcome: str (enum resolved\|escalated\|abandoned)`, `summary: str=""` | `{episode_id, importance, facts_changed:[...], promoted:[...]}` (Section 5.4) |

`create_handoff` uses the context `agent_id` as `from_agent`. `accept_handoff` and `complete_handoff` use the context `agent_id` as the acting agent. The write tools emit `visit.kind` of `write`, `handoff`, `task` or `state`.

### 7.4 Role allowlists (`memory_mcp/allowlist.py`; enforced in the bridge **and** on the server)
- **triage:** `get_user_profile`, `recall_memory`, `remember_fact`, `find_procedure`, `route_to_specialist`, `create_handoff`, `create_task`, `close_session`.
- **specialist:** `get_user_profile`, `recall_memory`, `remember_fact`, `find_procedure`, `record_procedure_outcome`, `get_pending_handoffs`, `accept_handoff`, `complete_handoff`, `claim_next_task`, `complete_task`, `get_shared_state`, `set_shared_state`, `close_session`.

The bridge shows the LLM only the tools in its role's allowlist. The server rejects any other call with `FORBIDDEN` (G13).

### 7.5 Notes for implementers
- Tool functions are thin: validate, call one `memory_core` service function, build the envelope. No Cypher in `memory_mcp/`.
- Messages are **not** a tool. The runtime appends user and agent messages through `memory_core.history.append_message` so persistence never depends on the LLM.
