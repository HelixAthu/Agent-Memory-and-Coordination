# Spec 02: Cypher queries, retrieval, memory update rules, coordination protocols

- **Purpose:** Defines every Cypher query, the recall algorithm and scoring, fact/procedure/episode update rules, and the handoff, task and shared-state protocols.
- **Read this when:** working on T1, T5, T6, T7, T8, T9.

> **File map note:** section numbers (for example "Section 2.3", "G2", "Q-RECALL") are global across the spec files. `AGENTS.md` has the index that says which file holds which section.

---

## 4. Cypher library (`memory_core/queries.py`)

Rules: each query is a module constant with an id (`Q-...`). Interpolate **only validated ints** (vector dimension, `LIMIT` numbers). Everything else is a parameter. The graph is already chosen by the connection (`mem_<tenant>`), so queries never mention tenants.

### 4.1 Message history (persistent conversation)
```cypher
// Q-SESSION-CREATE
MATCH (u:User {id:$uid})
CREATE (s:Session {id:$sid, user_id:$uid, status:'OPEN', started_at:$ts, current_agent:$agent, msg_count:0})
CREATE (u)-[:HAD_SESSION]->(s)
RETURN s.id AS id

// Q-MSG-APPEND  (atomic: seq is assigned and the node created in ONE write query)
MATCH (s:Session {id:$sid})
SET s.msg_count = s.msg_count + 1
WITH s, s.msg_count AS seq
CREATE (m:Message {id:$mid, session_id:$sid, seq:seq, role:$role, agent_id:$agent, text:$text, ts:$ts})
CREATE (s)-[:HAS_MESSAGE]->(m)
RETURN seq

// Q-MSG-LINK  (run after append when seq > 1; the previous seq always exists because writes are serialized)
MATCH (a:Message {session_id:$sid, seq:$prev}), (b:Message {id:$mid})
MERGE (a)-[:NEXT]->(b)

// Q-MSG-LIST
MATCH (s:Session {id:$sid})-[:HAS_MESSAGE]->(m:Message)
RETURN m.seq AS seq, m.role AS role, m.agent_id AS agent_id, m.text AS text, m.ts AS ts
ORDER BY m.seq DESC LIMIT {LIMIT}
```
`get_messages` reverses the result so it is oldest-first.

### 4.2 Facts (semantic memory)
```cypher
// Q-FACTS-ACTIVE
MATCH (u:User {id:$uid})-[:HAS_FACT]->(f:Fact {status:'ACTIVE'})
RETURN f.id AS id, f.predicate AS predicate, f.object AS object, f.confidence AS confidence, f.valid_from AS valid_from
ORDER BY f.predicate

// Q-FACT-ACTIVE-ONE
MATCH (u:User {id:$uid})-[:HAS_FACT]->(f:Fact {predicate:$pred, status:'ACTIVE'})
RETURN f.id AS id, f.object AS object, f.confidence AS confidence

// Q-FACT-HISTORY
MATCH (u:User {id:$uid})-[:HAS_FACT]->(f:Fact {predicate:$pred})
RETURN f.id AS id, f.object AS object, f.status AS status, f.valid_from AS valid_from, f.valid_to AS valid_to
ORDER BY f.valid_from DESC, f.status ASC

// Q-FACT-REINFORCE  (confidence capped at 1.0; round in Python when returning)
MATCH (f:Fact {id:$fid, status:'ACTIVE'})
SET f.confidence = CASE WHEN f.confidence + 0.05 > 1.0 THEN 1.0 ELSE f.confidence + 0.05 END, f.last_confirmed = $ts
RETURN f.confidence AS confidence

// Q-FACT-CLOSE-OLD  (conditional: returns a row only if the old fact was still ACTIVE)
MATCH (old:Fact {id:$old_id, status:'ACTIVE'})
SET old.status = 'SUPERSEDED', old.valid_to = $ts
RETURN old.id AS id

// Q-FACT-CREATE
MATCH (u:User {id:$uid})
CREATE (f:Fact {id:$fid, predicate:$pred, object:$obj, confidence:$conf, status:'ACTIVE', valid_from:$ts, last_confirmed:$ts, embedding:vecf32($emb)})
CREATE (u)-[:HAS_FACT]->(f)
RETURN f.id AS id

// Q-FACT-LINK-SUPERSEDES
MATCH (n:Fact {id:$new_id}), (o:Fact {id:$old_id}) CREATE (n)-[:SUPERSEDES]->(o)

// Q-FACT-LINK-SOURCE
MATCH (f:Fact {id:$fid}), (s:Session {id:$sid}) CREATE (f)-[:DERIVED_FROM]->(s)
```

