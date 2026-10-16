/**
 * Common frontend types mirroring memory graph models, API schemas, and SSE events.
 */

export interface GraphNode {
  id: string;
  label: "User" | "Session" | "Episode" | "Fact" | "Procedure" | "Entity" | "Agent" | "Handoff" | "Task" | string;
  props: Record<string, any>;
  data?: Record<string, any>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  props?: Record<string, any>;
  animated?: boolean;
}

export interface Fact {
  id: string;
  predicate: string;
  object: string;
  status: "ACTIVE" | "SUPERSEDED" | string;
  confidence: number;
  valid_from: number;
  valid_to?: number | null;
}

export interface Episode {
  id: string;
  summary: string;
  importance: number;
  status: "ACTIVE" | "ARCHIVED" | string;
  created_at: number;
}

export interface Procedure {
  id: string;
  name: string;
  situation: string;
  steps: string[];
  successes: number;
  failures: number;
  status: "CANDIDATE" | "ACTIVE" | "DEPRECATED" | string;
  distinct_users?: number;
}

export interface Task {
  id: string;
  title: string;
  status: "OPEN" | "CLAIMED" | "DONE" | string;
  claimed_by: string | null;
  priority: number;
  version: number;
}

export interface Handoff {
  id: string;
  session_id: string;
  from_agent: string;
  to_agent: string;
  status: "PENDING" | "ACCEPTED" | "COMPLETED" | "REJECTED" | string;
  context_summary: string;
  created_at: number;
  accepted_at?: number | null;
  completed_at?: number | null;
  carried_counts?: Record<string, number>;
}

export interface StateEntry {
  key: string;
  value: string;
  version: number;
  updated_by: string;
  updated_at: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  agent_id?: string | null;
  text: string;
  seq: number;
  created_at: number;
}

export type AgentEvent =
  | { type: "agent_active"; data: { agent_id: string; name: string; role: string; tools: string[] }; seq: number; ts: number }
  | { type: "agent_thought"; data: { thought: string }; seq: number; ts: number }
  | { type: "tool_call"; data: { id: string; name: string; args: Record<string, any> }; seq: number; ts: number }
  | { type: "tool_result"; data: { id: string; name: string; result: any; is_error?: boolean }; seq: number; ts: number }
  | { type: "recall_result"; data: { query: string; episodes: Array<{ id: string; score: number; summary?: string }>; facts: any[] }; seq: number; ts: number }
  | { type: "memory_visit"; data: { node_ids: string[]; edge_keys: string[] }; seq: number; ts: number }
  | { type: "fact_update"; data: { fact_id: string; predicate: string; value: string; old_fact_id?: string }; seq: number; ts: number }
  | { type: "handoff"; data: { handoff_id: string; from_agent: string; to_agent: string; status: string; carried_counts?: Record<string, number> }; seq: number; ts: number }
  | { type: "procedure_event"; data: { procedure_id: string; kind: string; successes?: number; users?: number }; seq: number; ts: number }
  | { type: "session_closed"; data: { session_id: string; episode_id?: string }; seq: number; ts: number }
  | { type: "message"; data: { id: string; role: string; text: string; agent_id?: string; seq?: number }; seq: number; ts: number }
  | { type: "warning"; data: { code: string; message: string }; seq: number; ts: number }
  | { type: "error"; data: { code: string; message: string; recoverable?: boolean }; seq: number; ts: number }
  | { type: "final"; data: { text: string; session_id?: string }; seq: number; ts: number };
