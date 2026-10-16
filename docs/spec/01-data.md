# Spec 01: Conventions, graph model, seed data, golden values

- **Purpose:** Defines every node, edge, property, the exact seed data and the exact expected test results.
- **Read this when:** building schema/seed (T4), writing tests (T5 to T9, T14), or whenever you need a number. Never recall a number from memory: open this file.

> **File map note:** section numbers (for example "Section 2.3", "G2", "Q-RECALL") are global across the spec files. `AGENTS.md` has the index that says which file holds which section.

---

## 1. Conventions and graph model

### 1.1 Conventions
- **Tenant = one graph** `mem_<tenant_id>`. There is no `tenant_id` property on nodes. Isolation comes from the graph boundary.
- **User scope:** user-private memory (Episode, Fact, Session, Message, Task `FOR_USER`) is only readable when the caller's `user_id` matches. Tenant-shared memory (Procedure, Agent, Entity) is readable by every user and agent of that tenant.
- ID prefixes: `agent-`, `user-`, `topic-`/`product-`/`invoice-` (Entity), `sess-`, `msg-`, `ep-`, `fact-`, `proc-`, `task-`, `hof-` (Handoff), `st-` (StateEntry).
- Edge key (used in events/UI): `<src_id>|<REL_TYPE>|<dst_id>`.
- **Memory types:** *episodic* = `Episode` (what happened), *semantic* = `Fact` (what is true about a user, with history), *procedural* = `Procedure` (how to do things, learned and promoted).
- **Context fields** (`tenant_id`, `user_id`, `agent_id`, `session_id`) are injected by the runtime into every tool call. The LLM never sees or sets them (Section 8.1).

### 1.2 Nodes

| Label | Properties |
|---|---|
| `User` | `id, name` |
| `Agent` | `id, name, role ('triage'\|'specialist'), status ('AVAILABLE'\|'BUSY'\|'OFFLINE')` |
| `Entity` | `id, name, type ('topic'\|'product'\|'invoice'), keywords (list of stems)` |
| `Session` | `id, user_id, status ('OPEN'\|'CLOSED'), started_at, ended_at, outcome, current_agent, msg_count` |
| `Message` | `id, session_id, seq, role ('user'\|'agent'), agent_id, text, ts` |
| `Episode` | `id, summary, outcome, importance (0..1), ts, status ('ACTIVE'\|'ARCHIVED'), embedding (vecf32)` |
| `Fact` | `id, predicate, object, confidence (0..1), status ('ACTIVE'\|'SUPERSEDED'), valid_from, valid_to, last_confirmed, embedding` |
| `Procedure` | `id, name, trigger, steps (list), status ('ACTIVE'\|'CANDIDATE'\|'DEPRECATED'), origin ('policy'\|'learned'), embedding` |
| `Task` | `id, title, status ('OPEN'\|'CLAIMED'\|'DONE'), priority, claimed_by, version, created_at (ms)` |
| `Handoff` | `id, status ('PENDING'\|'ACCEPTED'\|'COMPLETED'), reason, from_agent, to_agent, session_id, version, created_at, accepted_at, completed_at, outcome, summary` |
| `StateEntry` | `id ('st-<session_id>-<key>'), key, value (string), version, updated_by, updated_at` |

Allowed fact predicates (registry, all single-valued): `plan`, `prefers_channel`, `city`. Any other predicate is rejected with `INVALID_INPUT`.

### 1.3 Relationships

| Edge | Meaning |
|---|---|
| `(User)-[:HAD_SESSION]->(Session)` | |
| `(Session)-[:HAS_MESSAGE]->(Message)`, `(Message)-[:NEXT]->(Message)` | persistent conversation history, ordered chain |
| `(Session)-[:SUMMARIZED_AS]->(Episode)` | consolidation result |
| `(Episode)-[:ABOUT]->(User)`, `(Episode)-[:MENTIONS]->(Entity)`, `(Episode)-[:INVOLVED]->(Agent)` | episodic structure |
| `(User)-[:HAS_FACT]->(Fact)`, `(Fact)-[:DERIVED_FROM]->(Session)`, `(Fact)-[:SUPERSEDES]->(Fact)` | semantic memory with provenance and history |
| `(Session)-[:APPLIED {outcome, ts}]->(Procedure)` | procedural usage (`outcome` = `success`\|`failure`) |
| `(Agent)-[:EXPERT_IN]->(Entity)` | routing |
| `(Task)-[:FOR_USER]->(User)` | |
| `(Agent)-[:HANDED_OFF]->(Handoff)`, `(Handoff)-[:TO]->(Agent)`, `(Handoff)-[:FOR_SESSION]->(Session)`, `(Handoff)-[:CARRIES {kind}]->(Fact\|Episode\|Procedure\|Message)` | handoff with context bundle |
| `(Session)-[:HAS_STATE]->(StateEntry)` | shared coordination state |

