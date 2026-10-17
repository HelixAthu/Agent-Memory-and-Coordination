# Cypher Query Catalog & Reference

This document provides the reference manual for every Cypher query executed by the **SwarmGraph Memory Fabric** against FalkorDB.

---

## 1. Architectural & Execution Principles

1. **Per-Tenant Graph Isolation**: Queries are executed directly against a dedicated database key (`mem_<tenant>`). No cross-tenant data can ever be read or written within a Cypher query.
2. **Strict Parameterization**: All query values (identifiers, text, timestamps, embeddings) are passed strictly as query parameters (`$param`), preventing Cypher injection.
3. **Atomic State Transitions**: Status transitions, sequences, claims, and counters are performed in single Cypher write transactions using optimistic concurrency / compare-and-set semantics.
4. **Hybrid Retrieval**: Vector indexes (`CALL db.idx.vector.queryNodes`) yield candidate nodes, followed immediately by graph traversal hops (`[:ABOUT]`, `[:MENTIONS]`) to pull relevant contextual memory.

---

## 2. Conversation History & Sessions

### `Q-SESSION-CREATE`
Creates an open agent session for a user and links it to the User node.

* **Parameters:**
  * `$uid` (`string`): User identifier (e.g. `"user-priya"`)
  * `$sid` (`string`): New session identifier (e.g. `"sess-demo-continuity"`)
  * `$ts` (`int`): Timestamp in epoch seconds
  * `$agent` (`string`): Initial active agent ID (e.g. `"agent-triage"`)

```cypher
MATCH (u:User {id:$uid})
CREATE (s:Session {id:$sid, user_id:$uid, status:'OPEN', started_at:$ts, current_agent:$agent, msg_count:0})
CREATE (u)-[:HAD_SESSION]->(s)
RETURN s.id AS id
```

* **Golden Output (`mem_acme`):**
```json
[{"id": "sess-demo-continuity"}]
```

---

### `Q-MSG-APPEND`
Atomically assigns the next sequence number and creates a Message node linked to the session in a single write operation.

* **Parameters:**
  * `$sid` (`string`): Session ID
  * `$mid` (`string`): Unique message ID
  * `$role` (`string`): `"user"` or `"agent"`
  * `$agent` (`string`): Agent ID or `""` for user messages
  * `$text` (`string`): Message body text
  * `$ts` (`int`): Epoch timestamp

```cypher
MATCH (s:Session {id:$sid})
SET s.msg_count = s.msg_count + 1
WITH s, s.msg_count AS seq
CREATE (m:Message {id:$mid, session_id:$sid, seq:seq, role:$role, agent_id:$agent, text:$text, ts:$ts})
CREATE (s)-[:HAS_MESSAGE]->(m)
RETURN seq
```

* **Golden Output (`mem_acme`):**
```json
[{"seq": 1}]
```

---

### `Q-MSG-LINK`
Links consecutive messages using the `[:NEXT]` relationship to form a persistent conversation chain.

* **Parameters:**
  * `$sid` (`string`): Session ID
  * `$prev` (`int`): Previous message sequence number
  * `$mid` (`string`): Current message ID

```cypher
MATCH (a:Message {session_id:$sid, seq:$prev}), (b:Message {id:$mid})
MERGE (a)-[:NEXT]->(b)
```

---

### `Q-MSG-LIST`
Fetches conversation history in descending sequence order with a parameterized limit.

* **Parameters:**
  * `$sid` (`string`): Session ID
  * `{LIMIT}` (interpolated integer): Number of recent messages to return

```cypher
MATCH (s:Session {id:$sid})-[:HAS_MESSAGE]->(m:Message)
RETURN m.seq AS seq, m.role AS role, m.agent_id AS agent_id, m.text AS text, m.ts AS ts
ORDER BY m.seq DESC LIMIT {LIMIT}
```

* **Golden Output (`sess-p1`, limit 4):**
```json
[
  {"seq": 4, "role": "user", "agent_id": "", "text": "Thanks, that fixed it.", "ts": 1786526400},
  {"seq": 3, "role": "agent", "agent_id": "agent-billing", "text": "I see the duplicate charge and issued a refund for the extra payment.", "ts": 1786525800},
  {"seq": 2, "role": "agent", "agent_id": "agent-triage", "text": "Sorry about that, I am bringing in Billing.", "ts": 1786525260},
  {"seq": 1, "role": "user", "agent_id": "", "text": "I was charged twice for invoice INV-1042.", "ts": 1786525200}
]
```

