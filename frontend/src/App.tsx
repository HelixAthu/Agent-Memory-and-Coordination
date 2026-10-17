import { useState, useEffect, useCallback, useReducer, useRef } from "react";
import { GraphNode, GraphEdge } from "./types";
import { fetchUserGraph, createSession, postMessage, resetDemoData, fetchReplay } from "./lib/api";
import { MemoryGraph } from "./components/MemoryGraph";
import { ChatPanel } from "./components/panels/ChatPanel";
import { TraceFeed } from "./components/panels/TraceFeed";
import { MemoryTabs } from "./components/panels/MemoryTabs";
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

  // Replay mode state
  const [isReplayMode, setIsReplayMode] = useState<boolean>(false);
  const [replayScenario, setReplayScenario] = useState<string>("continuity");
  const [replayRunning, setReplayRunning] = useState<boolean>(false);
  const [replayProgress, setReplayProgress] = useState<{ current: number; total: number } | null>(null);
  const replayTimerRef = useRef<number | null>(null);

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

  const stopReplay = useCallback(() => {
    if (replayTimerRef.current !== null) {
      window.clearInterval(replayTimerRef.current);
      replayTimerRef.current = null;
    }
    setReplayRunning(false);
  }, []);

  useEffect(() => {
    return () => {
      if (replayTimerRef.current !== null) {
        window.clearInterval(replayTimerRef.current);
      }
    };
  }, []);

  const startReplay = async (scenarioName = replayScenario) => {
    stopReplay();
    try {
      setLoading(true);
      setError(null);
      const events = await fetchReplay(scenarioName);
      if (!events || events.length === 0) {
        setError(`No events found for replay '${scenarioName}'`);
        return;
      }

      dispatchMemoryEvent({ type: "reset" });
      setReplayRunning(true);
      setReplayProgress({ current: 0, total: events.length });

      let idx = 0;
      replayTimerRef.current = window.setInterval(() => {
        if (idx < events.length) {
          const evt = events[idx];
          dispatchMemoryEvent(evt);
          idx++;
          setReplayProgress({ current: idx, total: events.length });
        } else {
          stopReplay();
        }
      }, 600);
    } catch (err: any) {
      setError(err.message || "Failed to load replay");
      stopReplay();
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
          {/* Scenario / Replay Controls */}
          <div className="p-3 border-b border-border bg-slate-900/80 space-y-2 shrink-0">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                {isReplayMode ? "Replay Mode (Headless)" : "Demo Scenarios (Live SSE)"}
              </span>
              <div className="flex items-center gap-1.5">
                <Button
                  variant={isReplayMode ? "secondary" : "outline"}
                  size="sm"
                  className="h-6 text-[10px] px-2"
                  onClick={() => {
                    stopReplay();
                    setIsReplayMode(!isReplayMode);
                  }}
                >
                  {isReplayMode ? "● Replay" : "○ Replay"}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 text-[10px] text-rose-400 hover:text-rose-300 px-1.5"
                  onClick={handleReset}
                >
                  Reset
                </Button>
              </div>
            </div>

            {isReplayMode ? (
              <div className="space-y-2">
                <div className="grid grid-cols-3 gap-1.5">
                  <Button
                    variant={replayScenario === "continuity" ? "default" : "outline"}
                    size="sm"
                    className="h-7 text-[11px] px-1 truncate"
                    onClick={() => {
                      stopReplay();
                      setReplayScenario("continuity");
                    }}
                    disabled={replayRunning}
                  >
                    Continuity
                  </Button>
                  <Button
                    variant={replayScenario === "fact_update" ? "default" : "outline"}
                    size="sm"
                    className="h-7 text-[11px] px-1 truncate"
                    onClick={() => {
                      stopReplay();
                      setReplayScenario("fact_update");
                    }}
                    disabled={replayRunning}
                  >
                    Fact Update
                  </Button>
                  <Button
                    variant={replayScenario === "procedure_learning" ? "default" : "outline"}
                    size="sm"
                    className="h-7 text-[11px] px-1 truncate"
                    onClick={() => {
                      stopReplay();
                      setReplayScenario("procedure_learning");
                    }}
                    disabled={replayRunning}
                  >
                    Procedure
                  </Button>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <Button
                    variant={replayRunning ? "destructive" : "default"}
                    size="sm"
                    className="h-7 text-xs flex-1"
                    onClick={() => (replayRunning ? stopReplay() : startReplay(replayScenario))}
                  >
                    {replayRunning ? "■ Stop Replay" : "▶ Play Replay (600ms)"}
                  </Button>
                  {replayProgress && (
                    <span className="text-[11px] font-mono text-muted-foreground whitespace-nowrap">
                      {replayProgress.current} / {replayProgress.total}
                    </span>
                  )}
                </div>
              </div>
            ) : (
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
            )}
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

        {/* Right Column (w-96): Memory Tabs */}
        <aside className="w-96 flex flex-col border-l border-border bg-slate-900/40 shrink-0 overflow-hidden">
          <MemoryTabs
            tenant={tenant}
            userId={userId}
          />
        </aside>
      </div>
    </div>
  );
}

export default App;
