import { GraphNode, GraphEdge } from "../types";

export interface MemoryState {
  sessionId: string | null;
  activeAgent: string | null;
  messages: Array<{
    id: string;
    role: string;
    text: string;
    agentId?: string | null;
    seq?: number;
  }>;
  traces: any[];
  nodes: GraphNode[];
  edges: GraphEdge[];
  lastRecall: {
    query?: string;
    episodes: Array<{ id: string; score: number; summary?: string; components?: any }>;
    fact_ids?: string[];
    procedure_ids?: string[];
  } | null;
  handoffs: Record<
    string,
    {
      id: string;
      status: string;
      from_agent: string;
      to_agent: string;
      carries?: Record<string, number>;
    }
  >;
  facts: Record<
    string,
    {
      id: string;
      predicate: string;
      object: string;
      status: string;
      confidence?: number;
    }
  >;
  procedures: Record<
    string,
    {
      id: string;
      name?: string;
      status: string;
      successes?: number;
      failures?: number;
    }
  >;
  visitedNodeIds: string[];
  visitedEdgeKeys: string[];
  lastProcedureEvent: { procedure_id: string; kind: string; detail?: string } | null;
  status: "idle" | "running" | "completed" | "error";
  error: string | null;
}

export function createInitialMemoryState(): MemoryState {
  return {
    sessionId: null,
    activeAgent: null,
    messages: [],
    traces: [],
    nodes: [],
    edges: [],
    lastRecall: null,
    handoffs: {},
    facts: {},
    procedures: {},
    visitedNodeIds: [],
    visitedEdgeKeys: [],
    lastProcedureEvent: null,
    status: "idle",
    error: null,
  };
}

export function reduceMemoryEvent(state: MemoryState, event: any): MemoryState {
  if (event.type === "reset") {
    return createInitialMemoryState();
  }

  const traces = [...state.traces, event];
  const type = event.type;
  const data = event.data || {};

  switch (type) {
    case "session_started": {
      return {
        ...state,
        traces,
        sessionId: data.session_id || state.sessionId,
        status: "running",
      };
    }

    case "message": {
      const msg = {
        id: data.id || `msg-${event.seq || Date.now()}`,
        role: data.role || "user",
        text: data.text || "",
        agentId: data.agent_id,
        seq: data.seq ?? event.seq,
      };
      return {
        ...state,
        traces,
        messages: [...state.messages, msg],
      };
    }

    case "agent_active": {
      return {
        ...state,
        traces,
        activeAgent: data.agent_id || state.activeAgent,
      };
    }

    case "recall_result": {
      return {
        ...state,
        traces,
        lastRecall: {
          query: data.query,
          episodes: data.episodes || [],
          fact_ids: data.fact_ids || [],
          procedure_ids: data.procedure_ids || [],
        },
      };
    }

    case "memory_visit": {
      const node_ids = data.node_ids || [];
      const edge_keys = data.edge_keys || [];
      return {
        ...state,
        traces,
        visitedNodeIds: Array.from(new Set([...state.visitedNodeIds, ...node_ids])),
        visitedEdgeKeys: Array.from(new Set([...state.visitedEdgeKeys, ...edge_keys])),
      };
    }

    case "handoff": {
      const hId = data.handoff_id;
      const handoffs = { ...state.handoffs };
      handoffs[hId] = {
        id: hId,
        status: data.status,
        from_agent: data.from_agent,
        to_agent: data.to_agent,
        carries: data.carries,
      };

      let edges = [...state.edges];
      if (data.from_agent && data.to_agent) {
        const edgeId = `${data.from_agent}|HANDOFF|${data.to_agent}`;
        if (!edges.some((e) => e.id === edgeId)) {
          edges.push({
            id: edgeId,
            source: data.from_agent,
            target: data.to_agent,
            type: "HANDOFF",
            animated: data.status === "PENDING" || data.status === "ACCEPTED",
          });
        }
      }

      return {
        ...state,
        traces,
        handoffs,
        edges,
      };
    }

    case "fact_update": {
      const { fact_id, old_fact_id, predicate, object } = data;
      const facts = { ...state.facts };
      let nodes = [...state.nodes];
      let edges = [...state.edges];

      if (old_fact_id) {
        if (facts[old_fact_id]) {
          facts[old_fact_id] = { ...facts[old_fact_id], status: "SUPERSEDED" };
        } else {
          facts[old_fact_id] = {
            id: old_fact_id,
            predicate: predicate || "",
            object: "",
            status: "SUPERSEDED",
          };
        }

        nodes = nodes.map((n) =>
          n.id === old_fact_id
            ? { ...n, props: { ...n.props, status: "SUPERSEDED" } }
            : n
        );
      }

      if (fact_id) {
        facts[fact_id] = {
          id: fact_id,
          predicate: predicate || "",
          object: object || "",
          status: "ACTIVE",
        };

        if (!nodes.some((n) => n.id === fact_id)) {
          nodes.push({
            id: fact_id,
            label: "Fact",
            props: {
              id: fact_id,
              predicate: predicate || "",
              object: object || "",
              status: "ACTIVE",
            },
          });
        }

        if (old_fact_id) {
          const edgeId = `${fact_id}|SUPERSEDES|${old_fact_id}`;
          if (!edges.some((e) => e.id === edgeId)) {
            edges.push({
              id: edgeId,
              source: fact_id,
              target: old_fact_id,
              type: "SUPERSEDES",
            });
          }
        }
      }

      return {
        ...state,
        traces,
        facts,
        nodes,
        edges,
      };
    }

    case "procedure_event": {
      const { procedure_id, kind, detail } = data;
      const procedures = { ...state.procedures };
      const current = procedures[procedure_id] || { id: procedure_id, status: "CANDIDATE" };
      if (kind === "promoted") {
        current.status = "ACTIVE";
      }
      procedures[procedure_id] = current;

      const nodes = state.nodes.map((n) =>
        n.id === procedure_id
          ? { ...n, props: { ...n.props, status: kind === "promoted" ? "ACTIVE" : n.props.status } }
          : n
      );

      return {
        ...state,
        traces,
        procedures,
        nodes,
        lastProcedureEvent: { procedure_id, kind, detail },
      };
    }

    case "session_closed": {
      const epId = data.episode_id;
      let nodes = [...state.nodes];
      let edges = [...state.edges];

      if (epId && !nodes.some((n) => n.id === epId)) {
        nodes.push({
          id: epId,
          label: "Episode",
          props: {
            id: epId,
            summary: "Session Episode",
            importance: data.importance || 0.8,
            status: "ACTIVE",
          },
        });

        if (state.sessionId) {
          const edgeId = `${state.sessionId}|CONSOLIDATED_TO|${epId}`;
          if (!edges.some((e) => e.id === edgeId)) {
            edges.push({
              id: edgeId,
              source: state.sessionId,
              target: epId,
              type: "CONSOLIDATED_TO",
            });
          }
        }
      }

      return {
        ...state,
        traces,
        nodes,
        edges,
        status: "completed",
      };
    }

    case "final": {
      return {
        ...state,
        traces,
        status: "completed",
      };
    }

    case "error": {
      return {
        ...state,
        traces,
        status: "error",
        error: data.message || "An error occurred",
      };
    }

    default: {
      return {
        ...state,
        traces,
      };
    }
  }
}
