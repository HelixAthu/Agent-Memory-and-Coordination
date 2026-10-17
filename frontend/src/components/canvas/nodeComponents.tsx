import { memo } from "react";
import { Handle, Position, NodeProps } from "@xyflow/react";
import { Badge } from "../ui/badge";

export const EpisodeNode = memo(({ data }: NodeProps) => {
  const props = (data?.props as Record<string, any>) || {};
  const summary = props.summary || data?.id || "Episode";
  const importance = props.importance !== undefined ? Number(props.importance).toFixed(2) : null;
  const isArchived = props.status === "ARCHIVED";
  const isVisited = !!data?.isVisited;
  const recallScore = typeof data?.recallScore === "number" ? data.recallScore : null;

  const glowStyle = recallScore !== null
    ? {
        boxShadow: `0 0 ${Math.max(10, Math.round(recallScore * 25))}px rgba(59, 130, 246, 0.85)`,
      }
    : undefined;

  return (
    <div
      style={glowStyle}
      className={`relative min-w-[190px] max-w-[240px] rounded-lg border bg-card p-2.5 shadow-sm transition-all duration-300 ${
        isVisited ? "ring-2 ring-purple-400 ring-offset-2 ring-offset-slate-950 animate-pulse" : ""
      } ${
        isArchived ? "opacity-50 border-zinc-700" : "border-blue-700/70 hover:border-blue-500"
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-blue-500 !w-2 !h-2" />
      <div className="flex items-center justify-between gap-1 mb-1">
        <Badge variant="secondary" className="bg-blue-950 text-blue-300 border border-blue-700/60 text-[10px] px-1.5 py-0">
          Episode
        </Badge>
        <div className="flex items-center gap-1">
          {recallScore !== null && (
            <span className="text-[9px] font-mono bg-blue-600/30 text-blue-200 px-1 py-0.2 rounded border border-blue-500/50">
              {(recallScore * 100).toFixed(0)}%
            </span>
          )}
          {importance && (
            <span className="text-[10px] font-mono text-blue-400">★ {importance}</span>
          )}
        </div>
      </div>
      <p className="text-xs text-foreground font-medium line-clamp-2 leading-snug">
        {summary}
      </p>
      <Handle type="source" position={Position.Right} className="!bg-blue-500 !w-2 !h-2" />
    </div>
  );
});
EpisodeNode.displayName = "EpisodeNode";

export const FactNode = memo(({ data }: NodeProps) => {
  const props = (data?.props as Record<string, any>) || {};
  const isSuperseded = props.status === "SUPERSEDED" || !!data?.isSuperseded;
  const isVisited = !!data?.isVisited;
  const predicate = props.predicate || "";
  const object = props.object || "";

  return (
    <div
      className={`relative min-w-[170px] max-w-[220px] rounded-lg border bg-card p-2.5 shadow-sm transition-all duration-500 ${
        isVisited ? "ring-2 ring-purple-400 ring-offset-2 ring-offset-slate-950 animate-pulse" : ""
      } ${
        isSuperseded
          ? "border-zinc-800 bg-zinc-950/70 text-zinc-500 opacity-50 grayscale"
          : "border-emerald-700/70 hover:border-emerald-500"
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-emerald-500 !w-2 !h-2" />
      <div className="flex items-center justify-between gap-1 mb-1">
        <Badge
          variant="secondary"
          className={`text-[10px] px-1.5 py-0 ${
            isSuperseded
              ? "bg-zinc-800 text-zinc-400 border border-zinc-700 line-through"
              : "bg-emerald-950 text-emerald-300 border border-emerald-700/60"
          }`}
        >
          {isSuperseded ? "Superseded" : "Fact"}
        </Badge>
        {props.confidence !== undefined && (
          <span className="text-[10px] font-mono text-muted-foreground">
            {Math.round(Number(props.confidence) * 100)}%
          </span>
        )}
      </div>
      <div className="text-xs font-mono">
        <span className={isSuperseded ? "line-through text-zinc-500" : "text-emerald-400 font-semibold"}>
          {predicate}
        </span>
        <span className="text-muted-foreground">: </span>
        <span className={isSuperseded ? "line-through text-zinc-500" : "text-foreground"}>
          {object}
        </span>
      </div>
      <Handle type="source" position={Position.Right} className="!bg-emerald-500 !w-2 !h-2" />
    </div>
  );
});
FactNode.displayName = "FactNode";

export const ProcedureNode = memo(({ data }: NodeProps) => {
  const props = (data?.props as Record<string, any>) || {};
  const isCandidate = props.status === "CANDIDATE";
  const isVisited = !!data?.isVisited;
  const isPromoted = !!data?.isPromoted || props.status === "ACTIVE";
  const name = props.name || data?.id || "Procedure";

  return (
    <div
      className={`relative min-w-[180px] max-w-[230px] rounded-lg border bg-card p-2.5 shadow-sm transition-all duration-300 ${
        isVisited ? "ring-2 ring-purple-400 ring-offset-2 ring-offset-slate-950 animate-pulse" : ""
      } ${
        isCandidate && !isPromoted
          ? "border-dashed border-purple-500/80 bg-purple-950/20"
          : "border-solid border-purple-500 hover:border-purple-300 shadow-purple-950/50 shadow-md"
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-purple-500 !w-2 !h-2" />
      <div className="flex items-center justify-between gap-1 mb-1">
        <div className="flex items-center gap-1">
          <Badge
            variant="secondary"
            className={`text-[10px] px-1.5 py-0 ${
              isCandidate && !isPromoted
                ? "bg-purple-950/60 text-purple-300 border border-dashed border-purple-500"
                : "bg-purple-900 text-purple-200 border border-purple-500 font-semibold"
            }`}
          >
            {isPromoted ? "Active" : isCandidate ? "Candidate" : "Procedure"}
          </Badge>
          {isPromoted && (
            <span className="animate-bounce bg-emerald-500 text-black text-[9px] font-bold px-1 rounded">
              PROMOTED
            </span>
          )}
        </div>
        <span className="text-[10px] font-mono text-purple-400">
          ✓ {props.successes ?? 0}
        </span>
      </div>
      <p className="text-xs font-medium text-foreground truncate">
        {name}
      </p>
      <Handle type="source" position={Position.Right} className="!bg-purple-500 !w-2 !h-2" />
    </div>
  );
});
ProcedureNode.displayName = "ProcedureNode";

export const GenericNode = memo(({ data }: NodeProps) => {
  const label = (data?.label as string) || "Node";
  const id = (data?.id as string) || "";
  const props = (data?.props as Record<string, any>) || {};
  const isVisited = !!data?.isVisited;

  const getStyle = () => {
    switch (label) {
      case "User":
        return { badge: "bg-indigo-950 text-indigo-300 border-indigo-700/60", border: "border-indigo-700/70" };
      case "Session":
        return { badge: "bg-cyan-950 text-cyan-300 border-cyan-700/60", border: "border-cyan-700/70" };
      case "Agent":
        return { badge: "bg-amber-950 text-amber-300 border-amber-700/60", border: "border-amber-700/70" };
      case "Task":
        return { badge: "bg-yellow-950 text-yellow-300 border-yellow-700/60", border: "border-yellow-700/70" };
      case "Handoff":
        return { badge: "bg-pink-950 text-pink-300 border-pink-700/60", border: "border-pink-700/70" };
      case "Entity":
        return { badge: "bg-teal-950 text-teal-300 border-teal-700/60", border: "border-teal-700/70" };
      default:
        return { badge: "bg-zinc-800 text-zinc-300 border-zinc-700", border: "border-zinc-700" };
    }
  };

  const style = getStyle();
  const title = props.name || props.title || id;

  return (
    <div
      className={`relative min-w-[150px] max-w-[200px] rounded-lg border bg-card p-2 shadow-sm transition-all duration-300 ${
        isVisited ? "ring-2 ring-purple-400 ring-offset-2 ring-offset-slate-950 animate-pulse" : ""
      } ${style.border}`}
    >
      <Handle type="target" position={Position.Left} className="!bg-slate-400 !w-2 !h-2" />
      <div className="flex items-center justify-between gap-1 mb-1">
        <Badge variant="secondary" className={`${style.badge} border text-[10px] px-1.5 py-0`}>
          {label}
        </Badge>
        {props.status && (
          <span className="text-[10px] font-mono text-muted-foreground">{props.status}</span>
        )}
      </div>
      <p className="text-xs font-medium text-foreground truncate">{title}</p>
      <Handle type="source" position={Position.Right} className="!bg-slate-400 !w-2 !h-2" />
    </div>
  );
});
GenericNode.displayName = "GenericNode";
