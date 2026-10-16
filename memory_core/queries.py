"""Central Cypher query catalog defining all parameterized graph operations."""

from __future__ import annotations

# 4.1 Message history (persistent conversation)
Q_SESSION_CREATE: str = """
MATCH (u:User {id:$uid})
CREATE (s:Session {id:$sid, user_id:$uid, status:'OPEN', started_at:$ts, current_agent:$agent, msg_count:0})
CREATE (u)-[:HAD_SESSION]->(s)
RETURN s.id AS id
"""

Q_MSG_APPEND: str = """
MATCH (s:Session {id:$sid})
SET s.msg_count = s.msg_count + 1
WITH s, s.msg_count AS seq
CREATE (m:Message {id:$mid, session_id:$sid, seq:seq, role:$role, agent_id:$agent, text:$text, ts:$ts})
CREATE (s)-[:HAS_MESSAGE]->(m)
RETURN seq
"""

Q_MSG_LINK: str = """
MATCH (a:Message {session_id:$sid, seq:$prev}), (b:Message {id:$mid})
MERGE (a)-[:NEXT]->(b)
"""

Q_MSG_LIST: str = """
MATCH (s:Session {id:$sid})-[:HAS_MESSAGE]->(m:Message)
RETURN m.seq AS seq, m.role AS role, m.agent_id AS agent_id, m.text AS text, m.ts AS ts
ORDER BY m.seq DESC LIMIT {LIMIT}
"""

# 4.2 Facts (semantic memory)
Q_FACTS_ACTIVE: str = """
MATCH (u:User {id:$uid})-[:HAS_FACT]->(f:Fact {status:'ACTIVE'})
RETURN f.id AS id, f.predicate AS predicate, f.object AS object, f.confidence AS confidence, f.valid_from AS valid_from
ORDER BY f.predicate
"""

Q_FACT_ACTIVE_ONE: str = """
MATCH (u:User {id:$uid})-[:HAS_FACT]->(f:Fact {predicate:$pred, status:'ACTIVE'})
RETURN f.id AS id, f.object AS object, f.confidence AS confidence
"""

Q_FACT_HISTORY: str = """
MATCH (u:User {id:$uid})-[:HAS_FACT]->(f:Fact {predicate:$pred})
RETURN f.id AS id, f.object AS object, f.status AS status, f.valid_from AS valid_from, f.valid_to AS valid_to
ORDER BY f.valid_from DESC, f.status ASC
"""

Q_FACT_REINFORCE: str = """
MATCH (f:Fact {id:$fid, status:'ACTIVE'})
SET f.confidence = CASE WHEN f.confidence + 0.05 > 1.0 THEN 1.0 ELSE f.confidence + 0.05 END, f.last_confirmed = $ts
RETURN f.confidence AS confidence
"""

Q_FACT_CLOSE_OLD: str = """
MATCH (old:Fact {id:$old_id, status:'ACTIVE'})
SET old.status = 'SUPERSEDED', old.valid_to = $ts
RETURN old.id AS id
"""

Q_FACT_CREATE: str = """
MATCH (u:User {id:$uid})
CREATE (f:Fact {id:$fid, predicate:$pred, object:$obj, confidence:$conf, status:'ACTIVE', valid_from:$ts, last_confirmed:$ts, embedding:vecf32($emb)})
CREATE (u)-[:HAS_FACT]->(f)
RETURN f.id AS id
"""

Q_FACT_LINK_SUPERSEDES: str = """
MATCH (n:Fact {id:$new_id}), (o:Fact {id:$old_id}) CREATE (n)-[:SUPERSEDES]->(o)
"""

Q_FACT_LINK_SOURCE: str = """
MATCH (f:Fact {id:$fid}), (s:Session {id:$sid}) CREATE (f)-[:DERIVED_FROM]->(s)
"""

# 4.3 Episodes and recall (episodic memory)
Q_EP_VEC: str = """
CALL db.idx.vector.queryNodes('Episode', 'embedding', $k, vecf32($qv)) YIELD node
MATCH (u:User {id:$uid})<-[:ABOUT]-(node)
WHERE node.status = 'ACTIVE'
RETURN node.id AS id, node.summary AS summary, node.importance AS importance, node.ts AS ts, node.embedding AS emb
"""

