import { useState, useRef, useEffect } from "react";
import {
  Activity,
  Terminal,
  Zap,
  ArrowRightLeft,
  Database,
  CheckCircle2,
  ChevronRight,
  ChevronDown,
  Eye,
} from "lucide-react";
import { Badge } from "../ui/badge";

interface TraceFeedProps {
  traces: any[];
}

export function TraceFeed({ traces }: TraceFeedProps): JSX.Element {
  const [expandedIndices, setExpandedIndices] = useState<Record<number, boolean>>({});
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [traces.length]);

  const toggleExpand = (index: number) => {
    setExpandedIndices((prev) => ({
      ...prev,
      [index]: !prev[index],
    }));
  };

  const getTraceBadge = (event: any) => {
    const type = event.type;
    const data = event.data || {};

    switch (type) {
      case "tool_call":
        return (
          <Badge variant="outline" className="bg-amber-950/60 text-amber-300 border-amber-700/60 text-[9px] px-1 py-0">
            Tool: {data.tool || data.name}
          </Badge>
        );
      case "tool_result":
        return (
          <Badge variant="outline" className="bg-slate-800 text-slate-300 border-slate-700 text-[9px] px-1 py-0">
            Result {data.is_error ? "(Error)" : "OK"}
          </Badge>
        );
      case "recall_result":
        return (
          <Badge variant="outline" className="bg-blue-950/60 text-blue-300 border-blue-700/60 text-[9px] px-1 py-0">
            Recall: {data.episodes?.length || 0} eps
          </Badge>
        );
      case "memory_visit":
        return (
          <Badge variant="outline" className="bg-purple-950/60 text-purple-300 border-purple-700/60 text-[9px] px-1 py-0">
            Visit: {data.node_ids?.length || 0} nodes
          </Badge>
        );
      case "handoff":
        return (
          <Badge variant="outline" className="bg-pink-950/60 text-pink-300 border-pink-700/60 text-[9px] px-1 py-0">
            Handoff {data.status}
          </Badge>
        );
      case "fact_update":
        return (
          <Badge variant="outline" className="bg-emerald-950/60 text-emerald-300 border-emerald-700/60 text-[9px] px-1 py-0">
            Fact: {data.predicate || data.action}
          </Badge>
        );
      case "procedure_event":
        return (
          <Badge variant="outline" className="bg-violet-950/60 text-violet-300 border-violet-700/60 text-[9px] px-1 py-0">
            Proc: {data.kind}
          </Badge>
        );
      case "agent_active":
        return (
          <Badge variant="outline" className="bg-cyan-950/60 text-cyan-300 border-cyan-700/60 text-[9px] px-1 py-0">
            Active: {data.agent_id}
          </Badge>
        );
      case "session_closed":
        return (
          <Badge variant="outline" className="bg-zinc-800 text-zinc-300 border-zinc-700 text-[9px] px-1 py-0">
            Closed
          </Badge>
        );
      case "final":
        return (
          <Badge variant="outline" className="bg-emerald-900/60 text-emerald-300 border-emerald-700 text-[9px] px-1 py-0">
            Final
          </Badge>
        );
      default:
        return (
          <Badge variant="outline" className="text-[9px] px-1 py-0">
            {type}
          </Badge>
        );
    }
  };

  const getTraceIcon = (type: string) => {
    switch (type) {
      case "tool_call":
        return <Terminal className="h-3 w-3 text-amber-400" />;
      case "recall_result":
        return <Zap className="h-3 w-3 text-blue-400" />;
      case "memory_visit":
        return <Eye className="h-3 w-3 text-purple-400" />;
      case "handoff":
        return <ArrowRightLeft className="h-3 w-3 text-pink-400" />;
      case "fact_update":
        return <Database className="h-3 w-3 text-emerald-400" />;
      case "procedure_event":
        return <CheckCircle2 className="h-3 w-3 text-violet-400" />;
      default:
        return <Activity className="h-3 w-3 text-slate-400" />;
    }
  };

  const formatSummary = (event: any): string => {
    const data = event.data || {};
    switch (event.type) {
      case "tool_call":
        return `${data.tool || data.name}(${data.args ? JSON.stringify(data.args).slice(0, 45) : ""})`;
      case "recall_result":
        return data.episodes?.[0] ? `Top candidate: ${data.episodes[0].id} (score ${Number(data.episodes[0].score).toFixed(2)})` : "No episodes recalled";
      case "memory_visit":
        return `Inspected [${(data.node_ids || []).slice(0, 3).join(", ")}]`;
      case "handoff":
        return `${data.from_agent} ➔ ${data.to_agent} (${data.status})`;
      case "fact_update":
        return `${data.predicate} = ${data.object || ""}`;
      case "procedure_event":
        return `${data.procedure_id}: ${data.kind}`;
      case "agent_active":
        return `Turn handed to ${data.agent_id} (${data.role || "specialist"})`;
      case "message":
        return `${data.role}: ${(data.text || "").slice(0, 50)}...`;
      case "final":
        return data.summary || "Turn completed";
      default:
        return JSON.stringify(data).slice(0, 50);
    }
  };

  return (
    <div className="flex h-full flex-col bg-slate-950/80">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2 bg-slate-900/60">
        <div className="flex items-center gap-1.5">
          <Activity className="h-4 w-4 text-purple-400" />
          <span className="text-xs font-semibold tracking-wide uppercase text-muted-foreground">
            Execution Trace
          </span>
        </div>
        <Badge variant="outline" className="text-[10px] font-mono">
          {traces.length} events
        </Badge>
      </div>

      {/* Stream List */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {traces.length === 0 ? (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
            Waiting for events...
          </div>
        ) : (
          traces.map((event, idx) => {
            const isExpanded = !!expandedIndices[idx];
            const hasPayload = event.data && Object.keys(event.data).length > 0;

            return (
              <div
                key={event.seq || idx}
                className="rounded border border-slate-800/80 bg-slate-900/50 p-2 text-xs transition-colors hover:border-slate-700"
              >
                <div className="flex items-center justify-between gap-1 mb-1">
                  <div className="flex items-center gap-1.5">
                    {getTraceIcon(event.type)}
                    {getTraceBadge(event)}
                  </div>
                  <span className="text-[10px] font-mono text-slate-500">
                    #{event.seq ?? idx + 1}
                  </span>
                </div>

                <div
                  className="flex items-center justify-between gap-2 text-[11px] text-slate-300 font-mono cursor-pointer"
                  onClick={() => hasPayload && toggleExpand(idx)}
                >
                  <span className="truncate">{formatSummary(event)}</span>
                  {hasPayload && (
                    <button className="text-slate-500 hover:text-slate-300 p-0.5">
                      {isExpanded ? (
                        <ChevronDown className="h-3 w-3" />
                      ) : (
                        <ChevronRight className="h-3 w-3" />
                      )}
                    </button>
                  )}
                </div>

                {isExpanded && hasPayload && (
                  <pre className="mt-2 rounded bg-slate-950 p-2 text-[10px] font-mono text-slate-400 overflow-x-auto border border-slate-850">
                    {JSON.stringify(event.data, null, 2)}
                  </pre>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