### 4.3 Episodes and recall (episodic memory)
```cypher
// Q-EP-VEC  (candidate generation: index first, then filter AFTER yield; vector queries cannot take property filters)
CALL db.idx.vector.queryNodes('Episode', 'embedding', $k, vecf32($qv)) YIELD node
MATCH (u:User {id:$uid})<-[:ABOUT]-(node)
WHERE node.status = 'ACTIVE'
RETURN node.id AS id, node.summary AS summary, node.importance AS importance, node.ts AS ts, node.embedding AS emb

// Q-EP-ENTITIES
MATCH (e:Episode {id:$eid})-[:MENTIONS]->(x:Entity) RETURN x.id AS id

// Q-EP-RELATED  (graph hop: same user's other episodes that share an entity)
MATCH (u:User {id:$uid})<-[:ABOUT]-(o:Episode {status:'ACTIVE'})-[:MENTIONS]->(x:Entity)
WHERE x.id IN $entities AND NOT o.id IN $exclude
RETURN o.id AS id, o.summary AS summary, o.importance AS importance, o.ts AS ts, o.embedding AS emb, collect(DISTINCT x.id) AS via

// Q-EP-CREATE  (consolidation)
MATCH (u:User {id:$uid}), (s:Session {id:$sid})
CREATE (e:Episode {id:$eid, summary:$summary, outcome:$outcome, importance:$imp, ts:$ts, status:'ACTIVE', embedding:vecf32($emb)})
CREATE (e)-[:ABOUT]->(u)
CREATE (s)-[:SUMMARIZED_AS]->(e)
RETURN e.id AS id

// Q-EP-LINK-ENTITIES
MATCH (e:Episode {id:$eid}) UNWIND $ids AS xid MATCH (x:Entity {id:xid}) MERGE (e)-[:MENTIONS]->(x)

// Q-EP-LINK-AGENTS
MATCH (e:Episode {id:$eid}) UNWIND $ids AS aid MATCH (a:Agent {id:aid}) MERGE (e)-[:INVOLVED]->(a)

// Q-DECAY
MATCH (e:Episode {status:'ACTIVE'}) WHERE e.importance < $min_imp AND e.ts < $cutoff
SET e.status = 'ARCHIVED'
RETURN e.id AS id
```
Vector `queryNodes` returns candidates; **do not use its `score`** (its direction depends on the similarity function). Recompute cosine in Python from the returned `emb` (probe F3 confirms the embedding is returned as a list of floats; if not, fetch it with a second query).

### 4.4 Procedures (procedural memory)
```cypher
// Q-PROC-VEC
CALL db.idx.vector.queryNodes('Procedure', 'embedding', $k, vecf32($qv)) YIELD node
WHERE node.status IN $statuses
RETURN node.id AS id, node.name AS name, node.trigger AS trigger, node.steps AS steps, node.status AS status, node.origin AS origin, node.embedding AS emb

// Q-PROC-STATS
MATCH (p:Procedure {id:$pid})
OPTIONAL MATCH (s:Session)-[a:APPLIED]->(p)
RETURN p.id AS id,
       sum(CASE WHEN a.outcome = 'success' THEN 1 ELSE 0 END) AS successes,
       sum(CASE WHEN a.outcome = 'failure' THEN 1 ELSE 0 END) AS failures,
       count(DISTINCT CASE WHEN a.outcome = 'success' THEN s.user_id END) AS success_users

// Q-PROC-OUTCOME
MATCH (s:Session {id:$sid}), (p:Procedure {id:$pid})
MERGE (s)-[a:APPLIED]->(p)
SET a.outcome = $outcome, a.ts = $ts
RETURN p.id AS id

// Q-PROC-PROMOTABLE
MATCH (p:Procedure {status:'CANDIDATE'})
OPTIONAL MATCH (s:Session)-[a:APPLIED {outcome:'success'}]->(p)
WITH p, count(a) AS successes, count(DISTINCT s.user_id) AS users
WHERE successes >= $min_successes AND users >= $min_users
RETURN p.id AS id, successes, users

// Q-PROC-SET-STATUS  (conditional)
MATCH (p:Procedure {id:$pid, status:$from_status}) SET p.status = $to_status RETURN p.id AS id
```
Constants: `PROMOTE_MIN_SUCCESSES = 2`, `PROMOTE_MIN_USERS = 2`, `DEPRECATE_MIN_USES = 5`, `DEPRECATE_BELOW = 0.3`, `DECAY_MIN_IMPORTANCE = 0.2`, `DECAY_MIN_AGE_DAYS = 90`.

