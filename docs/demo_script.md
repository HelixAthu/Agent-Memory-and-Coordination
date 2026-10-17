# 3-Minute Demo Video Script & Walkthrough

This document contains the timed script for the hackathon submission video (~3 minutes), matching `docs/spec/06-load-evals-docs.md` Section 11.3.

---

## Timed Video Script

### 0:00 – 0:25: The Problem & Initial Memory State
* **Visual**: Open browser at `http://localhost:5173`. Show the Acme Corp tenant with user **Priya Sharma** selected. The memory graph renders Priya's past 3 sessions, episodes, facts, and procedures.
* **Narration**:
  > "Autonomous multi-agent swarms face a major hurdle in enterprise support: context amnesia. When sessions end, LLM context vanishes. Flat vector stores cannot explain why past decisions were made or navigate connections across shared entities.
  > Here is SwarmGraph Memory Fabric, powered by FalkorDB. For Priya, we see three historical episodes, her active Pro plan fact, and enterprise procedures directly in the graph."

---

### 0:25 – 1:10: Multi-Turn Continuity & Specialist Handoff
* **Visual**: Click the **Continuity** scenario button.
* **Observe in UI**:
  1. Chat panel streams Priya's inquiry: *"Hello, my card shows a duplicate charge again on invoice INV-1042."*
  2. The graph highlights `ep-p1` and `ep-p3` with a golden recall glow and scores.
  3. Notice `ep-p3` was discovered via the graph hop on entity `invoice-inv-1042`, which vector search alone ranked lower.
  4. An animated handoff edge pulses from `agent-triage` to `agent-billing`. The Trace feed shows a bundle of **8 carried items**.
* **Narration**:
  > "When Priya returns with an invoice question, Triage instantly recalls her August duplicate charge. Notice how the second episode is pulled in via a graph hop through the invoice entity.
  > Rather than dumping the entire raw transcript, Triage creates an atomic handoff carrying exactly 8 pre-verified context items to Billing."

---

### 1:10 – 1:35: Billing Resolution & Episode Consolidation
* **Visual**: Billing specialist accepts the handoff, looks up the refund procedure in procedural memory, and resolves the issue.
* **Observe in UI**:
  1. Billing executes the refund workflow steps without re-asking Priya for invoice details.
  2. A new `Episode` node (`ep-sess-demo-continuity`) appears in the graph linked via `[:SUMMARIZED_AS]`.
  3. Click the **Episodic** tab on the right panel to show the newly consolidated episode timeline.
* **Narration**:
  > "Billing accepts the handoff, retrieves the refund procedure, and completes the transaction without asking Priya to repeat herself.
  > Upon session closure, the conversation is automatically consolidated into a new Episode node with graph links to all involved agents and entities."

---

### 1:35 – 1:55: Semantic Memory & Fact Evolution
* **Visual**: Click the **Fact Update** scenario button.
* **Observe in UI**:
  1. Priya states: *"I moved to Pune and prefer chat."*
  2. The old facts (`Mumbai` and `email`) fade to grey with strikethrough labels.
  3. New active facts (`Pune` and `chat`) slide in with green badges and `[:SUPERSEDES]` relationships.
  4. Open the **Semantic** tab and toggle **Show History** to show the 3-entry supersession chain for `prefers_channel`.
* **Narration**:
  > "When user facts evolve, traditional databases either overwrite and destroy the audit trail or duplicate rows.
  > In SwarmGraph, the old facts fade to superseded status, while new facts link directly to them via SUPERSEDES edges. Agents only see current active facts, while the full temporal history remains intact."

---

### 1:55 – 2:15: Procedural Learning & Promotion
* **Visual**: Switch user to **Rahul Verma** and click **Procedure Learning**.
* **Observe in UI**:
  1. Rahul encounters an expired VPN token. Technical Support executes candidate procedure `proc-vpn-token-reset`.
  2. The procedure border turns from dashed to solid, and a **PROMOTED** badge flashes.
  3. Open the **Procedural** tab to show the promotion criteria: 2 successes across 2 distinct users achieved.
* **Narration**:
  > "Workflows start as CANDIDATE procedures. When Rahul's VPN issue is resolved, Technical Support records the success.
  > Having achieved 2 successes across 2 distinct users, FalkorDB promotes the procedure to ACTIVE. The organization learns automatically from agent experience."

---

### 2:15 – 2:50: Isolation Proof & Concurrency Under Load
* **Visual**: Open the **Proof** tab on the right.
* **Observe in UI**:
  1. Click **Run Isolation Check**: All checks turn green (cross-tenant leak: 0, cross-user leak: 0, 403 API key protection).
  2. Switch to **Globex Corp** in the tenant switcher: Show completely disjoint graph with Dana Cole's data.
  3. Switch back to Acme and click **Run Load Test**: Live ops/s counter surges to ~200 ops/s; latency table shows p50 at 5 ms; invariants C1 to C5 all pass.
* **Narration**:
  > "Under the hood, security and concurrency are bulletproof.
  > Our Isolation Proof verifies that each tenant operates on a physically distinct FalkorDB graph. Acme's API keys receive an immediate 403 on Globex data.
  > Running our concurrency load test against 200 tasks and 50 competing claimants demonstrates zero race conditions and sub-10ms write latency using native Cypher CAS."

---

### 2:50 – 3:00: Summary & Conclusion
* **Visual**: Zoom out on the memory graph canvas showing the complete multi-tenant fabric.
* **Narration**:
  > "SwarmGraph Memory Fabric: hybrid recall, evolving semantic facts, self-promoting procedures, and atomic handoffs—built natively on FalkorDB. Thank you."

---

## Owner Pre-Submission Checklist

- [ ] Record video following this script using Loom, QuickTime, or OBS Studio (~3:00).
- [ ] Upload video to YouTube (Unlisted) or Loom.
- [ ] Add the video link to `README.md` under the Demo Video section.
- [ ] Verify fresh clone from temporary directory: `git clone ... && make up seed test`.
- [ ] Push final commit and tag `v1.0` to GitHub.
