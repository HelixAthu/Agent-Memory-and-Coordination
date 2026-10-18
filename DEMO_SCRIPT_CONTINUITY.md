# 5-Minute Demo Video Script & Deep Dive: Continuity Scenario

This guide provides a comprehensive breakdown of what happens under the hood during the **Continuity Scenario** in
**Agent-Memory-and-Coordination**, followed by an exact second-by-second recording script (voiceover text, visual
actions, and on-screen focus areas) for a 5-minute explainer demo.

---

## Part 1: What Is Happening Under the Hood

### 1. The Core Architecture
This system is an **Enterprise Multi-Agent Memory & Coordination Fabric** built on **FalkorDB** (RedisGraph).
Standard LLM agent architectures suffer from two fatal flaws in production:
1. **Agent Amnesia:** Conversations are transient; when a new session starts, the agent forgets all past context.
2. **Broken Handoffs:** When transferring a user between specialized agents (e.g., Triage to Billing), context is
   lost or dumped as an unformatted token-expensive text blob, forcing users to repeat themselves.

Our architecture solves this through a **4-Tier Connected Graph Memory Fabric**:
* **Working Memory:** Live in-session short-term scratchpad, recent messages, and active handoff token state.
* **Semantic Memory:** Long-term user facts and preferences stored as subject-predicate-object triples with
  validity windows (`valid_from`, `valid_to`, `superseded_by`).
* **Episodic Memory:** Temporal record of past sessions and interactions with composite importance scoring:
  `score = (similarity * 0.5) + (recency_decay * 0.3) + (importance * 0.2) + context_boost`.
* **Procedural Memory:** Executable workflows and Standard Operating Procedures (SOPs) tracking execution counts,
  success rates, failure rates, and promotion stages (`CANDIDATE` vs `ACTIVE`).
* **Graph Handoff Protocol:** Structured tokens (`Handoff` nodes) carrying exact references to relevant facts,
  episodes, and procedures across agent boundaries without context degradation.

---

### 2. The 8-Step Lifecycle of the Continuity Scenario

1. **User Request Ingestion:**
   User Priya (`user-priya`) sends:
   `"Hello, my card shows a duplicate charge again on invoice INV-1042."`
2. **Context Discovery (`get_user_profile`):**
   `agent-triage` queries FalkorDB via Cypher (`Q-FACTS-ACTIVE`) to load Priya's profile:
   - Pro plan subscriber (`fact-p-plan`)
   - Preferred communication channel: email (`fact-p-channel`)
   - Location: Bengaluru (`fact-p-city`)
3. **Multi-Tier Memory Recall (`recall_memory`):**
   The agent performs hybrid vector + graph retrieval across episodic and procedural memory:
   - Recalls episode `ep-p1` (score: 0.485): On 2026-08-12, Priya reported a duplicate charge on INV-1042.
   - Recalls procedure `proc-dup-charge-refund`: Standard SOP for duplicate charge verification and refund.
4. **Context-Aware Conversational Greeting:**
   Instead of asking generic questions, `agent-triage` responds:
   *"Welcome back, Priya. Last time (2026-08-12) you reported a duplicate charge on invoice INV-1042;
   Billing refunded the duplicate; resolved. I see you prefer email and are on the Pro plan.
   I'm bringing in our Billing specialist."*
5. **Specialist Routing & Handoff Creation (`route_to_specialist`, `create_handoff`):**
   - Routes topic to `agent-billing`.
   - Packages an immutable handoff token (`hof-8b95080d`) in FalkorDB carrying:
     `3 facts, 2 episodes, 1 procedure, 2 conversation messages`.
6. **Specialist Handoff Acceptance (`accept_handoff`):**
   `agent-billing` activates, polls pending handoffs, and accepts `hof-8b95080d`.
   The billing specialist now possesses full historic context without querying the user.
7. **Procedural Execution & Outcome Logging (`find_procedure`, `record_procedure_outcome`):**
   `agent-billing` follows `proc-dup-charge-refund`, verifies both transactions, executes the refund,
   and logs a `success` outcome, incrementing procedure reliability stats in the graph.
8. **Handoff Completion & Episode Consolidation (`complete_handoff`, `close_session`):**
   - Marks handoff token `COMPLETED`.
   - Compresses the session into a new Episode node (`ep-sess-demo-continuity`, importance 0.8).
   - Writes the new episode to FalkorDB and refreshes the graph canvas.

---

## Part 2: Recording Preparation Checklist