### 1.4 Indexes and constraints (created by `ensure_tenant`, idempotent)
- Range index on `id` for every label; also `Session.user_id`, `Task.status`, `Handoff.status`, `Handoff.to_agent`.
- Vector indexes: `CREATE VECTOR INDEX FOR (n:Episode) ON (n.embedding) OPTIONS {dimension: <EMBED_DIM>, similarityFunction: 'cosine'}`; same for `Fact` and `Procedure`.
- Unique constraint on `id` for every label **if probe F7 passes** (it requires the range index first). If it fails, use the fallback in Section 6.5.

---

## 2. Seed data (exact; transcribe into JSON)

### 2.1 Tenant `acme`

**Agents:** `agent-triage` (Triage Agent, role triage), `agent-billing` (Billing Specialist, role specialist), `agent-tech` (Technical Specialist, role specialist). All status `AVAILABLE`.

**Users:** `user-priya` (Priya Nair), `user-rahul` (Rahul Mehta).

**Entities** (`keywords` are already stemmed, see Section 5.1):

| id | name | type | keywords |
|---|---|---|---|
| topic-general | General | topic | [] |
| topic-billing | Billing | topic | bill, charg, invoic, payment |
| topic-refunds | Refunds | topic | refund |
| topic-vpn | VPN | topic | vpn |
| topic-login | Login | topic | login, token |
| product-vpn-client | VPN Client | product | client |
| product-pro-plan | Pro Plan | product | pro |
| invoice-inv-1042 | Invoice INV-1042 | invoice | 1042 |

**EXPERT_IN:** triage to topic-general; billing to topic-billing and topic-refunds; tech to topic-vpn and topic-login.

**Sessions** (all `CLOSED`, `outcome=resolved`, `msg_count=4`; times UTC):

| id | user | started | ended |
|---|---|---|---|
| sess-p1 | user-priya | 2026-08-12 09:00 | 2026-08-12 09:20 |
| sess-p2 | user-priya | 2026-09-03 14:00 | 2026-09-03 14:15 |
| sess-p3 | user-priya | 2026-09-28 11:00 | 2026-09-28 11:10 |
| sess-r1 | user-rahul | 2026-09-20 16:00 | 2026-09-20 16:12 |
| sess-r2 | user-rahul | 2026-06-02 10:00 | 2026-06-02 10:05 |

`current_agent` = the specialist (or `agent-triage` for sess-r2).

**Messages** (4 per session, ids `msg-<sid>-<seq>`, `ts` = session start + `seq` minutes). seq 1 = user, seq 2 = agent (agent-triage), seq 3 = agent (specialist), seq 4 = user (`"Thanks, that fixed it."`):

| session | seq 1 (user) | seq 2 (agent-triage) | seq 3 (specialist agent id and text) |
|---|---|---|---|
| sess-p1 | I was charged twice for invoice INV-1042. | Sorry about that, I am bringing in Billing. | agent-billing: I see the duplicate charge and issued a refund for the extra payment. |
| sess-p2 | My VPN client will not let me log in. | Let me bring in Technical Support. | agent-tech: Your VPN token had expired, I reset it. |
| sess-p3 | Why was there a late fee on invoice INV-1042? | I will ask Billing to explain. | agent-billing: The late fee follows the payment policy, I explained the details. |
| sess-r1 | My VPN token expired. | I will ask Technical Support. | agent-tech: I reset your VPN token. |
| sess-r2 | How do I get invoice PDFs formatted? | I can help with that directly. | agent-triage: Invoices can be exported as PDF from the billing page. |