Q_EP_ENTITIES: str = """
MATCH (e:Episode {id:$eid})-[:MENTIONS]->(x:Entity) RETURN x.id AS id
"""

Q_EP_RELATED: str = """
MATCH (u:User {id:$uid})<-[:ABOUT]-(o:Episode {status:'ACTIVE'})-[:MENTIONS]->(x:Entity)
WHERE x.id IN $entities AND NOT o.id IN $exclude
RETURN o.id AS id, o.summary AS summary, o.importance AS importance, o.ts AS ts, o.embedding AS emb, collect(DISTINCT x.id) AS via
"""

Q_EP_CREATE: str = """
MATCH (u:User {id:$uid}), (s:Session {id:$sid})
CREATE (e:Episode {id:$eid, summary:$summary, outcome:$outcome, importance:$imp, ts:$ts, status:'ACTIVE', embedding:vecf32($emb)})
CREATE (e)-[:ABOUT]->(u)
CREATE (s)-[:SUMMARIZED_AS]->(e)
RETURN e.id AS id
"""

Q_EP_LINK_ENTITIES: str = """
MATCH (e:Episode {id:$eid}) UNWIND $ids AS xid MATCH (x:Entity {id:xid}) MERGE (e)-[:MENTIONS]->(x)
"""

Q_EP_LINK_AGENTS: str = """
MATCH (e:Episode {id:$eid}) UNWIND $ids AS aid MATCH (a:Agent {id:aid}) MERGE (e)-[:INVOLVED]->(a)
"""

Q_DECAY: str = """
MATCH (e:Episode {status:'ACTIVE'}) WHERE e.importance < $min_imp AND e.ts < $cutoff
SET e.status = 'ARCHIVED'
RETURN e.id AS id
"""

# 4.4 Procedures (procedural memory)
Q_PROC_VEC: str = """
CALL db.idx.vector.queryNodes('Procedure', 'embedding', $k, vecf32($qv)) YIELD node
WHERE node.status IN $statuses
RETURN node.id AS id, node.name AS name, node.trigger AS trigger, node.steps AS steps, node.status AS status, node.origin AS origin, node.embedding AS emb
"""

Q_PROC_STATS: str = """
MATCH (p:Procedure {id:$pid})
OPTIONAL MATCH (s:Session)-[a:APPLIED]->(p)
RETURN p.id AS id,
       sum(CASE WHEN a.outcome = 'success' THEN 1 ELSE 0 END) AS successes,
       sum(CASE WHEN a.outcome = 'failure' THEN 1 ELSE 0 END) AS failures,
       count(DISTINCT CASE WHEN a.outcome = 'success' THEN s.user_id END) AS success_users
"""

Q_PROC_OUTCOME: str = """
MATCH (s:Session {id:$sid}), (p:Procedure {id:$pid})
MERGE (s)-[a:APPLIED]->(p)
SET a.outcome = $outcome, a.ts = $ts
RETURN p.id AS id
"""

Q_PROC_PROMOTABLE: str = """
MATCH (p:Procedure {status:'CANDIDATE'})
OPTIONAL MATCH (s:Session)-[a:APPLIED {outcome:'success'}]->(p)
WITH p, count(a) AS successes, count(DISTINCT s.user_id) AS users
WHERE successes >= $min_successes AND users >= $min_users
RETURN p.id AS id, successes, users
"""

Q_PROC_SET_STATUS: str = """
MATCH (p:Procedure {id:$pid, status:$from_status}) SET p.status = $to_status RETURN p.id AS id
"""

# 4.5 Coordination
Q_ROUTE: str = """
MATCH (a:Agent {status:'AVAILABLE'})-[:EXPERT_IN]->(e:Entity {id:$topic})
OPTIONAL MATCH (t:Task) WHERE t.status = 'CLAIMED' AND t.claimed_by = a.id
RETURN a.id AS id, a.name AS name, count(t) AS load
ORDER BY load ASC, id ASC
"""