* **Screen Resolution:** 1080p (1920x1080), browser zoom at 100%, dark mode.
* **URLs:**
  - Frontend: `http://localhost:5173`
  - Backend: `http://localhost:8000`
* **Pre-Recording Reset:**
  - In the left sidebar, click the red **"Reset"** button to restore clean seed state.
* **Tenant & User Setup:**
  - Tenant: **Acme Corp** (default).
  - User: **Priya** (`user-priya`).
* **Replay Toggle State:**
  - The Replay button shows **`○ Replay`** (inactive).
  - The header displays **`Demo Scenarios (Live SSE)`**.
  - All 3 scenario buttons (**Continuity**, **Fact Update**, **Procedure**) are visible and ready.

---

## Part 3: Minute-by-Minute Video Script (Total Duration: 5:00)

```
====================================================================================================
SECTION 1: THE MULTI-AGENT AMNESIA PROBLEM (0:00 - 0:50)
====================================================================================================
```

### [0:00 - 0:25]
* **VISUAL ACTION:**
  - Full-screen view of the dashboard at `http://localhost:5173`.
  - Mouse pointer moves over the 3-column layout: Left (Chat & Trace), Center (Graph), Right (Memory).
* **AUDIO / SPOKEN SCRIPT:**
  "Welcome! Today I am presenting an Autonomous Multi-Agent Memory and Coordination Fabric.
  If you've ever interacted with customer support chatbots, you've experienced the frustration of agent amnesia:
  the moment you start a new conversation or get transferred to another agent, all your history disappears.
  You are forced to repeat your account number, your issue, and your preferences all over again."

### [0:25 - 0:50]
* **VISUAL ACTION:**
  - Hover over the Center Column (Graph Canvas) showing User, Fact, Agent, and Episode nodes.
* **AUDIO / SPOKEN SCRIPT:**
  "Today's AI agents operate with stateless context windows.
  Our project solves this by anchoring multi-agent coordination into a live knowledge graph powered by FalkorDB.
  We divide memory into four distinct tiers: Semantic facts, Episodic history, Procedural workflows,
  and Working memory. Let's see this in action using our Continuity Scenario."

```
====================================================================================================
SECTION 2: DASHBOARD TOUR & SCENARIO TRIGGER (0:50 - 1:40)
====================================================================================================
```

### [0:50 - 1:15]
* **VISUAL ACTION:**
  - Point to the **Tenant Selector** (`Acme Corp`) and **User Selector** (`Priya`).
  - Point to the header: **Demo Scenarios (Live SSE)**.
  - Show the 3 scenario buttons: `Continuity`, `Fact Update`, `Procedure`.
* **AUDIO / SPOKEN SCRIPT:**
  "Here is our operations dashboard. In the top bar, we are viewing Acme Corporation for customer Priya.
  On the left, we have our real-time Chat and Trace feed.
  In the center, our live FalkorDB memory graph.
  And on the right, our 4-tier memory inspector.
  Notice our Demo Scenarios are primed and ready. Let's click 'Continuity'."

### [1:15 - 1:40]
* **VISUAL ACTION:**
  - Click the **"Continuity"** button.
  - Focus immediately on the **Chat Panel** as Priya's incoming message appears:
    `"Hello, my card shows a duplicate charge again on invoice INV-1042."`
  - Direct attention to the **Trace Feed** right below the chat as tool calls begin streaming in.
* **AUDIO / SPOKEN SCRIPT:**
  "Priya reaches out with a message: 'Hello, my card shows a duplicate charge again on invoice INV-1042.'
  Notice she says 'again'—she has dealt with this before.
  Immediately, our Triage Agent activates and begins interrogating the memory graph via MCP tools."

```
====================================================================================================
SECTION 3: MULTI-TIER MEMORY RECALL IN ACTION (1:40 - 2:40)
====================================================================================================
```

### [1:40 - 2:10]
* **VISUAL ACTION:**
  - Point to `get_user_profile` in the Trace Feed.
  - In the Center Graph, show `fact-p-plan` and `fact-p-channel` nodes highlighting in blue.
  - In the Trace Feed, point to `recall_memory`.
* **AUDIO / SPOKEN SCRIPT:**
  "Look at the trace feed. First, Triage calls `get_user_profile`.
  It reads Priya's semantic facts: she is on the Pro plan and prefers email communication.
  Next, it calls `recall_memory`. Under the hood, this executes a hybrid Cypher query combining vector similarity
  and recency decay across Priya's past episodes.
  And it finds a hit: Episode 1 from August 12, 2026, where Priya had this exact duplicate charge on invoice INV-1042!"