### 4.5 Coordination
```cypher
// Q-ROUTE
MATCH (a:Agent {status:'AVAILABLE'})-[:EXPERT_IN]->(e:Entity {id:$topic})
OPTIONAL MATCH (t:Task) WHERE t.status = 'CLAIMED' AND t.claimed_by = a.id
RETURN a.id AS id, a.name AS name, count(t) AS load
ORDER BY load ASC, id ASC

// Q-TASK-CREATE
CREATE (t:Task {id:$id, title:$title, status:'OPEN', priority:$prio, claimed_by:'', version:1, created_at:$ts})
RETURN t.id AS id

// Q-TASK-LINK-USER
MATCH (t:Task {id:$id}), (u:User {id:$uid}) CREATE (t)-[:FOR_USER]->(u)

// Q-TASK-CLAIM  (atomic compare-and-set inside ONE write query)
MATCH (t:Task {id:$id, status:'OPEN'})
SET t.status = 'CLAIMED', t.claimed_by = $agent, t.version = t.version + 1
RETURN t.id AS id, t.version AS version

// Q-TASK-CLAIM-NEXT  (atomic: pick and claim in ONE write query)
MATCH (t:Task {status:'OPEN'})
WITH t ORDER BY t.priority DESC, t.created_at ASC, t.id ASC LIMIT 1
SET t.status = 'CLAIMED', t.claimed_by = $agent, t.version = t.version + 1
RETURN t.id AS id, t.title AS title, t.version AS version

// Q-TASK-DONE
MATCH (t:Task {id:$id, status:'CLAIMED', claimed_by:$agent}) SET t.status = 'DONE', t.version = t.version + 1 RETURN t.id AS id

// Q-STATE-GET
MATCH (:Session {id:$sid})-[:HAS_STATE]->(e:StateEntry {key:$key}) RETURN e.value AS value, e.version AS version

// Q-STATE-CREATE  (relies on the unique constraint on StateEntry.id; a duplicate raises an error, map it to CONFLICT)
MATCH (s:Session {id:$sid})
CREATE (e:StateEntry {id:$eid, key:$key, value:$value, version:1, updated_by:$agent, updated_at:$ts})
CREATE (s)-[:HAS_STATE]->(e)
RETURN e.version AS version

// Q-STATE-CAS
MATCH (e:StateEntry {id:$eid, version:$expected})
SET e.value = $value, e.version = e.version + 1, e.updated_by = $agent, e.updated_at = $ts
RETURN e.version AS version

// Q-HANDOFF-CREATE
MATCH (a:Agent {id:$from}), (b:Agent {id:$to}), (s:Session {id:$sid})
CREATE (h:Handoff {id:$hid, status:'PENDING', reason:$reason, from_agent:$from, to_agent:$to, session_id:$sid, version:1, created_at:$ts})
CREATE (a)-[:HANDED_OFF]->(h)
CREATE (h)-[:TO]->(b)
CREATE (h)-[:FOR_SESSION]->(s)
RETURN h.id AS id

// Q-HANDOFF-CARRY-{FACT|EPISODE|PROCEDURE|MESSAGE}  (one query per label; {LABEL} is whitelisted, never user input)
MATCH (h:Handoff {id:$hid}) UNWIND $ids AS xid MATCH (x:{LABEL} {id:xid}) CREATE (h)-[:CARRIES {kind:$kind}]->(x)

// Q-HANDOFF-BUNDLE
MATCH (h:Handoff {id:$hid})-[c:CARRIES]->(x)
RETURN c.kind AS kind, x.id AS id, x.summary AS summary, x.predicate AS predicate, x.object AS object, x.name AS name, x.text AS text, x.role AS role

// Q-HANDOFF-ACCEPT  (atomic PENDING -> ACCEPTED, only the target agent)
MATCH (h:Handoff {id:$hid, status:'PENDING', to_agent:$agent})
SET h.status = 'ACCEPTED', h.accepted_at = $ts, h.version = h.version + 1
RETURN h.id AS id

// Q-HANDOFF-COMPLETE
MATCH (h:Handoff {id:$hid, status:'ACCEPTED', to_agent:$agent})
SET h.status = 'COMPLETED', h.completed_at = $ts, h.outcome = $outcome, h.summary = $summary, h.version = h.version + 1
RETURN h.id AS id

// Q-HANDOFF-PENDING
MATCH (h:Handoff {status:'PENDING', to_agent:$agent})
RETURN h.id AS id, h.reason AS reason, h.from_agent AS from_agent, h.session_id AS session_id, h.created_at AS created_at
ORDER BY h.created_at

// Q-HANDOFF-READ
MATCH (h:Handoff {id:$hid}) RETURN h.status AS status, h.to_agent AS to_agent, h.session_id AS session_id

// Q-SESSION-SET-AGENT
MATCH (s:Session {id:$sid}) SET s.current_agent = $agent RETURN s.id AS id
```
**Why these are safe under concurrency:** each statement above that changes state does its check (`WHERE status = ...`) and its write inside a single write query. If probe F5 shows that concurrent write queries on one graph are serialized and atomic, only one concurrent caller can match. The service layer turns "zero rows returned" into a typed error (`CONFLICT`, `FORBIDDEN` or `NOT_FOUND`) by reading the current state afterwards (`Q-HANDOFF-READ` etc.).