`(Message)-[:NEXT]->(Message)` chains each session's 4 messages in seq order.

**Episodes** (status `ACTIVE`; `ts` = session end; `SUMMARIZED_AS` from the session; `ABOUT` the session's user):

| id | session | summary | importance | MENTIONS | INVOLVED |
|---|---|---|---|---|---|
| ep-p1 | sess-p1 | Priya reported a duplicate charge on invoice INV-1042; Billing refunded the duplicate; resolved. | 0.8 | topic-billing, topic-refunds, invoice-inv-1042 | agent-triage, agent-billing |
| ep-p2 | sess-p2 | Priya could not log in to the VPN client; Tech reset her token; resolved. | 0.5 | topic-vpn, topic-login, product-vpn-client | agent-triage, agent-tech |
| ep-p3 | sess-p3 | Priya asked about a late fee on invoice INV-1042; Billing explained the fee policy; resolved. | 0.6 | topic-billing, invoice-inv-1042 | agent-triage, agent-billing |
| ep-r1 | sess-r1 | Rahul's VPN token expired; Tech reset his token; resolved. | 0.5 | topic-vpn, topic-login | agent-triage, agent-tech |
| ep-r2 | sess-r2 | Rahul asked how to format invoice PDFs; Triage answered; resolved. | 0.1 | topic-general | agent-triage |

**Facts** (embedding text = `"<predicate> <object>"`; `DERIVED_FROM` the listed session):

| id | user | predicate | object | confidence | status | valid_from | valid_to | derived from |
|---|---|---|---|---|---|---|---|---|
| fact-p-plan | user-priya | plan | Pro | 0.9 | ACTIVE | 2026-08-12 | none | sess-p1 |
| fact-p-channel | user-priya | prefers_channel | email | 0.8 | ACTIVE | 2026-08-12 | none | sess-p1 |
| fact-p-channel-old | user-priya | prefers_channel | phone | 0.6 | SUPERSEDED | 2026-06-01 | 2026-08-12 | none |
| fact-p-city | user-priya | city | Mumbai | 0.7 | ACTIVE | 2026-08-12 | none | sess-p1 |
| fact-r-plan | user-rahul | plan | Basic | 0.9 | ACTIVE | 2026-09-20 | none | sess-r1 |
| fact-r-channel | user-rahul | prefers_channel | chat | 0.8 | ACTIVE | 2026-09-20 | none | sess-r1 |

Plus `(fact-p-channel)-[:SUPERSEDES]->(fact-p-channel-old)`. Every fact is `HAS_FACT` of its user. `last_confirmed` = `valid_from`.

**Procedures** (embedding text = `trigger`):

| id | name | trigger | steps | status | origin |
|---|---|---|---|---|---|
| proc-dup-charge-refund | Refund duplicate charge | duplicate charge refund twice charged invoice | Verify both charges on the invoice; Confirm the charges are identical; Issue a refund for the duplicate; Email the customer the refund reference | ACTIVE | policy |
| proc-vpn-token-reset | Reset VPN token | vpn login failing token expired reset | Confirm the user identity; Revoke the old VPN token; Issue a new token and email it | CANDIDATE | learned |

**APPLIED:** `(sess-p1)-[:APPLIED {outcome:'success'}]->(proc-dup-charge-refund)`; `(sess-p2)-[:APPLIED {outcome:'success'}]->(proc-vpn-token-reset)`.

**Tasks:** `task-001` "Verify VPN token expiry policy", OPEN, priority 2, created_at = `2026-10-01T00:00:00Z` converted to epoch milliseconds in code, claimed_by "", version 1, `FOR_USER` user-rahul. `task-002` "Send refund confirmation for INV-1042", DONE, priority 1, claimed_by agent-billing, version 2, created 2026-08-12, `FOR_USER` user-priya.

### 2.2 Tenant `globex` (isolation tests; ids deliberately collide with acme where noted)
- Agent `agent-g-triage` (Triage Agent, triage). User `user-dana` (Dana Cole).
- Entity `topic-billing` (same id as acme on purpose; keywords as in acme).
- Session `sess-d1` (user-dana, 2026-09-10 09:00 to 09:20, resolved, msg_count 4) with 4 messages ("I was charged twice.", "Sorry, let me look.", "I refunded the duplicate charge by phone callback.", "Thanks, that fixed it.") chained by NEXT.
- Episode `ep-d1` (summary: "Dana was charged twice, a duplicate charge; refunded by phone callback; resolved.", importance 0.7, ts 2026-09-10 09:20, ACTIVE, ABOUT user-dana, MENTIONS topic-billing, INVOLVED agent-g-triage, SUMMARIZED_AS from sess-d1).
- Fact `fact-d-channel` (user-dana, prefers_channel, phone, 0.8, ACTIVE, 2026-09-10, derived from sess-d1).
- Procedure `proc-g-dup-refund` (name "Phone refund", trigger "duplicate charge refund phone callback", steps: Call the customer; Refund the duplicate; ACTIVE, policy).

### 2.3 Seed script requirements
`python seed/seed.py [--reset]`. Without `--reset`: idempotent (`MERGE` by `id`). With `--reset`: delete each tenant graph and rebuild. Computes embeddings with the configured embedder. Prints counts per label and relationship type per tenant. Must be callable as a function `seed_tenant(tenant_id)` for tests.

---

## 3. Golden values (tests must assert these; clock frozen at `2026-10-16T00:00:00Z`, mock embedder, `EMBED_DIM=4096`)

**Query Q1** (used below): `Hello, my card shows a duplicate charge again on invoice INV-1042.`

### G1. Seed counts
- `mem_acme` nodes: Agent 3, User 2, Entity 8, Session 5, Message 20, Episode 5, Fact 6, Procedure 2, Task 2 = **53**.
- `mem_acme` edges: HAD_SESSION 5, HAS_MESSAGE 20, NEXT 15, SUMMARIZED_AS 5, ABOUT 5, MENTIONS 11, INVOLVED 9, HAS_FACT 6, DERIVED_FROM 5, SUPERSEDES 1, APPLIED 2, EXPERT_IN 5, FOR_USER 2.
- `mem_globex` nodes: Agent 1, User 1, Entity 1, Session 1, Message 4, Episode 1, Fact 1, Procedure 1 = **11**.

### G2. Recall for `user-priya`, Q1, k=3
- `episodes` ids in order: `[ep-p1, ep-p3, ep-p2]`.
- Components: `ep-p3.boost == 1`; `ep-p1.boost == 0`; `ep-p2.boost == 0`.
- Approximate scores (tolerance 0.05; hand-estimated, so if outside tolerance check the tokenizer before changing the expectation): ep-p1 about 0.485, ep-p3 about 0.405, ep-p2 about 0.087.
- `facts` = exactly the ACTIVE ids `{fact-p-plan, fact-p-channel, fact-p-city}`.
- `procedures` = `[proc-dup-charge-refund]` (CANDIDATE procedures are excluded from recall).
- No id starting with `ep-r`, `ep-d`, `fact-r`, `fact-d` appears anywhere in the result.

### G3. Recall for `user-rahul`, Q1, k=3
Episodes only from `{ep-r1, ep-r2}`; no `ep-p*`; facts `{fact-r-plan, fact-r-channel}`.

### G4. Fact supersession (apply `remember_fact` twice for `user-priya`: `city=Pune`, `prefers_channel=chat`)
- `fact-p-city` becomes SUPERSEDED with `valid_to` = now; a new ACTIVE fact `city=Pune` exists with `(new)-[:SUPERSEDES]->(fact-p-city)`.
- `fact-p-channel` becomes SUPERSEDED; new ACTIVE `prefers_channel=chat`.
- Active facts for priya: exactly 3 (`plan=Pro`, `prefers_channel=chat`, `city=Pune`).
- History for `prefers_channel`: 3 entries `[chat ACTIVE, email SUPERSEDED, phone SUPERSEDED]` (newest first). History for `city`: `[Pune ACTIVE, Mumbai SUPERSEDED]`.

### G5. Reinforcement
`remember_fact(user-priya, plan, Pro)`: returns `action="reinforced"`, same fact id `fact-p-plan`, confidence about 0.95 (tolerance 0.001), no new Fact node (Fact count stays 6).

### G6. Decay
`decay(now)` archives exactly `[ep-r2]` (importance 0.1 < 0.2 and age 135 days > 90). All other episodes stay ACTIVE. Archived episodes never appear in recall.

### G7. Routing
`route(topic-billing) = [agent-billing]`, `route(topic-refunds) = [agent-billing]`, `route(topic-vpn) = [agent-tech]`, `route(topic-login) = [agent-tech]`, `route(topic-general) = [agent-triage]`. Unknown topic returns `NOT_FOUND`.

### G8. Handoff (scripted continuity scenario, session `sess-demo-continuity`, 2 messages written before the handoff)
- Bundle `CARRIES` = **8**: facts 3 (all ACTIVE of priya), episodes 2 (`ep-p1`, `ep-p3`), procedures 1 (`proc-dup-charge-refund`), messages 2.
- State machine: PENDING, then ACCEPTED, then COMPLETED.
- `accept_handoff` by `agent-tech` returns `FORBIDDEN`; by `agent-billing` succeeds; a second accept returns `CONFLICT`.
- 10 concurrent accepts by `agent-billing` on one PENDING handoff produce exactly 1 success and 9 `CONFLICT`.

### G9. Consolidation (`close_session` for `sess-demo-continuity`, outcome `resolved`, handoff occurred)
- Episode id `ep-sess-demo-continuity`; `importance == 0.8` (0.6 base for resolved, plus 0.2 for a handoff); `ABOUT user-priya`; `INVOLVED` = `{agent-triage, agent-billing}`; `MENTIONS` contains `{topic-billing, topic-refunds, invoice-inv-1042}`; `(sess-demo-continuity)-[:SUMMARIZED_AS]->(episode)`; session status CLOSED.

### G10. Procedure promotion (scripted procedure-learning scenario for `user-rahul`)
- Before: `proc-vpn-token-reset` CANDIDATE with 1 success from 1 distinct user.
- After `record_procedure_outcome(success)` in a rahul session and `promote_procedures()`: 2 successes, 2 distinct users, status **ACTIVE**, and `promote_procedures()` returns `[proc-vpn-token-reset]`. Calling it again returns `[]`.

### G11. Tasks
- `claim(task-001, agent-tech)` succeeds with version 2; a second claim returns `CONFLICT`. `claim_next` with `task-001` already claimed returns `NOT_FOUND` ("no open tasks") because `task-002` is DONE.

### G12. Shared state (CAS)
`set_state(key, "a", expected_version=0)` creates version 1; `set_state(key, "b", expected_version=1)` gives version 2; `set_state(key, "c", expected_version=1)` returns `CONFLICT` with `current_version=2`.

### G13. Isolation
- Tenant: Q1 recall in `mem_globex` for `user-dana` returns `[ep-d1]`, never any acme id; Q1 recall in `mem_acme` for priya never returns `ep-d1`.
- Context injection: a tool call whose LLM-supplied args include `tenant_id="globex"` still runs in the bound tenant (acme).
- API: a request to `/t/globex/...` with the acme key returns HTTP 403.
- Validation: `tenant_id="acme; DROP"` is rejected with `INVALID_INPUT` before any DB call.
- User: recall as `user-rahul` never returns `ep-p*` or `fact-p*`.
- Role allowlist: `agent-triage` calling `accept_handoff` returns `FORBIDDEN`.

### G14. Persistent history under concurrency
3 concurrent `append_message` calls on one session with `msg_count=4` produce seq values exactly `{5, 6, 7}` (no duplicates, no gaps). The session then has 7 messages chained by 6 `NEXT` edges (seq 1 to 7, in order).

### G15. Concurrency invariants (load test)
- C1: 1 OPEN task, 50 concurrent `claim` attempts: exactly 1 success, 49 `CONFLICT`.
- C2: 200 OPEN tasks, 20 workers looping `claim_next` until none left: exactly 200 successful claims, 0 tasks claimed twice, sum of per-worker counts equals 200.
- C3: CAS counter: 20 workers each perform 10 increments (read, set with expected_version, retry on `CONFLICT`): final value is 200.
- C4: Two tenants (`acme`, `globex`) run C2 and C3 interleaved: each tenant's final counts are correct and no id created in one tenant exists in the other.
- C5: While writes run, 100 concurrent `recall` calls all succeed (no exceptions); record p50/p95/p99 latency.
