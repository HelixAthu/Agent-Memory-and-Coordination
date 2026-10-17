import { useState, useEffect } from "react";
import {
  BookOpen,
  Calendar,
  Database,
  History,
  Layers,
  Sparkles,
  GitPullRequest,
  CheckSquare,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../ui/tabs";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { fetchEpisodes, fetchFacts, fetchProcedures, fetchTasks, fetchHandoffs } from "../../lib/api";
import { Episode, Fact, Procedure, Task, Handoff } from "../../types";
import { ProofPanel } from "./ProofPanel";

interface MemoryTabsProps {
  tenant: string;
  userId: string;
  onSelectNode?: (nodeId: string) => void;
}

export function MemoryTabs({ tenant, userId, onSelectNode }: MemoryTabsProps): JSX.Element {
  const [activeTab, setActiveTab] = useState<string>("episodic");

  // Tab Data States
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [showHistory, setShowHistory] = useState<boolean>(false);
  const [procedures, setProcedures] = useState<Procedure[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    let isCurrent = true;
    const loadData = async () => {
      setLoading(true);
      try {
        if (activeTab === "episodic") {
          const eps = await fetchEpisodes(tenant, userId);
          if (isCurrent) setEpisodes(eps);
        } else if (activeTab === "semantic") {
          const fcts = await fetchFacts(tenant, userId, showHistory);
          if (isCurrent) setFacts(fcts);
        } else if (activeTab === "procedural") {
          const procs = await fetchProcedures(tenant);
          if (isCurrent) setProcedures(procs);
        } else if (activeTab === "coordination") {
          const [ts, hs] = await Promise.all([fetchTasks(tenant), fetchHandoffs(tenant)]);
          if (isCurrent) {
            setTasks(ts);
            setHandoffs(hs);
          }
        }
      } catch (err) {
        console.warn("Failed to load tab data:", err);
      } finally {
        if (isCurrent) setLoading(false);
      }
    };

    loadData();
    return () => {
      isCurrent = false;
    };
  }, [tenant, userId, activeTab, showHistory]);

  const formatDate = (epochSec: number) => {
    if (!epochSec) return "Aug 2026";
    const date = new Date(epochSec * 1000);
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  return (
    <div className="flex h-full flex-col bg-slate-900/40 overflow-hidden border-l border-border">
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex h-full flex-col">
        {/* Tab Headers */}
        <div className="border-b border-border bg-slate-900/80 px-2 py-1.5 shrink-0">
          <TabsList className="grid grid-cols-5 h-8 bg-slate-950/70 p-0.5">
            <TabsTrigger value="episodic" className="text-[11px] px-1 data-[state=active]:bg-blue-950/80 data-[state=active]:text-blue-300">
              Episodic
            </TabsTrigger>
            <TabsTrigger value="semantic" className="text-[11px] px-1 data-[state=active]:bg-emerald-950/80 data-[state=active]:text-emerald-300">
              Semantic
            </TabsTrigger>
            <TabsTrigger value="procedural" className="text-[11px] px-1 data-[state=active]:bg-purple-950/80 data-[state=active]:text-purple-300">
              Procedural
            </TabsTrigger>
            <TabsTrigger value="coordination" className="text-[11px] px-1 data-[state=active]:bg-amber-950/80 data-[state=active]:text-amber-300">
              Coord
            </TabsTrigger>
            <TabsTrigger value="proof" className="text-[11px] px-1 data-[state=active]:bg-rose-950/80 data-[state=active]:text-rose-300">
              Proof
            </TabsTrigger>
          </TabsList>
        </div>

        {/* Tab Content Container */}
        <div className="flex-1 overflow-y-auto p-3">
          {loading && (
            <div className="flex items-center justify-center p-4 text-xs text-muted-foreground animate-pulse">
              Loading memory items...
            </div>
          )}

          {/* 1. Episodic Tab */}
          <TabsContent value="episodic" className="m-0 space-y-3">
            <div className="flex items-center justify-between pb-1 border-b border-border">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                <BookOpen className="h-3.5 w-3.5 text-blue-400" />
                Episodic Timeline
              </span>
              <Badge variant="outline" className="text-[10px]">
                {episodes.length} episodes
              </Badge>
            </div>

            <div className="relative pl-3 space-y-3 border-l border-slate-800">
              {episodes.map((ep) => {
                const isArchived = ep.status === "ARCHIVED";
                const importancePct = Math.round((ep.importance || 0.5) * 100);

                return (
                  <div
                    key={ep.id}
                    onClick={() => onSelectNode && onSelectNode(ep.id)}
                    className={`relative rounded-lg border p-2.5 transition-all cursor-pointer hover:border-blue-500/80 ${
                      isArchived
                        ? "bg-slate-950/40 border-slate-850 opacity-60 text-slate-400"
                        : "bg-slate-900/60 border-slate-800 text-slate-200"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1 mb-1">
                      <div className="flex items-center gap-1 text-[11px] font-mono text-slate-400">
                        <Calendar className="h-3 w-3" />
                        <span>{formatDate(ep.created_at)}</span>
                      </div>
                      <Badge
                        variant="secondary"
                        className={`text-[9px] px-1 py-0 ${
                          isArchived
                            ? "bg-zinc-800 text-zinc-400"
                            : "bg-blue-950 text-blue-300 border border-blue-700/60"
                        }`}
                      >
                        {ep.status}
                      </Badge>
                    </div>

                    <p className="text-xs font-medium leading-relaxed mb-2">
                      {ep.summary}
                    </p>

                    {/* Importance Bar */}
                    <div className="space-y-1">
                      <div className="flex justify-between text-[10px] text-muted-foreground font-mono">
                        <span>Importance</span>
                        <span>{importancePct}%</span>
                      </div>
                      <div className="h-1.5 w-full bg-slate-950 rounded-full overflow-hidden border border-slate-800">
                        <div
                          className="h-full bg-blue-500 rounded-full transition-all"
                          style={{ width: `${importancePct}%` }}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </TabsContent>

          {/* 2. Semantic Tab */}
          <TabsContent value="semantic" className="m-0 space-y-3">
            <div className="flex items-center justify-between pb-1 border-b border-border">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                <Database className="h-3.5 w-3.5 text-emerald-400" />
                Semantic Facts
              </span>
              <Button
                variant="ghost"
                size="sm"
                className={`h-6 text-[10px] px-2 gap-1 ${showHistory ? "text-emerald-400 bg-emerald-950/40" : "text-muted-foreground"}`}
                onClick={() => setShowHistory(!showHistory)}
              >
                <History className="h-3 w-3" />
                {showHistory ? "Hide History" : "Show History"}
              </Button>
            </div>

            <div className="space-y-2">
              {facts.map((f) => {
                const isSuperseded = f.status === "SUPERSEDED";
                const confPct = Math.round((f.confidence || 1.0) * 100);

                return (
                  <div
                    key={f.id}
                    onClick={() => onSelectNode && onSelectNode(f.id)}
                    className={`rounded-lg border p-2.5 transition-all cursor-pointer ${
                      isSuperseded
                        ? "bg-slate-950/40 border-slate-850 opacity-50 grayscale"
                        : "bg-slate-900/60 border-slate-800 hover:border-emerald-500/80"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1 mb-1">
                      <span className={`text-xs font-mono font-semibold ${isSuperseded ? "line-through text-slate-500" : "text-emerald-400"}`}>
                        {f.predicate}
                      </span>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] font-mono text-muted-foreground">
                          {confPct}% conf
                        </span>
                        <Badge
                          variant="secondary"
                          className={`text-[9px] px-1 py-0 ${
                            isSuperseded
                              ? "bg-zinc-800 text-zinc-400 line-through"
                              : "bg-emerald-950 text-emerald-300 border border-emerald-700/60"
                          }`}
                        >
                          {f.status}
                        </Badge>
                      </div>
                    </div>
                    <p className={`text-xs ${isSuperseded ? "line-through text-slate-500" : "text-foreground font-medium"}`}>
                      {f.object}
                    </p>
                  </div>
                );
              })}
            </div>
          </TabsContent>

          {/* 3. Procedural Tab */}
          <TabsContent value="procedural" className="m-0 space-y-3">
            <div className="flex items-center justify-between pb-1 border-b border-border">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                <Layers className="h-3.5 w-3.5 text-purple-400" />
                Procedures
              </span>
              <Badge variant="outline" className="text-[10px]">
                {procedures.length} total
              </Badge>
            </div>

            <div className="space-y-3">
              {procedures.map((p) => {
                const isCandidate = p.status === "CANDIDATE";
                const progressPct = Math.min(100, Math.round((p.successes / 2) * 100));

                return (
                  <div
                    key={p.id}
                    onClick={() => onSelectNode && onSelectNode(p.id)}
                    className={`rounded-lg border p-2.5 transition-all cursor-pointer ${
                      isCandidate
                        ? "border-dashed border-purple-500/70 bg-purple-950/20"
                        : "border-purple-600/70 bg-slate-900/60 hover:border-purple-400"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1 mb-1">
                      <h4 className="text-xs font-bold text-foreground truncate">
                        {p.name}
                      </h4>
                      <Badge
                        variant="secondary"
                        className={`text-[9px] px-1 py-0 ${
                          isCandidate
                            ? "bg-purple-950/60 text-purple-300 border border-dashed border-purple-500"
                            : "bg-purple-900 text-purple-200 border border-purple-600"
                        }`}
                      >
                        {p.status}
                      </Badge>
                    </div>

                    <p className="text-[11px] text-muted-foreground italic mb-2">
                      When: {p.situation}
                    </p>

                    {/* Steps List */}
                    <div className="mb-2 space-y-1">
                      <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">
                        Steps:
                      </span>
                      <ol className="list-decimal list-inside text-[11px] text-slate-300 space-y-0.5">
                        {p.steps.map((s, idx) => (
                          <li key={idx} className="truncate">{s}</li>
                        ))}
                      </ol>
                    </div>

                    {/* Promotion Progress (for Candidates) */}
                    {isCandidate && (
                      <div className="space-y-1 pt-1 border-t border-purple-950">
                        <div className="flex justify-between text-[10px] text-purple-300 font-mono">
                          <span className="flex items-center gap-1">
                            <Sparkles className="h-3 w-3 text-purple-400" /> Promotion Progress
                          </span>
                          <span>{p.successes} / 2 successes</span>
                        </div>
                        <div className="h-1.5 w-full bg-purple-950 rounded-full overflow-hidden border border-purple-900">
                          <div
                            className="h-full bg-purple-500 rounded-full transition-all"
                            style={{ width: `${progressPct}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </TabsContent>

          {/* 4. Coordination Tab */}
          <TabsContent value="coordination" className="m-0 space-y-4">
            {/* Tasks Section */}
            <div className="space-y-2">
              <div className="flex items-center justify-between pb-1 border-b border-border">
                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                  <CheckSquare className="h-3.5 w-3.5 text-amber-400" />
                  Task Queue
                </span>
                <Badge variant="outline" className="text-[10px]">
                  {tasks.length} tasks
                </Badge>
              </div>

              <div className="space-y-1.5">
                {tasks.map((t) => (
                  <div
                    key={t.id}
                    className="flex items-center justify-between p-2 rounded bg-slate-900/60 border border-slate-800 text-xs"
                  >
                    <div className="flex flex-col gap-0.5 truncate pr-2">
                      <span className="font-medium text-foreground truncate">{t.title}</span>
                      <span className="text-[10px] text-muted-foreground font-mono">
                        priority: {t.priority} {t.claimed_by ? `· by ${t.claimed_by}` : ""}
                      </span>
                    </div>
                    <Badge
                      variant="secondary"
                      className={`text-[9px] px-1 py-0 shrink-0 ${
                        t.status === "DONE"
                          ? "bg-emerald-950 text-emerald-300 border border-emerald-700/60"
                          : t.status === "CLAIMED"
                          ? "bg-amber-950 text-amber-300 border border-amber-700/60"
                          : "bg-slate-800 text-slate-300 border border-slate-700"
                      }`}
                    >
                      {t.status}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>

            {/* Handoffs Section */}
            <div className="space-y-2">
              <div className="flex items-center justify-between pb-1 border-b border-border">
                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                  <GitPullRequest className="h-3.5 w-3.5 text-pink-400" />
                  Handoff Protocol
                </span>
                <Badge variant="outline" className="text-[10px]">
                  {handoffs.length} logged
                </Badge>
              </div>

              <div className="space-y-2">
                {handoffs.map((h) => (
                  <div
                    key={h.id}
                    className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 text-xs space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-pink-300 font-semibold text-[11px]">
                        {h.from_agent} ➔ {h.to_agent}
                      </span>
                      <Badge
                        variant="secondary"
                        className={`text-[9px] px-1 py-0 ${
                          h.status === "COMPLETED"
                            ? "bg-emerald-950 text-emerald-300 border-emerald-700/60"
                            : h.status === "ACCEPTED"
                            ? "bg-blue-950 text-blue-300 border-blue-700/60"
                            : "bg-pink-950 text-pink-300 border-pink-700/60"
                        }`}
                      >
                        {h.status}
                      </Badge>
                    </div>
                    {h.context_summary && (
                      <p className="text-[11px] text-muted-foreground line-clamp-2">
                        {h.context_summary}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </TabsContent>

          {/* 5. Proof Tab */}
          <TabsContent value="proof" className="m-0 space-y-3">
            <ProofPanel tenant={tenant} />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