### 4.6 Graph export for the UI (bounded)
```cypher
// Q-UI-NODES  (per user; exclude embeddings)
MATCH (u:User {id:$uid})
OPTIONAL MATCH (u)-[:HAD_SESSION]->(s:Session)
OPTIONAL MATCH (u)-[:HAS_FACT]->(f:Fact)
OPTIONAL MATCH (e:Episode)-[:ABOUT]->(u)
RETURN u.id AS user, collect(DISTINCT properties(s)) AS sessions, collect(DISTINCT properties(f)) AS facts, collect(DISTINCT properties(e)) AS episodes
```
Strip any `embedding` key in Python before returning. Procedures, entities, agents, handoffs and tasks come from separate small queries (`Q-UI-PROCS`, `Q-UI-ENTITIES`, `Q-UI-AGENTS`, `Q-UI-HANDOFFS`, `Q-UI-TASKS`) and edges from `Q-UI-EDGES` (`MATCH (a)-[r]->(b) WHERE a.id IN $ids AND b.id IN $ids RETURN a.id, type(r), b.id, properties(r)`). Cap at 200 nodes.

---

## 5. Retrieval and memory update rules

### 5.1 Tokenizer and mock embedder (`memory_core/embedder.py`, pure functions)
```
STOPWORDS = {a, an, the, on, in, of, to, for, my, i, me, is, was, it, and, or, about, with, by, at, as, be, are, were, this, that, her, his, she, he, you, your, we, they, their, has, have, had, from, am}
tokens(text): lowercase; split on any non-alphanumeric character; drop empty tokens and stopwords.
stem(w): for suf in ("ing","ed","es","s"): if w ends with suf and len(w)-len(suf) >= 3: w = w[:-len(suf)]; break
         then: if w ends with "e" and len(w) > 3: w = w[:-1]
mock_embed(text): vec = [0.0]*EMBED_DIM; for each stemmed token: vec[int(md5(stem).hexdigest(), 16) % EMBED_DIM] += 1.0; L2-normalize (zero vector stays zero).
cosine(a, b): dot(a, b) / (|a| * |b|), 0.0 if either norm is 0; clamp to [0, 1].
```
Examples: `stem("charged") == "charg"`, `stem("charge") == "charg"`, `stem("invoice") == "invoic"`, `stem("billing") == "bill"`, `stem("refunded") == "refund"`, `stem("duplicate") == "duplicat"`. Entity `keywords` are matched against the stems of a text's tokens.

