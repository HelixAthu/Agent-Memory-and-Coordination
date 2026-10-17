import { useState, useEffect, useCallback, useReducer } from "react";
import { GraphNode, GraphEdge } from "./types";
import { fetchUserGraph, createSession, postMessage, resetDemoData } from "./lib/api";
import { MemoryGraph } from "./components/MemoryGraph";
import { ChatPanel } from "./components/panels/ChatPanel";
import { TraceFeed } from "./components/panels/TraceFeed";
import { Button } from "./components/ui/button";
import { Badge } from "./components/ui/badge";
import { useMemoryStream } from "./hooks/useMemoryStream";
import { createInitialMemoryState, reduceMemoryEvent } from "./lib/eventReducer";

export function App(): JSX.Element {
  const [tenant, setTenant] = useState<string>("acme");
  const [userId, setUserId] = useState<string>("user-priya");
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [activeScenario, setActiveScenario] = useState<string | null>(null);

  // Event-driven state using pure reducer
  const [memoryState, dispatchMemoryEvent] = useReducer(
    reduceMemoryEvent,
    undefined,
    createInitialMemoryState
  );

  const { isStreaming, startStream, stopStream } = useMemoryStream();

  const loadGraph = useCallback(async (t: string, u: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchUserGraph(t, u);
      setGraphNodes(data.nodes || []);
      setGraphEdges(data.edges || []);
    } catch (err: any) {
      setError(err.message || "Failed to load graph");
      setGraphNodes([]);
      setGraphEdges([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleTenantChange = (newTenant: string) => {
    if (newTenant === tenant) return;
    stopStream();
    setTenant(newTenant);
    setGraphNodes([]);
    setGraphEdges([]);
    setError(null);
  };

  const handleUserChange = (newUser: string) => {
    if (newUser === userId) return;
    setUserId(newUser);
  };

  useEffect(() => {
    loadGraph(tenant, userId);
  }, [tenant, userId, loadGraph]);

  const runScenario = async (scenarioName: string) => {
    try {
      setLoading(true);
      setError(null);
      setActiveScenario(scenarioName);

      const targetUser = scenarioName === "procedure_learning" ? "user-rahul" : "user-priya";
      if (userId !== targetUser) {
        setUserId(targetUser);
      }

      const res = await createSession(tenant, targetUser, scenarioName);
      startStream(tenant, res.session_id, (evt) => {
        dispatchMemoryEvent(evt);
        if (evt.type === "final" || evt.type === "session_closed") {
          loadGraph(tenant, targetUser);
        }
      });
    } catch (err: any) {
      setError(err.message || "Failed to run scenario");
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async (text: string) => {
    if (!memoryState.sessionId) return;
    try {
      await postMessage(tenant, memoryState.sessionId, "user", text);
    } catch (err: any) {
      setError(err.message || "Failed to send message");
    }
  };

  const handleReset = async () => {
    try {
      setLoading(true);
      await resetDemoData();
      await loadGraph(tenant, userId);
    } catch (err: any) {
      setError(err.message || "Reset failed");
    } finally {
      setLoading(false);
    }
  };

  // Merge graph nodes with live dynamically updated nodes from reducer
  const allNodes = [...graphNodes];
  for (const liveNode of memoryState.nodes) {
    const idx = allNodes.findIndex((n) => n.id === liveNode.id);
    if (idx >= 0) {
      allNodes[idx] = liveNode;
    } else {
      allNodes.push(liveNode);
    }
  }

  const allEdges = [...graphEdges];
  for (const liveEdge of memoryState.edges) {
    if (!allEdges.some((e) => e.id === liveEdge.id)) {
      allEdges.push(liveEdge);
    }
  }

  return (
    <div className="flex h-screen w-screen flex-col bg-background text-foreground overflow-hidden">
      {/* Top Header & Tenant Switcher */}
      <header className="flex h-14 items-center justify-between border-b border-border bg-slate-900/90 px-4 shrink-0">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xl">🕸️</span>
            <span className="font-bold tracking-tight text-sm text-foreground">
              SwarmGraph Memory Fabric
            </span>
          </div>

          <div className="h-4 w-[1px] bg-border" />

          {/* Tenant Switcher */}
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground mr-1">Tenant:</span>
            <Button
              size="sm"
              variant={tenant === "acme" ? "default" : "outline"}
              className="h-7 text-xs px-2.5"
              onClick={() => handleTenantChange("acme")}
            >
              Acme Corp
            </Button>
            <Button
              size="sm"
              variant={tenant === "globex" ? "default" : "outline"}
              className="h-7 text-xs px-2.5"
              onClick={() => handleTenantChange("globex")}
            >
              Globex Corp
            </Button>
          </div>

          <div className="h-4 w-[1px] bg-border" />

          {/* User Picker */}
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground mr-1">User:</span>
            <Button
              size="sm"
              variant={userId === "user-priya" ? "secondary" : "ghost"}
              className="h-7 text-xs px-2.5"
              onClick={() => handleUserChange("user-priya")}
            >
              Priya Sharma
            </Button>
            <Button
              size="sm"
              variant={userId === "user-rahul" ? "secondary" : "ghost"}
              className="h-7 text-xs px-2.5"
              onClick={() => handleUserChange("user-rahul")}
            >
              Rahul Verma
            </Button>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {error && (
            <Badge variant="destructive" className="text-xs">
              {error}
            </Badge>
          )}
          <Badge variant="outline" className="text-[11px] font-mono text-muted-foreground">
            {allNodes.length} nodes · {allEdges.length} edges
          </Badge>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs"
            onClick={() => loadGraph(tenant, userId)}
            disabled={loading}
          >
            {loading ? "Refreshing..." : "↻ Refresh"}
          </Button>
        </div>
      </header>

      {/* Main 3-Column Layout */}
      <div className="flex flex-1 w-full overflow-hidden">
        {/* Left Column (w-96) */}
        <aside className="w-96 flex flex-col border-r border-border bg-slate-900/40 shrink-0 overflow-hidden">
          {/* Scenario Trigger Buttons */}
          <div className="p-3 border-b border-border bg-slate-900/80 space-y-2 shrink-0">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Demo Scenarios
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 text-[10px] text-rose-400 hover:text-rose-300"
                onClick={handleReset}
              >
                Reset Demo Data
              </Button>
            </div>
            <div className="grid grid-cols-3 gap-1.5">
              <Button
                variant={activeScenario === "continuity" ? "default" : "outline"}
                size="sm"
                className="h-7 text-[11px] px-1 truncate"
                onClick={() => runScenario("continuity")}
                disabled={isStreaming}
              >
                Continuity
              </Button>
              <Button
                variant={activeScenario === "fact_update" ? "default" : "outline"}
                size="sm"
                className="h-7 text-[11px] px-1 truncate"
                onClick={() => runScenario("fact_update")}
                disabled={isStreaming}
              >
                Fact Update
              </Button>
              <Button
                variant={activeScenario === "procedure_learning" ? "default" : "outline"}
                size="sm"
                className="h-7 text-[11px] px-1 truncate"
                onClick={() => runScenario("procedure_learning")}
                disabled={isStreaming}
              >
                Procedure
              </Button>
            </div>
          </div>

          {/* Top Half: Chat Panel */}
          <div className="flex-1 min-h-[220px] overflow-hidden flex flex-col">
            <ChatPanel
              messages={memoryState.messages}
              onSendMessage={handleSendMessage}
              isStreaming={isStreaming}
              agentMode="mock"
            />
          </div>

          {/* Bottom Half: Trace Feed */}
          <div className="flex-1 min-h-[200px] border-t border-border overflow-hidden flex flex-col">
            <TraceFeed traces={memoryState.traces} />
          </div>
        </aside>

        {/* Center: Memory Graph */}
        <main className="flex-1 h-full relative overflow-hidden">
          <MemoryGraph
            nodes={allNodes}
            edges={allEdges}
            highlight={{
              visitedNodeIds: memoryState.visitedNodeIds,
              visitedEdgeKeys: memoryState.visitedEdgeKeys,
              recallEpisodes: memoryState.lastRecall?.episodes,
              promotedProcedureId: memoryState.lastProcedureEvent?.kind === "promoted"
                ? memoryState.lastProcedureEvent.procedure_id
                : null,
            }}
            isLoading={loading}
          />
        </main>
      </div>
    </div>
  );
}

export default App;
