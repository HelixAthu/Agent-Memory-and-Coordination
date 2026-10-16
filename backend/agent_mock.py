"""Scripted mock agents executing real MCP tools and emitting structured events."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from backend.events import EventBus
from backend.mcp_bridge import MCPBridge, MemoryContext
from backend.scenarios import SCENARIOS, Scenario
from memory_core.clock import now
from memory_core.db import get_tenant_db
from memory_core.history import append_message


class MockAgentRunner:
    """Orchestrates deterministic mock runs using real MCP tools and the bridge."""

    def __init__(self, bridge: MCPBridge | None = None) -> None:
        self.bridge = bridge or MCPBridge()

    async def _call_and_emit(
        self,
        ctx: MemoryContext,
        tool: str,
        args: dict[str, Any],
        bus: EventBus,
    ) -> dict[str, Any]:
        """Invoke MCP tool via bridge, emitting tool_call, memory_visit, and tool_result events."""
        call_id = f"call-{uuid.uuid4().hex[:8]}"
        await bus.emit(
            "tool_call",
            {"call_id": call_id, "agent_id": ctx.agent_id, "tool": tool, "args": args},
        )

        envelope = await self.bridge.call(ctx, tool, args, bus=bus)

        # Emit memory_visit from tool envelope
        visit = envelope.get("visit", {})
        await bus.emit(
            "memory_visit",
            {
                "call_id": call_id,
                "kind": visit.get("kind", "read"),
                "node_ids": visit.get("node_ids", []),
                "edge_keys": visit.get("edge_keys", []),
            },
        )

        # Emit tool_result summary
        evidence = envelope.get("evidence", {})
        data = envelope.get("data", {})
        summary = (
            f"{len(data)} items"
            if isinstance(data, (list, dict))
            else str(data)[:30]
        )
        await bus.emit(
            "tool_result",
            {
                "call_id": call_id,
                "ok": envelope.get("ok", False),
                "summary": summary,
                "query_ids": evidence.get("query_ids", []),
                "ms": evidence.get("ms", 0.0),
            },
        )

        return envelope

    async def run(self, scenario_name: str, bus: EventBus | None = None) -> EventBus:
        """Execute a complete mock scenario workflow."""
        if scenario_name not in SCENARIOS:
            raise ValueError(f"Unknown scenario '{scenario_name}'. Available: {list(SCENARIOS.keys())}")

        scenario: Scenario = SCENARIOS[scenario_name]
        event_bus = bus or EventBus()

        # 1. Initialize session in tenant graph
        db = await get_tenant_db(scenario.tenant_id)
        await db.run_rw(
            "MATCH (s:Session {id: $sid}) "
            "OPTIONAL MATCH (s)-[:HAS_MESSAGE]->(m:Message) "
            "OPTIONAL MATCH (s)-[:SUMMARIZED_AS]->(e:Episode) "
            "DETACH DELETE s, m, e",
            {"sid": scenario.session_id},
        )
        await db.run_rw(
            "MATCH (h:Handoff {session_id: $sid}) DETACH DELETE h",
            {"sid": scenario.session_id},
        )
        await db.run_rw(
            "MATCH (u:User {id: $uid}) "
            "CREATE (s:Session {id: $sid, user_id: $uid, status: 'OPEN', current_agent: 'agent-triage', started_at: $ts, msg_count: 0}) "
            "CREATE (u)-[:HAD_SESSION]->(s)",
            {"uid": scenario.user_id, "sid": scenario.session_id, "ts": now()},
        )

        await event_bus.emit(
            "session_started",
            {
                "session_id": scenario.session_id,
                "user_id": scenario.user_id,
                "mode": "mock",
            },
        )

        # 2. Append incoming user turn message
        msg1 = await append_message(
            scenario.tenant_id,
            scenario.session_id,
            role="user",
            text=scenario.user_text,
        )
        await event_bus.emit(
            "message",
            {
                "role": "user",
                "agent_id": None,
                "text": scenario.user_text,
                "seq": msg1["seq"],
            },
        )

        ctx_triage = MemoryContext(
            tenant_id=scenario.tenant_id,
            user_id=scenario.user_id,
            agent_id="agent-triage",
            session_id=scenario.session_id,
        )

        if scenario.id == "continuity":
            await self._run_continuity(scenario, ctx_triage, event_bus)
        elif scenario.id == "fact_update":
            await self._run_fact_update(scenario, ctx_triage, event_bus)
        elif scenario.id == "procedure_learning":
            await self._run_procedure_learning(scenario, ctx_triage, event_bus)

        await event_bus.emit(
            "final",
            {
                "session_id": scenario.session_id,
                "summary": f"Scenario {scenario.id} completed successfully",
            },
        )
        return event_bus

    async def _run_continuity(
        self,
        scenario: Scenario,
        ctx: MemoryContext,
        bus: EventBus,
    ) -> None:
        """Execute continuity scenario with triage and billing specialist handoff."""
        db = await get_tenant_db(scenario.tenant_id)
        await db.run_rw(
            "MATCH (e:Episode {id: 'ep-' + $sid}) DETACH DELETE e",
            {"sid": scenario.session_id},
        )
        await db.run_rw(
            "MATCH (u:User {id: $uid})-[:HAS_FACT]->(f:Fact) WHERE NOT (f.id IN $seed_ids) DETACH DELETE f",
            {
                "uid": scenario.user_id,
                "seed_ids": ["fact-p-plan", "fact-p-channel", "fact-p-channel-old", "fact-p-city"],
            },
        )
        await db.run_rw(
            "MATCH (f:Fact) WHERE f.id = 'fact-p-city' SET f.status = 'ACTIVE', f.object = 'Mumbai', f.valid_to = null"
        )
        await db.run_rw(
            "MATCH (f:Fact) WHERE f.id = 'fact-p-channel' SET f.status = 'ACTIVE', f.object = 'email', f.valid_to = null"
        )

        await bus.emit("agent_active", {"agent_id": "agent-triage", "role": "triage"})

        # Triage Step 1: get_user_profile
        env_prof = await self._call_and_emit(ctx, "get_user_profile", {}, bus)
        facts = env_prof.get("data", {}).get("facts", [])
        plan = next((f["object"] for f in facts if f["predicate"] == "plan"), "Pro")
        channel = next((f["object"] for f in facts if f["predicate"] == "prefers_channel"), "email")
        first_name = "Priya"

        # Triage Step 2: recall_memory
        env_recall = await self._call_and_emit(
            ctx, "recall_memory", {"query": scenario.user_text, "k": 3}, bus
        )
        data_rec = env_recall.get("data", {})
        episodes = data_rec.get("episodes", [])
        await bus.emit(
            "recall_result",
            {
                "episodes": [
                    {"id": e["id"], "score": e["score"], "components": e.get("components", {})}
                    for e in episodes
                ],
                "fact_ids": [f["id"] for f in data_rec.get("facts", [])],
                "procedure_ids": [p["id"] for p in data_rec.get("procedures", [])],
            },
        )

        # Triage Step 3: find_procedure
        await self._call_and_emit(
            ctx, "find_procedure", {"situation": scenario.user_text}, bus
        )

        # Triage Message (seq 2)
        top_ep = episodes[0] if episodes else {"id": "ep-p1", "summary": "", "ts": 1786526400}
        ep_date = datetime.fromtimestamp(1786526400, timezone.utc).strftime("%Y-%m-%d")
        triage_text = (
            f"Welcome back, {first_name}. Last time ({ep_date}) {top_ep.get('summary')} "
            f"I see you prefer {channel} and are on the {plan} plan. I'm bringing in our Billing specialist."
        )
        msg2 = await append_message(
            scenario.tenant_id,
            scenario.session_id,
            role="agent",
            text=triage_text,
            agent_id="agent-triage",
        )
        await bus.emit(
            "message",
            {"role": "agent", "agent_id": "agent-triage", "text": triage_text, "seq": msg2["seq"]},
        )

        # Triage Step 4: route_to_specialist
        env_route = await self._call_and_emit(
            ctx, "route_to_specialist", {"topic_id": "topic-billing"}, bus
        )
        candidates = env_route.get("data", {}).get("candidates", [])
        target_agent = candidates[0]["id"] if candidates else "agent-billing"

        # Triage Step 5: create_handoff
        env_ho = await self._call_and_emit(
            ctx,
            "create_handoff",
            {"to_agent_id": target_agent, "reason": "duplicate charge on invoice INV-1042"},
            bus,
        )
        ho_data = env_ho.get("data", {})
        handoff_id = ho_data["handoff_id"]
        carries = ho_data.get("carries", {})
        await bus.emit(
            "handoff",
            {
                "handoff_id": handoff_id,
                "status": "PENDING",
                "from_agent": "agent-triage",
                "to_agent": target_agent,
                "carries": carries,
            },
        )

        # --- Specialist turn (agent-billing) ---
        ctx_billing = ctx.with_agent(target_agent)
        await bus.emit("agent_active", {"agent_id": target_agent, "role": "specialist"})

        # Specialist Step 1: get_pending_handoffs
        await self._call_and_emit(ctx_billing, "get_pending_handoffs", {}, bus)

        # Specialist Step 2: accept_handoff
        await self._call_and_emit(ctx_billing, "accept_handoff", {"handoff_id": handoff_id}, bus)
        await bus.emit(
            "handoff",
            {
                "handoff_id": handoff_id,
                "status": "ACCEPTED",
                "from_agent": "agent-triage",
                "to_agent": target_agent,
                "carries": carries,
            },
        )

        # Specialist Step 3: find_procedure
        env_proc = await self._call_and_emit(
            ctx_billing, "find_procedure", {"situation": scenario.user_text}, bus
        )
        procs = env_proc.get("data", {}).get("procedures", [])
        proc = procs[0] if procs else {"id": "proc-dup-charge-refund", "name": "Refund duplicate charge"}
        proc_name = proc.get("name", "Refund duplicate charge")
        proc_id = proc.get("id", "proc-dup-charge-refund")

        # Specialist Message (seq 3)
        specialist_text = (
            f"I have the full history from Triage. Following the '{proc_name}' procedure, "
            f"I verified both charges and issued a refund for the duplicate. "
            f"You will get confirmation by {channel}."
        )
        msg3 = await append_message(
            scenario.tenant_id,
            scenario.session_id,
            role="agent",
            text=specialist_text,
            agent_id=target_agent,
        )
        await bus.emit(
            "message",
            {"role": "agent", "agent_id": target_agent, "text": specialist_text, "seq": msg3["seq"]},
        )

        # Specialist Step 4: record_procedure_outcome
        await self._call_and_emit(
            ctx_billing,
            "record_procedure_outcome",
            {"procedure_id": proc_id, "outcome": "success"},
            bus,
        )
        await bus.emit(
            "procedure_event",
            {"procedure_id": proc_id, "kind": "outcome", "detail": "success"},
        )

        # Specialist Step 5: complete_handoff
        await self._call_and_emit(
            ctx_billing,
            "complete_handoff",
            {
                "handoff_id": handoff_id,
                "outcome": "resolved",
                "summary": "Duplicate charge refunded",
            },
            bus,
        )
        await bus.emit(
            "handoff",
            {
                "handoff_id": handoff_id,
                "status": "COMPLETED",
                "from_agent": "agent-triage",
                "to_agent": target_agent,
                "carries": carries,
            },
        )

        # Specialist Step 6: close_session
        env_close = await self._call_and_emit(
            ctx_billing,
            "close_session",
            {"outcome": "resolved"},
            bus,
        )
        close_data = env_close.get("data", {})
        await bus.emit(
            "session_closed",
            {
                "episode_id": close_data.get("episode_id"),
                "importance": close_data.get("importance"),
                "facts_changed": close_data.get("facts_changed", []),
                "promoted": close_data.get("promoted", []),
            },
        )

    async def _run_fact_update(
        self,
        scenario: Scenario,
        ctx: MemoryContext,
        bus: EventBus,
    ) -> None:
        """Execute fact_update scenario recording semantic updates."""
        db = await get_tenant_db(scenario.tenant_id)
        await db.run_rw(
            "MATCH (u:User {id: $uid})-[:HAS_FACT]->(f:Fact) WHERE NOT (f.id IN $seed_ids) DETACH DELETE f",
            {
                "uid": scenario.user_id,
                "seed_ids": ["fact-p-plan", "fact-p-channel", "fact-p-channel-old", "fact-p-city"],
            },
        )
        await db.run_rw(
            "MATCH (f:Fact) WHERE f.id = 'fact-p-city' SET f.status = 'ACTIVE', f.object = 'Mumbai', f.valid_to = null"
        )
        await db.run_rw(
            "MATCH (f:Fact) WHERE f.id = 'fact-p-channel' SET f.status = 'ACTIVE', f.object = 'email', f.valid_to = null"
        )

        await bus.emit("agent_active", {"agent_id": "agent-triage", "role": "triage"})

        # Step 1: get_user_profile
        await self._call_and_emit(ctx, "get_user_profile", {}, bus)

        # Step 2: remember_fact city
        env_f1 = await self._call_and_emit(
            ctx,
            "remember_fact",
            {"predicate": "city", "object": "Pune"},
            bus,
        )
        d1 = env_f1.get("data", {})
        await bus.emit(
            "fact_update",
            {
                "action": d1.get("action", "superseded"),
                "fact_id": d1.get("fact_id"),
                "old_fact_id": d1.get("old_fact_id"),
                "predicate": "city",
                "object": "Pune",
            },
        )

        # Step 3: remember_fact prefers_channel
        env_f2 = await self._call_and_emit(
            ctx,
            "remember_fact",
            {"predicate": "prefers_channel", "object": "chat"},
            bus,
        )
        d2 = env_f2.get("data", {})
        await bus.emit(
            "fact_update",
            {
                "action": d2.get("action", "superseded"),
                "fact_id": d2.get("fact_id"),
                "old_fact_id": d2.get("old_fact_id"),
                "predicate": "prefers_channel",
                "object": "chat",
            },
        )

        # Step 4: Say acknowledgement
        reply_text = "Thanks Priya, I updated your city to Pune and your preferred channel to chat."
        msg = await append_message(
            scenario.tenant_id,
            scenario.session_id,
            role="agent",
            text=reply_text,
            agent_id="agent-triage",
        )
        await bus.emit(
            "message",
            {"role": "agent", "agent_id": "agent-triage", "text": reply_text, "seq": msg["seq"]},
        )

        # Step 5: close_session
        env_close = await self._call_and_emit(ctx, "close_session", {"outcome": "resolved"}, bus)
        close_data = env_close.get("data", {})
        await bus.emit(
            "session_closed",
            {
                "episode_id": close_data.get("episode_id"),
                "importance": close_data.get("importance"),
                "facts_changed": close_data.get("facts_changed", []),
                "promoted": close_data.get("promoted", []),
            },
        )

    async def _run_procedure_learning(
        self,
        scenario: Scenario,
        ctx: MemoryContext,
        bus: EventBus,
    ) -> None:
        """Execute procedure_learning scenario triggering procedure promotion."""
        db = await get_tenant_db(scenario.tenant_id)
        await db.run_rw(
            "MATCH (p:Procedure {id: 'proc-vpn-token-reset'}) SET p.status = 'CANDIDATE'"
        )
        await db.run_rw(
            "MATCH (s:Session {id: $sid})-[a:APPLIED]->(p) DELETE a",
            {"sid": scenario.session_id},
        )

        await bus.emit("agent_active", {"agent_id": "agent-triage", "role": "triage"})

        # Triage Step 1: get_user_profile
        await self._call_and_emit(ctx, "get_user_profile", {}, bus)

        # Triage Step 2: find_procedure
        await self._call_and_emit(
            ctx, "find_procedure", {"situation": scenario.user_text}, bus
        )

        # Triage Message
        triage_text = "I will bring in Technical Support."
        msg2 = await append_message(
            scenario.tenant_id,
            scenario.session_id,
            role="agent",
            text=triage_text,
            agent_id="agent-triage",
        )
        await bus.emit(
            "message",
            {"role": "agent", "agent_id": "agent-triage", "text": triage_text, "seq": msg2["seq"]},
        )

        # Triage Step 3: route_to_specialist
        env_route = await self._call_and_emit(
            ctx, "route_to_specialist", {"topic_id": "topic-vpn"}, bus
        )
        candidates = env_route.get("data", {}).get("candidates", [])
        target_agent = candidates[0]["id"] if candidates else "agent-tech"

        # Triage Step 4: create_handoff
        env_ho = await self._call_and_emit(
            ctx,
            "create_handoff",
            {"to_agent_id": target_agent, "reason": "vpn token expired"},
            bus,
        )
        ho_data = env_ho.get("data", {})
        handoff_id = ho_data["handoff_id"]
        carries = ho_data.get("carries", {})
        await bus.emit(
            "handoff",
            {
                "handoff_id": handoff_id,
                "status": "PENDING",
                "from_agent": "agent-triage",
                "to_agent": target_agent,
                "carries": carries,
            },
        )

        # --- Tech Specialist turn ---
        ctx_tech = ctx.with_agent(target_agent)
        await bus.emit("agent_active", {"agent_id": target_agent, "role": "specialist"})

        # Step 1: get_pending_handoffs
        await self._call_and_emit(ctx_tech, "get_pending_handoffs", {}, bus)

        # Step 2: accept_handoff
        await self._call_and_emit(ctx_tech, "accept_handoff", {"handoff_id": handoff_id}, bus)
        await bus.emit(
            "handoff",
            {
                "handoff_id": handoff_id,
                "status": "ACCEPTED",
                "from_agent": "agent-triage",
                "to_agent": target_agent,
                "carries": carries,
            },
        )

        # Step 3: find_procedure
        env_proc = await self._call_and_emit(
            ctx_tech, "find_procedure", {"situation": scenario.user_text}, bus
        )
        procs = env_proc.get("data", {}).get("procedures", [])
        proc = procs[0] if procs else {"id": "proc-vpn-token-reset", "name": "Reset VPN token"}
        proc_name = proc.get("name", "Reset VPN token")
        proc_id = proc.get("id", "proc-vpn-token-reset")

        # Step 4: Tech Message
        tech_text = f"Following the '{proc_name}' steps, I reset your VPN token."
        msg3 = await append_message(
            scenario.tenant_id,
            scenario.session_id,
            role="agent",
            text=tech_text,
            agent_id=target_agent,
        )
        await bus.emit(
            "message",
            {"role": "agent", "agent_id": target_agent, "text": tech_text, "seq": msg3["seq"]},
        )

        # Step 5: record_procedure_outcome
        await self._call_and_emit(
            ctx_tech,
            "record_procedure_outcome",
            {"procedure_id": proc_id, "outcome": "success"},
            bus,
        )
        await bus.emit(
            "procedure_event",
            {"procedure_id": proc_id, "kind": "outcome", "detail": "success"},
        )

        # Step 6: complete_handoff
        await self._call_and_emit(
            ctx_tech,
            "complete_handoff",
            {
                "handoff_id": handoff_id,
                "outcome": "resolved",
                "summary": "VPN token reset",
            },
            bus,
        )
        await bus.emit(
            "handoff",
            {
                "handoff_id": handoff_id,
                "status": "COMPLETED",
                "from_agent": "agent-triage",
                "to_agent": target_agent,
                "carries": carries,
            },
        )

        # Step 7: close_session (triggers promotion check)
        env_close = await self._call_and_emit(ctx_tech, "close_session", {"outcome": "resolved"}, bus)
        close_data = env_close.get("data", {})
        promoted = close_data.get("promoted", [])
        for p_id in promoted:
            await bus.emit(
                "procedure_event",
                {"procedure_id": p_id, "kind": "promoted", "detail": "promoted to ACTIVE"},
            )

        await bus.emit(
            "session_closed",
            {
                "episode_id": close_data.get("episode_id"),
                "importance": close_data.get("importance"),
                "facts_changed": close_data.get("facts_changed", []),
                "promoted": promoted,
            },
        )


async def run_mock_scenario(scenario_name: str, bus: EventBus | None = None) -> EventBus:
    """Helper entrypoint to execute a mock scenario."""
    runner = MockAgentRunner()
    return await runner.run(scenario_name, bus=bus)