---

## 3. Semantic Memory & Facts

### `Q-FACTS-ACTIVE`
Returns all current active facts for a user.

* **Parameters:**
  * `$uid` (`string`): User ID

```cypher
MATCH (u:User {id:$uid})-[:HAS_FACT]->(f:Fact {status:'ACTIVE'})
RETURN f.id AS id, f.predicate AS predicate, f.object AS object, f.confidence AS confidence, f.valid_from AS valid_from
ORDER BY f.predicate
```

* **Golden Output (`user-priya`):**
```json
[
  {"id": "fact-p-city", "predicate": "city", "object": "Mumbai", "confidence": 0.7, "valid_from": 1786525200},
  {"id": "fact-p-plan", "predicate": "plan", "object": "Pro", "confidence": 0.9, "valid_from": 1786525200},
  {"id": "fact-p-channel", "predicate": "prefers_channel", "object": "email", "confidence": 0.8, "valid_from": 1786525200}
]
```

---

### `Q-FACT-HISTORY`
Retrieves the full temporal audit trail and supersession chain for a given user predicate.

* **Parameters:**
  * `$uid` (`string`): User ID
  * `$pred` (`string`): Predicate name (e.g. `"prefers_channel"`)

```cypher
MATCH (u:User {id:$uid})-[:HAS_FACT]->(f:Fact {predicate:$pred})
RETURN f.id AS id, f.object AS object, f.status AS status, f.valid_from AS valid_from, f.valid_to AS valid_to
ORDER BY f.valid_from DESC, f.status ASC
```

* **Golden Output (`user-priya`, `prefers_channel`):**
```json
[
  {"id": "fact-p-channel", "object": "email", "status": "ACTIVE", "valid_from": 1786525200, "valid_to": null},
  {"id": "fact-p-channel-old", "object": "phone", "status": "SUPERSEDED", "valid_from": 1780272000, "valid_to": 1786525200}
]
```

---

### `Q-FACT-REINFORCE`
Reinforces an existing active fact by increasing its confidence (+0.05, capped at 1.0) and updating `last_confirmed`.

* **Parameters:**
  * `$fid` (`string`): Fact ID
  * `$ts` (`int`): Timestamp

```cypher
MATCH (f:Fact {id:$fid, status:'ACTIVE'})
SET f.confidence = CASE WHEN f.confidence + 0.05 > 1.0 THEN 1.0 ELSE f.confidence + 0.05 END, f.last_confirmed = $ts
RETURN f.confidence AS confidence
```

---

### `Q-FACT-CLOSE-OLD`
Marks an active fact as SUPERSEDED with `valid_to` set to current timestamp.

* **Parameters:**
  * `$old_id` (`string`): Existing fact ID
  * `$ts` (`int`): Timestamp

```cypher
MATCH (old:Fact {id:$old_id, status:'ACTIVE'})
SET old.status = 'SUPERSEDED', old.valid_to = $ts
RETURN old.id AS id
```

---

### `Q-FACT-CREATE`
Creates a new active fact with vector embedding and links it to the user.

* **Parameters:**
  * `$uid` (`string`): User ID
  * `$fid` (`string`): Fact ID
  * `$pred` (`string`): Predicate
  * `$obj` (`string`): Object
  * `$conf` (`float`): Confidence score
  * `$ts` (`int`): Epoch timestamp
  * `$emb` (`list[float]`): Float vector array (dim=4096)

```cypher
MATCH (u:User {id:$uid})
CREATE (f:Fact {id:$fid, predicate:$pred, object:$obj, confidence:$conf, status:'ACTIVE', valid_from:$ts, last_confirmed:$ts, embedding:vecf32($emb)})
CREATE (u)-[:HAS_FACT]->(f)
RETURN f.id AS id
```

---

### `Q-FACT-LINK-SUPERSEDES`
Creates a `[:SUPERSEDES]` relationship directed from the new Fact to the old Fact.

