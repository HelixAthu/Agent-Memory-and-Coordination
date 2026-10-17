import { GraphNode, GraphEdge, Fact, Episode, Procedure, Task, Handoff, Message } from "../types";

export const TENANT_KEYS: Record<string, string> = {
  acme: "acme-demo-key",
  globex: "globex-demo-key",
};

export function getApiKey(tenantId: string): string {
  return TENANT_KEYS[tenantId] || "";
}

export function getHeaders(tenantId: string): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-API-Key": getApiKey(tenantId),
  };
}

export async function fetchUserGraph(
  tenantId: string,
  userId: string
): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }> {
  const res = await fetch(`/t/${tenantId}/users/${userId}/graph`, {
    headers: getHeaders(tenantId),
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch graph: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchFacts(
  tenantId: string,
  userId: string,
  includeHistory = false
): Promise<Fact[]> {
  const url = `/t/${tenantId}/users/${userId}/facts${includeHistory ? "?include_history=true" : ""}`;
  const res = await fetch(url, { headers: getHeaders(tenantId) });
  if (!res.ok) throw new Error(`Failed to fetch facts: ${res.statusText}`);
  return res.json();
}

export async function fetchEpisodes(
  tenantId: string,
  userId: string
): Promise<Episode[]> {
  const res = await fetch(`/t/${tenantId}/users/${userId}/episodes`, {
    headers: getHeaders(tenantId),
  });
  if (!res.ok) throw new Error(`Failed to fetch episodes: ${res.statusText}`);
  return res.json();
}

export async function fetchProcedures(tenantId: string): Promise<Procedure[]> {
  const res = await fetch(`/t/${tenantId}/procedures`, {
    headers: getHeaders(tenantId),
  });
  if (!res.ok) throw new Error(`Failed to fetch procedures: ${res.statusText}`);
  return res.json();
}

export async function fetchTasks(tenantId: string): Promise<Task[]> {
  const res = await fetch(`/t/${tenantId}/tasks`, {
    headers: getHeaders(tenantId),
  });
  if (!res.ok) throw new Error(`Failed to fetch tasks: ${res.statusText}`);
  return res.json();
}

export async function fetchHandoffs(tenantId: string): Promise<Handoff[]> {
  const res = await fetch(`/t/${tenantId}/handoffs`, {
    headers: getHeaders(tenantId),
  });
  if (!res.ok) throw new Error(`Failed to fetch handoffs: ${res.statusText}`);
  return res.json();
}

export async function checkIsolation(tenantId: string): Promise<any> {
  const res = await fetch(`/t/${tenantId}/isolation-check`, {
    headers: getHeaders(tenantId),
  });
  if (!res.ok) throw new Error(`Isolation check failed: ${res.statusText}`);
  return res.json();
}

export async function createSession(
  tenantId: string,
  userId: string,
  scenario?: string
): Promise<{ session_id: string }> {
  const res = await fetch(`/t/${tenantId}/sessions`, {
    method: "POST",
    headers: getHeaders(tenantId),
    body: JSON.stringify({ user_id: userId, scenario }),
  });
  if (!res.ok) throw new Error(`Failed to create session: ${res.statusText}`);
  return res.json();
}

export async function postMessage(
  tenantId: string,
  sessionId: string,
  role: string,
  text: string
): Promise<{ turn_id: string }> {
  const res = await fetch(`/t/${tenantId}/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: getHeaders(tenantId),
    body: JSON.stringify({ role, text }),
  });
  if (!res.ok) throw new Error(`Failed to post message: ${res.statusText}`);
  return res.json();
}

export async function fetchSessionMessages(
  tenantId: string,
  sessionId: string
): Promise<Message[]> {
  const res = await fetch(`/t/${tenantId}/sessions/${sessionId}/messages`, {
    headers: getHeaders(tenantId),
  });
  if (!res.ok) throw new Error(`Failed to fetch messages: ${res.statusText}`);
  return res.json();
}

export async function resetDemoData(): Promise<any> {
  const res = await fetch("/admin/reset", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Key": "admin-demo-key",
    },
  });
  if (!res.ok) throw new Error(`Failed to reset data: ${res.statusText}`);
  return res.json();
}

export async function runAdminLoadTest(scaleDown = false): Promise<any> {
  const url = `/admin/loadtest${scaleDown ? "?scale_down=true" : ""}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`Load test failed: ${res.statusText}`);
  return res.json();
}