### 5.2 Recall algorithm (`memory_core/recall.py`)
Input: `user_id, query, k=3, now`. Steps:
1. `qv = embed(query)`.
2. **Episodes:** run `Q-EP-VEC` with `$k = k * 5`. Compute `sim = cosine(qv, emb)` in Python for each row.
3. Let `top1` = the candidate with the highest `sim`. Fetch its entities with `Q-EP-ENTITIES`. Run `Q-EP-RELATED` with `$entities` and `$exclude = ids already seen` to add graph-hop candidates; compute their `sim` in Python too. Candidates added by this hop and `top1`'s sharing partners get `boost = 1`; `top1` and everything else gets `boost = 0`.
4. Score each episode:
```
age_days  = max(0, (now - ts) / 86400)
recency   = 0.5 ** (age_days / 14)
score     = 0.65*sim + 0.10*recency + 0.15*importance + 0.10*boost
```
Return the top `k` by score (ties: higher `ts` first), each with `{id, summary, score, components:{sim, recency, importance, boost}, via}` (`via` = shared entities, empty if none).
5. **Facts:** `Q-FACTS-ACTIVE` (all ACTIVE facts of the user, max 10, ordered by confidence desc then predicate).
6. **Procedures:** `Q-PROC-VEC` with `statuses=['ACTIVE']`, `$k = 5`; for each compute `sim` in Python and `conf = (successes + 1) / (successes + failures + 2)` from `Q-PROC-STATS`; `pscore = 0.7*sim + 0.3*conf`; return the top 2 with `pscore > 0` (drop items with `sim == 0`).
7. Return `{episodes, facts, procedures}`. The recall result must never include another user's episodes or facts.
8. The `visit` for the MCP envelope lists the node ids returned and edge keys among them (for UI highlighting).

`find_procedure(situation, include_candidates=True)` uses the same procedure scoring with `statuses=['ACTIVE','CANDIDATE']`; ACTIVE items get `+0.1` to `pscore`; each result includes its `status`, `successes`, `failures`.

### 5.3 Fact update (`memory_core/semantic.py: remember_fact`)
Input: `user_id, predicate, object, confidence=0.8, session_id`. Validate the predicate against the registry.
```
loop up to 3 times:
  active = Q-FACT-ACTIVE-ONE(user, predicate)
  if active exists and active.object == object (case-insensitive):
      Q-FACT-REINFORCE -> return {action:'reinforced', fact_id}
  if active exists:
      closed = Q-FACT-CLOSE-OLD(active.id)        # conditional write
      if closed is empty: continue                # someone else changed it; re-read and retry
  create Q-FACT-CREATE (new id 'fact-' + uuid hex[:8], embedding of "<predicate> <object>")
  if active existed: Q-FACT-LINK-SUPERSEDES(new, active.id)
  Q-FACT-LINK-SOURCE(new, session_id)
  return {action: 'superseded' if active existed else 'created', fact_id, old_fact_id?}
after 3 failed loops: raise CONFLICT
```
`object` is stored with first letter capitalized for `city` and `plan` and lower-cased for `prefers_channel`.

### 5.4 Consolidation (`memory_core/consolidation.py: close_session`)
Input: `session_id, outcome ('resolved'|'escalated'|'abandoned'), summary?`. Steps:
1. Load messages and the session. Refuse if the session is already CLOSED (`CONFLICT`).
2. `summary`: use the supplied one if non-empty, else template `"<User name>: <first user message text>. Outcome: <outcome>."`.
3. Entities: for every message, stem its tokens; an `Entity` matches if any of its `keywords` is among the stems. The set of matched ids = `MENTIONS`.
4. Agents involved: distinct `agent_id` values of agent-role messages.
5. Importance: `0.6` if outcome is `resolved`, `0.4` if `escalated`, `0.2` if `abandoned`; `+0.2` if a handoff exists for the session; `+0.1` if any fact was created or superseded in this session; capped at `1.0` (round to 2 decimals).
6. Create the Episode with id `ep-<session_id>` (`Q-EP-CREATE`, `Q-EP-LINK-ENTITIES`, `Q-EP-LINK-AGENTS`).
7. Rule-based fact extraction over **user** messages (lowercased), calling `remember_fact`: `i prefer (email|phone|chat)` gives `prefers_channel`; `moved to ([a-z]+)` gives `city`; `plan is ([a-z]+)` gives `plan`. **Skip** a rule hit if an ACTIVE fact with the same predicate and object already has `DERIVED_FROM` this session.
8. `promote_procedures()` (Section 5.5).
9. Mark the session CLOSED (`ended_at`, `outcome`). Return `{episode_id, importance, facts_changed:[...], promoted:[...]}`.