```cypher
MATCH (n:Fact {id:$new_id}), (o:Fact {id:$old_id}) CREATE (n)-[:SUPERSEDES]->(o)
```

---

## 4. Episodic Memory & Hybrid Retrieval

### `Q-EP-VEC` (Candidate Generation)
Uses the FalkorDB HNSW vector index on `Episode.embedding` to find k-nearest candidates, then filters by `[:ABOUT]` user and `status = 'ACTIVE'`.

* **Parameters:**
  * `$k` (`int`): Number of vector candidates
  * `$qv` (`list[float]`): Query embedding vector
  * `$uid` (`string`): Target User ID

```cypher
CALL db.idx.vector.queryNodes('Episode', 'embedding', $k, vecf32($qv)) YIELD node
MATCH (u:User {id:$uid})<-[:ABOUT]-(node)
WHERE node.status = 'ACTIVE'
RETURN node.id AS id, node.summary AS summary, node.importance AS importance, node.ts AS ts, node.embedding AS emb
```

---

### `Q-EP-ENTITIES`
Extracts all Entity nodes mentioned by a specific episode.

* **Parameters:**
  * `$eid` (`string`): Episode ID

```cypher
MATCH (e:Episode {id:$eid})-[:MENTIONS]->(x:Entity) RETURN x.id AS id
```

* **Golden Output (`ep-p1`):**
```json
[
  {"id": "topic-billing"},
  {"id": "topic-refunds"},
  {"id": "invoice-inv-1042"}
]
```

---

### `Q-EP-RELATED` (Graph Hop Discovery)
Follows shared entity relationships to discover related episodes for the same user that the vector search may have ranked lower or missed.

* **Parameters:**
  * `$uid` (`string`): User ID
  * `$entities` (`list[string]`): Entity IDs gathered from candidate episodes
  * `$exclude` (`list[string]`): Episode IDs already retrieved

```cypher
MATCH (u:User {id:$uid})<-[:ABOUT]-(o:Episode {status:'ACTIVE'})-[:MENTIONS]->(x:Entity)
WHERE x.id IN $entities AND NOT o.id IN $exclude
RETURN o.id AS id, o.summary AS summary, o.importance AS importance, o.ts AS ts, o.embedding AS emb, collect(DISTINCT x.id) AS via
```

* **Golden Output (`user-priya`, via `invoice-inv-1042`):**
```json
[
  {
    "id": "ep-p3",
    "summary": "Priya asked about a late fee on invoice INV-1042; Billing explained the fee policy; resolved.",
    "importance": 0.6,
    "via": ["invoice-inv-1042"]
  }
]
```

---

### `Q-DECAY`
Archives stale, low-importance episodes whose age exceeds the cutoff threshold (importance < 0.2, age > 90 days).

* **Parameters:**
  * `$min_imp` (`float`): Minimum importance threshold (0.2)
  * `$cutoff` (`int`): Epoch cutoff timestamp (now - 90 days)

```cypher
MATCH (e:Episode {status:'ACTIVE'}) WHERE e.importance < $min_imp AND e.ts < $cutoff
SET e.status = 'ARCHIVED'
RETURN e.id AS id
```

* **Golden Output (`mem_acme` at frozen time `2026-10-16`):**
```json
[{"id": "ep-r2"}]
```

---

## 5. Procedural Memory

### `Q-PROC-VEC`
Retrieves procedure candidates using vector search filtered by allowable status (`['ACTIVE']` for general recall, `['ACTIVE', 'CANDIDATE']` for tool lookups).

* **Parameters:**
  * `$k` (`int`): Number of candidates
  * `$qv` (`list[float]`): Query embedding vector
  * `$statuses` (`list[string]`): Status filter list

```cypher
CALL db.idx.vector.queryNodes('Procedure', 'embedding', $k, vecf32($qv)) YIELD node
WHERE node.status IN $statuses
RETURN node.id AS id, node.name AS name, node.trigger AS trigger, node.steps AS steps, node.status AS status, node.origin AS origin, node.embedding AS emb
```

---

### `Q-PROC-PROMOTABLE`
Evaluates candidate procedures against promotion criteria: minimum 2 successful applications across at least 2 distinct users.

* **Parameters:**
  * `$min_successes` (`int`): 2
  * `$min_users` (`int`): 2

