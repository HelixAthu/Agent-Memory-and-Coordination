import { useState, useEffect, useCallback, useReducer, useRef } from "react";
import { GraphNode, GraphEdge } from "./types";
import {
  fetchUserGraph,
  createSession,
  postMessage,
  resetDemoData,
  fetchReplay,
  updateAgentMode,
} from "./lib/api";
import { MemoryGraph } from "./components/MemoryGraph";
import { ChatPanel } from "./components/panels/ChatPanel";
import { TraceFeed } from "./components/panels/TraceFeed";
import { MemoryTabs } from "./components/panels/MemoryTabs";
import { Button } from "./components/ui/button";
import { Badge } from "./components/ui/badge";
import { useMemoryStream } from "./hooks/useMemoryStream";
import { createInitialMemoryState, reduceMemoryEvent } from "./lib/eventReducer";

const USERS_BY_TENANT: Record<string, { id: string; name: string }[]> = {
  acme: [
    { id: "user-priya", name: "Priya Sharma" },
    { id: "user-rahul", name: "Rahul Verma" },
  ],
  globex: [{ id: "user-dana", name: "Dana Cole" }],
};

export function App(): JSX.Element {
  const [tenant, setTenant] = useState<string>("acme");
  const [userId, setUserId] = useState<string>("user-priya");
  const [agentMode, setAgentMode] = useState<"mock" | "live">("mock");
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [activeScenario, setActiveScenario] = useState<string | null>(null);
  const [tabRefreshKey, setTabRefreshKey] = useState<number>(0);

  // Replay mode state & full capabilities
  const [isReplayMode, setIsReplayMode] = useState<boolean>(false);
  const [replayScenario, setReplayScenario] = useState<string>("continuity");
  const [replayEvents, setReplayEvents] = useState<any[]>([]);
  const [replayIndex, setReplayIndex] = useState<number>(0);
  const [replayRunning, setReplayRunning] = useState<boolean>(false);
  const [replaySpeed, setReplaySpeed] = useState<number>(600);
  const replayTimerRef = useRef<number | null>(null);
  const replayEventsRef = useRef<any[]>([]);
  const replayIndexRef = useRef<number>(0);

  // Keep refs in sync for interval callbacks
  replayEventsRef.current = replayEvents;
  replayIndexRef.current = replayIndex;

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
    stopReplay();
    stopStream();
    dispatchMemoryEvent({ type: "reset" });
    setTenant(newTenant);
    const defaultUser = newTenant === "globex" ? "user-dana" : "user-priya";
    setUserId(defaultUser);
    setGraphNodes([]);
    setGraphEdges([]);
    setError(null);
    setActiveScenario(null);
  };

  const handleUserChange = (newUser: string) => {
    if (newUser === userId) return;
    setUserId(newUser);
  };

  const handleModeChange = async (newMode: "mock" | "live") => {
    setAgentMode(newMode);
    try {
      await updateAgentMode(newMode);
      setStatusMessage(`Mode: ${newMode === "live" ? "✨ Gemini Live" : "🤖 Mock Engine"}`);
      setTimeout(() => setStatusMessage(null), 3000);
    } catch {
      // Best-effort config sync
    }
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
      if (tenant !== "acme") {
        setTenant("acme");
      }
      if (userId !== targetUser) {
        setUserId(targetUser);
      }

      const res = await createSession("acme", targetUser, scenarioName, agentMode);
      startStream("acme", res.session_id, (evt) => {
        dispatchMemoryEvent(evt);
        if (evt.type === "final" || evt.type === "session_closed") {
          loadGraph("acme", targetUser);
          setTabRefreshKey((k) => k + 1);
        }
      });
    } catch (err: any) {
      setError(err.message || "Failed to run scenario");
    } finally {
      setLoading(false);
    }
  };

  const runGlobexInquiry = async () => {
    try {
      setLoading(true);
      setError(null);
      setActiveScenario("globex_charge_inquiry");
      const res = await createSession("globex", "user-dana", undefined, agentMode);
      startStream("globex", res.session_id, (evt) => {
        dispatchMemoryEvent(evt);
        if (evt.type === "final" || evt.type === "session_closed") {
          loadGraph("globex", "user-dana");
          setTabRefreshKey((k) => k + 1);
        }
      });
      await postMessage(
        "globex",
        res.session_id,
        "user",
        "Hello, I was charged twice for invoice GLX-8801. My preferred contact channel is phone callback.",
        agentMode
      );
    } catch (err: any) {
      setError(err.message || "Failed to run Globex inquiry");
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async (text: string) => {
    try {
      let sid = memoryState.sessionId;
      if (!sid) {
        setLoading(true);
        const res = await createSession(tenant, userId, undefined, agentMode);
        sid = res.session_id;
        startStream(tenant, sid, (evt) => {
          dispatchMemoryEvent(evt);
          if (evt.type === "final" || evt.type === "session_closed") {
            loadGraph(tenant, userId);
            setTabRefreshKey((k) => k + 1);
          }
        });
      }
      await postMessage(tenant, sid, "user", text, agentMode);
    } catch (err: any) {
      setError(err.message || "Failed to send message");
    } finally {
      setLoading(false);
    }
  };

  // Full Reset: stops ongoing streams/replays, resets reducer, wipes FalkorDB to seeds, reloads canvas & tabs
  const handleReset = async () => {
    try {
      setLoading(true);
      stopReplay();
      stopStream();
      dispatchMemoryEvent({ type: "reset" });
      setActiveScenario(null);
      await resetDemoData();
      await loadGraph(tenant, userId);
      setTabRefreshKey((k) => k + 1);
      setError(null);
      setStatusMessage("Environment reset to clean seed state");
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err: any) {
      setError(err.message || "Reset failed");
    } finally {
      setLoading(false);
    }
  };

  // Replay Management
  const stopReplay = useCallback(() => {
    if (replayTimerRef.current !== null) {
      window.clearInterval(replayTimerRef.current);
      replayTimerRef.current = null;
    }
    setReplayRunning(false);
  }, []);

  const loadReplay = useCallback(async (scenarioName: string) => {
    stopReplay();
    try {
      setLoading(true);
      setError(null);
      setReplayScenario(scenarioName);

      // Auto-align tenant and user with recorded scenario
      const targetUser = scenarioName === "procedure_learning" ? "user-rahul" : "user-priya";
      if (tenant !== "acme") {
        setTenant("acme");
      }
      if (userId !== targetUser) {
        setUserId(targetUser);
      }

      const events = await fetchReplay(scenarioName);
      if (!events || events.length === 0) {
        setError(`No events found for replay '${scenarioName}'`);
        setReplayEvents([]);
        setReplayIndex(0);
        return;
      }
      dispatchMemoryEvent({ type: "reset" });
      setReplayEvents(events);
      setReplayIndex(0);
    } catch (err: any) {
      setError(err.message || "Failed to load replay events");
      setReplayEvents([]);
      setReplayIndex(0);
    } finally {
      setLoading(false);
    }
  }, [stopReplay, tenant, userId]);

  useEffect(() => {
    return () => {
      if (replayTimerRef.current !== null) {
        window.clearInterval(replayTimerRef.current);
      }
    };
  }, []);

  // Play / Resume
  const playReplay = (speed = replaySpeed) => {
    if (replayEventsRef.current.length === 0) return;
    stopReplay();

    // If finished, restart from start
    if (replayIndexRef.current >= replayEventsRef.current.length) {
      dispatchMemoryEvent({ type: "reset" });
      setReplayIndex(0);
      replayIndexRef.current = 0;
    }

    setReplayRunning(true);
    const targetUser = replayScenario === "procedure_learning" ? "user-rahul" : "user-priya";

    replayTimerRef.current = window.setInterval(() => {
      const evts = replayEventsRef.current;
      const idx = replayIndexRef.current;
      if (idx < evts.length) {
        const evt = evts[idx];
        dispatchMemoryEvent(evt);
        const nextIdx = idx + 1;
        setReplayIndex(nextIdx);
        replayIndexRef.current = nextIdx;
        if (nextIdx >= evts.length) {
          stopReplay();
          loadGraph("acme", targetUser);
          setTabRefreshKey((k) => k + 1);
        }
      } else {
        stopReplay();
        loadGraph("acme", targetUser);
        setTabRefreshKey((k) => k + 1);
      }
    }, speed);
  };

  // Step single event
  const stepReplay = () => {
    stopReplay();
    const evts = replayEventsRef.current;
    const idx = replayIndexRef.current;
    if (idx < evts.length) {
      const evt = evts[idx];
      dispatchMemoryEvent(evt);
      const nextIdx = idx + 1;
      setReplayIndex(nextIdx);
      replayIndexRef.current = nextIdx;
      if (nextIdx >= evts.length) {
        const targetUser = replayScenario === "procedure_learning" ? "user-rahul" : "user-priya";
        loadGraph("acme", targetUser);
        setTabRefreshKey((k) => k + 1);
      }
    }
  };

  // Restart from beginning
  const restartReplay = () => {
    stopReplay();
    dispatchMemoryEvent({ type: "reset" });
    setReplayIndex(0);
    replayIndexRef.current = 0;
  };

  // Change speed dynamically
  const handleSpeedChange = (speedMs: number) => {
    setReplaySpeed(speedMs);
    if (replayRunning) {
      playReplay(speedMs);
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

  const currentUsers = USERS_BY_TENANT[tenant] || [];

  return (
    <div className="flex h-screen w-screen flex-col bg-background text-foreground overflow-hidden">
      {/* Top Header & Tenant Switcher */}
      <header className="flex h-14 items-center justify-between border-b border-border bg-slate-900/90 px-4 shrink-0">
        <div className="flex items-center gap-3">
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

          {/* User Picker based on tenant */}
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground mr-1">User:</span>
            {currentUsers.map((u) => (
              <Button
                key={u.id}
                size="sm"
                variant={userId === u.id ? "secondary" : "ghost"}
                className="h-7 text-xs px-2.5"
                onClick={() => handleUserChange(u.id)}
              >
                {u.name}
              </Button>
            ))}
          </div>

          <div className="h-4 w-[1px] bg-border" />

          {/* Model Engine Selector */}
          <div className="flex items-center gap-1 bg-slate-950/80 p-0.5 rounded border border-border">
            <span className="text-[11px] text-muted-foreground px-1.5">Engine:</span>
            <button
              type="button"
              className={`h-6 text-[10px] px-2 rounded transition-colors ${
                agentMode === "mock"
                  ? "bg-slate-800 text-slate-100 font-medium"
                  : "text-muted-foreground hover:text-slate-200"
              }`}
              onClick={() => handleModeChange("mock")}
            >
              🤖 Mock
            </button>
            <button
              type="button"
              className={`h-6 text-[10px] px-2 rounded transition-colors ${
                agentMode === "live"
                  ? "bg-amber-950 text-amber-200 border border-amber-700/60 font-medium"
                  : "text-muted-foreground hover:text-amber-200"
              }`}
              onClick={() => handleModeChange("live")}
            >
              ✨ Gemini Live
            </button>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {statusMessage && (
            <Badge variant="secondary" className="text-xs bg-emerald-950 text-emerald-300 border-emerald-700/50">
              {statusMessage}
            </Badge>
          )}
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
                {isReplayMode ? "Replay Mode (Headless Player)" : "Demo Scenarios (Live SSE)"}
              </span>
              <div className="flex items-center gap-1.5">
                <Button
                  variant={isReplayMode ? "secondary" : "outline"}
                  size="sm"
                  className="h-6 text-[10px] px-2"
                  onClick={() => {
                    stopReplay();
                    const nextMode = !isReplayMode;
                    setIsReplayMode(nextMode);
                    if (nextMode && replayEvents.length === 0) {
                      loadReplay(replayScenario);
                    }
                  }}
                >
                  {isReplayMode ? "● Replay" : "○ Replay"}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 text-[10px] text-rose-400 hover:text-rose-300 px-1.5"
                  onClick={handleReset}
                  title="Full Reset: stops replays/streams, wipes to seeds, reloads graph & tabs"
                >
                  Reset
                </Button>
              </div>
            </div>

            {isReplayMode ? (
              <div className="space-y-2">
                {/* Scenario Picker */}
                <div className="grid grid-cols-3 gap-1.5">
                  <Button
                    variant={replayScenario === "continuity" ? "default" : "outline"}
                    size="sm"
                    className="h-7 text-[11px] px-1 truncate"
                    onClick={() => loadReplay("continuity")}
                  >
                    Continuity
                  </Button>
                  <Button
                    variant={replayScenario === "fact_update" ? "default" : "outline"}
                    size="sm"
                    className="h-7 text-[11px] px-1 truncate"
                    onClick={() => loadReplay("fact_update")}
                  >
                    Fact Update
                  </Button>
                  <Button
                    variant={replayScenario === "procedure_learning" ? "default" : "outline"}
                    size="sm"
                    className="h-7 text-[11px] px-1 truncate"
                    onClick={() => loadReplay("procedure_learning")}
                  >
                    Procedure
                  </Button>
                </div>

                {/* Playback Controls & Stepper */}
                <div className="flex items-center gap-1.5">
                  <Button
                    variant={replayRunning ? "secondary" : "default"}
                    size="sm"
                    className="h-7 text-xs flex-1"
                    onClick={() => (replayRunning ? stopReplay() : playReplay())}
                  >
                    {replayRunning
                      ? "⏸ Pause"
                      : replayIndex > 0 && replayIndex < replayEvents.length
                      ? "▶ Resume"
                      : "▶ Play"}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs px-2"
                    onClick={stepReplay}
                    disabled={replayIndex >= replayEvents.length}
                    title="Step 1 event forward"
                  >
                    ▶| Step
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs px-2 text-slate-400 hover:text-slate-200"
                    onClick={restartReplay}
                    title="Restart from beginning"
                  >
                    ↺ Reset
                  </Button>
                </div>

                {/* Speed Selector & Progress Scrubber */}
                <div className="flex items-center justify-between gap-2 pt-0.5 text-[11px]">
                  <div className="flex items-center gap-1">
                    <span className="text-[10px] text-muted-foreground">Speed:</span>
                    <button
                      type="button"
                      className={`px-1.5 py-0.5 rounded text-[10px] ${
                        replaySpeed === 600 ? "bg-slate-700 text-white font-medium" : "text-slate-400 hover:text-white"
                      }`}
                      onClick={() => handleSpeedChange(600)}
                    >
                      1x
                    </button>
                    <button
                      type="button"
                      className={`px-1.5 py-0.5 rounded text-[10px] ${
                        replaySpeed === 300 ? "bg-slate-700 text-white font-medium" : "text-slate-400 hover:text-white"
                      }`}
                      onClick={() => handleSpeedChange(300)}
                    >
                      2x
                    </button>
                    <button
                      type="button"
                      className={`px-1.5 py-0.5 rounded text-[10px] ${
                        replaySpeed === 100 ? "bg-slate-700 text-white font-medium" : "text-slate-400 hover:text-white"
                      }`}
                      onClick={() => handleSpeedChange(100)}
                    >
                      5x
                    </button>
                  </div>

                  <span className="font-mono text-muted-foreground whitespace-nowrap text-[10px]">
                    {replayIndex} / {replayEvents.length} events
                  </span>
                </div>

                {/* Progress bar */}
                {replayEvents.length > 0 && (
                  <div className="w-full bg-slate-800 rounded-full h-1 overflow-hidden">
                    <div
                      className="bg-blue-500 h-1 transition-all duration-150"
                      style={{
                        width: `${(replayIndex / replayEvents.length) * 100}%`,
                      }}
                    />
                  </div>
                )}
              </div>
            ) : tenant === "globex" ? (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>Globex Demo Incident:</span>
                  <Badge variant="outline" className="text-[9px] text-amber-300 border-amber-800">
                    user-dana
                  </Badge>
                </div>
                <Button
                  variant={activeScenario === "globex_charge_inquiry" ? "default" : "outline"}
                  size="sm"
                  className="h-7 text-xs w-full"
                  onClick={runGlobexInquiry}
                  disabled={isStreaming}
                >
                  Duplicate Charge Inquiry (Phone Callback)
                </Button>
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
              agentMode={agentMode}
              onModeChange={handleModeChange}
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
              promotedProcedureId:
                memoryState.lastProcedureEvent?.kind === "promoted"
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
            refreshKey={tabRefreshKey}
          />
        </aside>
      </div>
    </div>
  );
}

export default App;