### [2:10 - 2:40]
* **VISUAL ACTION:**
  - Focus on the **Chat Panel** as Triage Agent's response appears:
    `"Welcome back, Priya. Last time (2026-08-12)... I'm bringing in our Billing specialist."`
  - Highlight the exact date reference (2026-08-12) in the agent's message.
* **AUDIO / SPOKEN SCRIPT:**
  "Look at Triage Agent's response:
  'Welcome back, Priya. Last time on August 12th, you reported a duplicate charge on INV-1042; Billing refunded it.
  I see you prefer email and are on the Pro plan. I'm bringing in our Billing specialist.'
  Notice that? Zero hallucination, exact date grounding, and immediate recognition of customer context.
  This transforms customer experience."

```
====================================================================================================
SECTION 4: THE STRUCTURED MULTI-AGENT HANDOFF (2:40 - 3:40)
====================================================================================================
```

### [2:40 - 3:10]
* **VISUAL ACTION:**
  - In the Trace Feed, highlight `route_to_specialist` and `create_handoff`.
  - In the Center Graph, point to the amber `Handoff` node (`hof-8b95080d`) connecting Triage to Billing.
* **AUDIO / SPOKEN SCRIPT:**
  "Now comes the most critical part of coordination: the handoff.
  Triage doesn't just dump text. It calls `create_handoff`, generating an immutable Handoff node in FalkorDB.
  Notice on the graph: an amber handoff token links Triage to the Billing Specialist.
  This structured token carries exactly 3 facts, 2 past episodes, 1 procedure, and the current conversation."

### [3:10 - 3:40]
* **VISUAL ACTION:**
  - In the Trace Feed, point to `accept_handoff` by `agent-billing`.
  - In the Chat Panel, show the message from **Billing Specialist**:
    `"I have the full history from Triage. Following the 'Refund duplicate charge' procedure..."`
* **AUDIO / SPOKEN SCRIPT:**
  "The Billing Specialist activates and calls `accept_handoff`.
  Instantly, the specialist receives the complete context package.
  Billing immediately responds: 'I have the full history from Triage.
  Following the Refund Duplicate Charge procedure, I verified both charges and issued a refund.'
  Priya didn't have to repeat a single detail. The handoff was completely seamless and lossless."

```
====================================================================================================
SECTION 5: PROCEDURAL EXECUTION & EPISODE PERSISTENCE (3:40 - 4:25)
====================================================================================================
```

### [3:40 - 4:05]
* **VISUAL ACTION:**
  - In the Trace Feed, show `record_procedure_outcome` logging `success`.
  - Show `complete_handoff` and `close_session`.
  - In the Center Graph, point to the new green Episode node appearing: `ep-sess-demo-continuity`.
* **AUDIO / SPOKEN SCRIPT:**
  "Behind the scenes, the Billing specialist called `find_procedure` to retrieve our validated refund SOP.
  After executing the refund, it called `record_procedure_outcome` with 'success'.
  This reinforces procedural memory in FalkorDB, improving workflow reliability.
  Finally, Billing marks the handoff complete and calls `close_session`.
  A brand new Episode node is created and linked in the graph, consolidating this interaction for future visits."

### [4:05 - 4:25]
* **VISUAL ACTION:**
  - Direct attention to the **Right Sidebar (Memory Inspector)**.
  - Click on the **"Episodic Memory"** tab to show the newly consolidated episode card.
  - Click on the **"Procedural Memory"** tab to show `Refund duplicate charge` stats.
* **AUDIO / SPOKEN SCRIPT:**
  "Let's inspect our memory tabs on the right:
  Under Episodic Memory, our session has been synthesized with an importance score of 0.8.
  Under Procedural Memory, the duplicate refund procedure tracks increased execution count and 100% success rate.
  Every memory tier is updated, structured, and auditable."

```
====================================================================================================
SECTION 6: CONCLUSION & SUMMARY (4:25 - 5:00)
====================================================================================================
```

### [4:25 - 5:00]
* **VISUAL ACTION:**
  - Pan out to the full dashboard view.
  - Move mouse smoothly across the Chat, live Graph Canvas, and Memory Tabs.
* **AUDIO / SPOKEN SCRIPT:**
  "To summarize:
  By grounding autonomous agents in a FalkorDB graph memory fabric, we eliminated agent amnesia,
  achieved zero-loss multi-agent handoffs, and made every interaction auditable and procedurally repeatable.
  This is how conversational AI transitions from toy chatbots into enterprise-grade multi-agent systems.
  Thank you for watching!"
```
