import fs from "fs";
import path from "path";
import { describe, it, expect } from "vitest";
import {
  createInitialMemoryState,
  reduceMemoryEvent,
  MemoryState,
} from "../lib/eventReducer";

function loadReplayEvents(filename: string): any[] {
  const replayPath = path.resolve(__dirname, "../../../replays", filename);
  const content = fs.readFileSync(replayPath, "utf-8");
  return content
    .trim()
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line));
}

describe("Memory Event Reducer", () => {
  it("initializes clean memory state", () => {
    const state = createInitialMemoryState();
    expect(state.status).toBe("idle");
    expect(state.messages).toEqual([]);
    expect(state.nodes).toEqual([]);
    expect(state.edges).toEqual([]);
    expect(state.lastRecall).toBeNull();
  });

  it("processes replays/continuity.jsonl to exact acceptance criteria", () => {
    const events = loadReplayEvents("continuity.jsonl");
    expect(events.length).toBeGreaterThan(0);

    let state: MemoryState = createInitialMemoryState();
    for (const event of events) {
      state = reduceMemoryEvent(state, event);
    }

    // Acceptance 1: the handoff status reached COMPLETED
    const handoffs = Object.values(state.handoffs);
    expect(handoffs.length).toBeGreaterThan(0);
    const completedHandoff = handoffs.find((h) => h.status === "COMPLETED");
    expect(completedHandoff).toBeDefined();
    expect(completedHandoff?.to_agent).toBe("agent-billing");

    // Acceptance 2: an Episode node ep-sess-demo-continuity exists at the end
    const episodeNode = state.nodes.find((n) => n.id === "ep-sess-demo-continuity");
    expect(episodeNode).toBeDefined();
    expect(episodeNode?.label).toBe("Episode");

    // Acceptance 3: recall_result.episodes[0].id == "ep-p1"
    expect(state.lastRecall).toBeDefined();
    expect(state.lastRecall?.episodes[0]?.id).toBe("ep-p1");

    // State completeness assertions
    expect(state.status).toBe("completed");
    expect(state.messages.length).toBeGreaterThan(0);
  });

  it("processes replays/fact_update.jsonl to exact acceptance criteria", () => {
    const events = loadReplayEvents("fact_update.jsonl");
    expect(events.length).toBeGreaterThan(0);

    let state: MemoryState = createInitialMemoryState();
    for (const event of events) {
      state = reduceMemoryEvent(state, event);
    }

    // Acceptance 1: fact-p-city ends SUPERSEDED
    expect(state.facts["fact-p-city"]).toBeDefined();
    expect(state.facts["fact-p-city"].status).toBe("SUPERSEDED");

    // Acceptance 2: a new ACTIVE city fact exists
    const facts = Object.values(state.facts);
    const activeCityFact = facts.find(
      (f) => f.predicate === "city" && f.status === "ACTIVE"
    );
    expect(activeCityFact).toBeDefined();
    expect(activeCityFact?.object).toBe("Pune");

    // Check edge supersession
    const supersedesEdge = state.edges.find(
      (e) => e.type === "SUPERSEDES" && e.target === "fact-p-city"
    );
    expect(supersedesEdge).toBeDefined();
  });

  it("processes replays/procedure_learning.jsonl to exact acceptance criteria", () => {
    const events = loadReplayEvents("procedure_learning.jsonl");
    expect(events.length).toBeGreaterThan(0);

    let state: MemoryState = createInitialMemoryState();
    for (const event of events) {
      state = reduceMemoryEvent(state, event);
    }

    // Acceptance: a procedure_event of kind promoted for proc-vpn-token-reset
    expect(state.lastProcedureEvent).toBeDefined();
    expect(state.lastProcedureEvent?.kind).toBe("promoted");
    expect(state.lastProcedureEvent?.procedure_id).toBe("proc-vpn-token-reset");

    // Procedure status was updated to ACTIVE
    expect(state.procedures["proc-vpn-token-reset"]).toBeDefined();
    expect(state.procedures["proc-vpn-token-reset"].status).toBe("ACTIVE");
  });
});