### 5.5 Procedural learning (`memory_core/procedural.py`)
- `record_outcome(session_id, procedure_id, outcome)`: `Q-PROC-OUTCOME`.
- `promote_procedures()`: run `Q-PROC-PROMOTABLE` with the constants; for each result run `Q-PROC-SET-STATUS` (`CANDIDATE` to `ACTIVE`); return the ids that actually changed.
- `deprecate_procedures()`: for each ACTIVE procedure with `origin='learned'` and `successes + failures >= 5` and `(successes+1)/(successes+failures+2) < 0.3`, set status `DEPRECATED`. (Pure function `should_deprecate(successes, failures)` is unit-tested.)
- `decay(now)`: `Q-DECAY` with `min_imp=0.2`, `cutoff = now - 90*86400`; return archived ids.

---

## 6. Coordination protocols

### 6.1 Handoff (`memory_core/coordination.py`)
`create_handoff(session_id, from_agent, to_agent, reason, now)`:
1. Validate both agents exist, `from != to`, session is OPEN and belongs to the caller's user.
2. `query_text` = text of the last **user** message in the session (fallback: `reason`).
3. Bundle: all ACTIVE facts of the user; top-2 episodes from `recall(user, query_text, k=2)`; top-1 procedure from `recall`; the last 6 messages of the session.
4. `Q-HANDOFF-CREATE`, then one `Q-HANDOFF-CARRY-*` per kind (`kind` = `fact|episode|procedure|message`).
5. Return `{handoff_id, carries:{fact:n, episode:n, procedure:n, message:n}, carries_total}`.

`accept_handoff(handoff_id, agent_id)`: run `Q-HANDOFF-ACCEPT`. If no row: read `Q-HANDOFF-READ`; not found gives `NOT_FOUND`; `to_agent != agent_id` gives `FORBIDDEN`; status not PENDING gives `CONFLICT`. On success also run `Q-SESSION-SET-AGENT` (the specialist becomes the session's current agent) and return the bundle (`Q-HANDOFF-BUNDLE`).

`complete_handoff(handoff_id, agent_id, outcome, summary)`: `Q-HANDOFF-COMPLETE`; same error mapping (status not ACCEPTED gives `CONFLICT`).

### 6.2 Tasks
`create_task(title, priority, user_id?)`, `claim_task(task_id, agent_id)`, `claim_next(agent_id)`, `complete_task(task_id, agent_id)`. A claim that returns zero rows becomes `CONFLICT` (task exists but not OPEN) or `NOT_FOUND` (no such task, or for `claim_next` no OPEN tasks). `task.created_at` is epoch **milliseconds**; ids for new tasks are `task-` + uuid hex[:8] unless given.

### 6.3 Shared state (optimistic concurrency)
`get_state(session_id, key)` returns `{value, version}` or `NOT_FOUND`. `set_state(session_id, key, value, expected_version, agent_id)`:
- `expected_version == 0`: `Q-STATE-CREATE` with `eid = "st-<session_id>-<key>"`; a unique-constraint violation (or any "already exists" error) becomes `CONFLICT` with `current_version` read via `Q-STATE-GET`.
- `expected_version >= 1`: `Q-STATE-CAS`; zero rows becomes `CONFLICT` with `current_version`.
`key` must match `^[a-z][a-z0-9_]{0,31}$`; `value` is a string up to 2000 chars.

### 6.4 Routing
`route(topic_id)` runs `Q-ROUTE` (load-aware: fewest currently CLAIMED tasks first, id as tiebreak). Return `NOT_FOUND` if the entity does not exist or is not an `Entity` with `type='topic'`.

### 6.5 Fallbacks (use only if the probe says so; log the decision in `DECISIONS.md`)
- **F5 fails** (concurrent write queries are not atomic per query): wrap every conditional write in a per-tenant lock. Use `redis.asyncio` (installed with the falkordb dependency; no new package) with `SET lock:<tenant> <token> NX PX 5000` and retry with a 5 ms backoff, plus an in-process `asyncio.Lock` per tenant. Apply the lock inside `TenantDB.run_rw_conditional(...)` only. Mention this prominently in the README.
- **F7 fails** (unique constraints unsupported): for `Q-STATE-CREATE` use `MERGE (e:StateEntry {id:$eid}) ON CREATE SET e.value=$value, e.version=1, e.updated_by=$agent, e.updated_at=$ts` and treat the call as created only if the returned version is 1 and the returned value equals the requested value.
- **F3 fails** (vector index missing or embedding not returned): candidates come from `db.idx.fulltext.queryNodes('Episode', $text)` with the Episode summary indexed, and `emb` is fetched by a second query. Recall's graph hop and scoring stay the same.
