import { useState, useEffect, useCallback } from "react";
import { GraphNode, GraphEdge } from "./types";
import { fetchUserGraph } from "./lib/api";
import { MemoryGraph } from "./components/MemoryGraph";
import { Button } from "./components/ui/button";
import { Badge } from "./components/ui/badge";

export function App(): JSX.Element {
  const [tenant, setTenant] = useState<string>("acme");
  const [userId, setUserId] = useState<string>("user-priya");
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const loadGraph = useCallback(async (t: string, u: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchUserGraph(t, u);
      setNodes(data.nodes || []);
      setEdges(data.edges || []);
    } catch (err: any) {
      setError(err.message || "Failed to load graph");
      setNodes([]);
      setEdges([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleTenantChange = (newTenant: string) => {
    if (newTenant === tenant) return;
    // Switching tenant clears all UI state per spec
    setTenant(newTenant);
    setNodes([]);
    setEdges([]);
    setError(null);
  };

  const handleUserChange = (newUser: string) => {
    if (newUser === userId) return;
    setUserId(newUser);
  };

  useEffect(() => {
    loadGraph(tenant, userId);
  }, [tenant, userId, loadGraph]);

  return (
    <div className="flex h-screen w-screen flex-col bg-background text-foreground overflow-hidden">
      {/* Top Header & Tenant Switcher */}
      <header className="flex h-14 items-center justify-between border-b border-border bg-slate-900/90 px-4">
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
            {nodes.length} nodes · {edges.length} edges
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

      {/* Main Canvas View */}
      <main className="flex-1 w-full h-[calc(100vh-3.5rem)] relative">
        <MemoryGraph
          nodes={nodes}
          edges={edges}
          isLoading={loading}
        />
      </main>
    </div>
  );
}

export default App;