Q_TASK_CREATE: str = """
CREATE (t:Task {id:$id, title:$title, status:'OPEN', priority:$prio, claimed_by:'', version:1, created_at:$ts})
RETURN t.id AS id
"""

Q_TASK_LINK_USER: str = """
MATCH (t:Task {id:$id}), (u:User {id:$uid}) CREATE (t)-[:FOR_USER]->(u)
"""

Q_TASK_CLAIM: str = """
MATCH (t:Task {id:$id, status:'OPEN'})
SET t.status = 'CLAIMED', t.claimed_by = $agent, t.version = t.version + 1
RETURN t.id AS id, t.version AS version
"""

Q_TASK_CLAIM_NEXT: str = """
MATCH (t:Task {status:'OPEN'})
WITH t ORDER BY t.priority DESC, t.created_at ASC, t.id ASC LIMIT 1
SET t.status = 'CLAIMED', t.claimed_by = $agent, t.version = t.version + 1
RETURN t.id AS id, t.title AS title, t.version AS version
"""

Q_TASK_DONE: str = """
MATCH (t:Task {id:$id, status:'CLAIMED', claimed_by:$agent}) SET t.status = 'DONE', t.version = t.version + 1 RETURN t.id AS id
"""

Q_STATE_GET: str = """
MATCH (:Session {id:$sid})-[:HAS_STATE]->(e:StateEntry {key:$key}) RETURN e.value AS value, e.version AS version
"""

# Unique constraint fallback: MERGE ON CREATE
Q_STATE_CREATE: str = """
MATCH (s:Session {id:$sid})
MERGE (e:StateEntry {id:$eid})
ON CREATE SET e.key=$key, e.value=$value, e.version=1, e.updated_by=$agent, e.updated_at=$ts
CREATE (s)-[:HAS_STATE]->(e)
RETURN e.version AS version, e.value AS value
"""

Q_STATE_CAS: str = """
MATCH (e:StateEntry {id:$eid, version:$expected})
SET e.value = $value, e.version = e.version + 1, e.updated_by = $agent, e.updated_at = $ts
RETURN e.version AS version
"""

Q_HANDOFF_CREATE: str = """
MATCH (a:Agent {id:$from}), (b:Agent {id:$to}), (s:Session {id:$sid})
CREATE (h:Handoff {id:$hid, status:'PENDING', reason:$reason, from_agent:$from, to_agent:$to, session_id:$sid, version:1, created_at:$ts})
CREATE (a)-[:HANDED_OFF]->(h)
CREATE (h)-[:TO]->(b)
CREATE (h)-[:FOR_SESSION]->(s)
RETURN h.id AS id
"""

Q_HANDOFF_BUNDLE: str = """
MATCH (h:Handoff {id:$hid})-[c:CARRIES]->(x)
RETURN c.kind AS kind, x.id AS id, x.summary AS summary, x.predicate AS predicate, x.object AS object, x.name AS name, x.text AS text, x.role AS role
"""

Q_HANDOFF_ACCEPT: str = """
MATCH (h:Handoff {id:$hid, status:'PENDING', to_agent:$agent})
SET h.status = 'ACCEPTED', h.accepted_at = $ts, h.version = h.version + 1
RETURN h.id AS id
"""

Q_HANDOFF_COMPLETE: str = """
MATCH (h:Handoff {id:$hid, status:'ACCEPTED', to_agent:$agent})
SET h.status = 'COMPLETED', h.completed_at = $ts, h.outcome = $outcome, h.summary = $summary, h.version = h.version + 1
RETURN h.id AS id
"""

Q_HANDOFF_PENDING: str = """
MATCH (h:Handoff {status:'PENDING', to_agent:$agent})
RETURN h.id AS id, h.reason AS reason, h.from_agent AS from_agent, h.session_id AS session_id, h.created_at AS created_at
ORDER BY h.created_at
"""

Q_HANDOFF_READ: str = """
MATCH (h:Handoff {id:$hid}) RETURN h.status AS status, h.to_agent AS to_agent, h.session_id AS session_id
"""

Q_SESSION_SET_AGENT: str = """
MATCH (s:Session {id:$sid}) SET s.current_agent = $agent RETURN s.id AS id
"""