```cypher
MATCH (p:Procedure {status:'CANDIDATE'})
OPTIONAL MATCH (s:Session)-[a:APPLIED {outcome:'success'}]->(p)
WITH p, count(a) AS successes, count(DISTINCT s.user_id) AS users
WHERE successes >= $min_successes AND users >= $min_users
RETURN p.id AS id, successes, users
```

* **Golden Output (after Rahul's successful VPN session):**
```json
[{"id": "proc-vpn-token-reset", "successes": 2, "users": 2}]
```

---

## 6. Coordination, Routing, Tasks & Shared State

### `Q-ROUTE`
Finds eligible specialists for a topic entity, ordered by their active task load and agent ID.

* **Parameters:**
  * `$topic` (`string`): Entity topic ID (e.g. `"topic-billing"`)

```cypher
MATCH (a:Agent {status:'AVAILABLE'})-[:EXPERT_IN]->(e:Entity {id:$topic})
OPTIONAL MATCH (t:Task) WHERE t.status = 'CLAIMED' AND t.claimed_by = a.id
RETURN a.id AS id, a.name AS name, count(t) AS load
ORDER BY load ASC, id ASC
```

* **Golden Output (`topic-billing`):**
```json
[{"id": "agent-billing", "name": "Billing Agent", "load": 0}]
```

---

### `Q-TASK-CLAIM` (Atomic Claim by ID)
Atomically transitions an OPEN task to CLAIMED in a single atomic transaction.

* **Parameters:**
  * `$id` (`string`): Task ID
  * `$agent` (`string`): Claiming Agent ID

```cypher
MATCH (t:Task {id:$id, status:'OPEN'})
SET t.status = 'CLAIMED', t.claimed_by = $agent, t.version = t.version + 1
RETURN t.id AS id, t.version AS version
```

---

### `Q-TASK-CLAIM-NEXT` (Work-Stealing Priority Queue)
Atomically selects and claims the highest-priority open task in a single write operation.

* **Parameters:**
  * `$agent` (`string`): Claiming Agent ID

```cypher
MATCH (t:Task {status:'OPEN'})
WITH t ORDER BY t.priority DESC, t.created_at ASC, t.id ASC LIMIT 1
SET t.status = 'CLAIMED', t.claimed_by = $agent, t.version = t.version + 1
RETURN t.id AS id, t.title AS title, t.version AS version
```

---

### `Q-STATE-CAS` (Optimistic Concurrency State Update)
Performs a Compare-And-Set write on shared session state, failing safely if the version has changed.

* **Parameters:**
  * `$eid` (`string`): State entry ID (`<session_id>:<key>`)
  * `$expected` (`int`): Expected current version
  * `$value` (`string`): New value
  * `$agent` (`string`): Updating agent ID
  * `$ts` (`int`): Timestamp

```cypher
MATCH (e:StateEntry {id:$eid, version:$expected})
SET e.value = $value, e.version = e.version + 1, e.updated_by = $agent, e.updated_at = $ts
RETURN e.version AS version
```

---

### `Q-HANDOFF-CREATE` & `Q-HANDOFF-ACCEPT`
State machine transitions for agent handoffs: PENDING -> ACCEPTED -> COMPLETED with bundled context items.

```cypher
// Create Handoff
MATCH (a:Agent {id:$from}), (b:Agent {id:$to}), (s:Session {id:$sid})
CREATE (h:Handoff {id:$hid, status:'PENDING', reason:$reason, from_agent:$from, to_agent:$to, session_id:$sid, version:1, created_at:$ts})
CREATE (a)-[:HANDED_OFF]->(h)
CREATE (h)-[:TO]->(b)
CREATE (h)-[:FOR_SESSION]->(s)
RETURN h.id AS id

// Accept Handoff (Atomic)
MATCH (h:Handoff {id:$hid, status:'PENDING', to_agent:$agent})
SET h.status = 'ACCEPTED', h.accepted_at = $ts, h.version = h.version + 1
RETURN h.id AS id
```

* **Golden Output (`sess-demo-continuity`):**
Carries exactly 8 bundle items: 3 facts, 2 episodes, 1 procedure, 2 session messages. Exactly 1 agent can accept; concurrent accepts produce `CONFLICT`.
