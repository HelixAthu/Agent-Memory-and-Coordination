import { memo } from "react";
import { Handle, Position, NodeProps } from "@xyflow/react";
import { Badge } from "../ui/badge";

export const EpisodeNode = memo(({ data }: NodeProps) => {
  const props = (data?.props as Record<string, any>) || {};
  const summary = props.summary || data?.id || "Episode";
  const importance = props.importance !== undefined ? Number(props.importance).toFixed(2) : null;
  const isArchived = props.status === "ARCHIVED";

  return (
    <div
      className={`relative min-w-[190px] max-w-[240px] rounded-lg border bg-card p-2.5 shadow-sm transition-all ${
        isArchived ? "opacity-60 border-zinc-700" : "border-blue-700/70 hover:border-blue-500"
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-blue-500 !w-2 !h-2" />
      <div className="flex items-center justify-between gap-1 mb-1">
        <Badge variant="secondary" className="bg-blue-950 text-blue-300 border border-blue-700/60 text-[10px] px-1.5 py-0">
          Episode
        </Badge>
        {importance && (
          <span className="text-[10px] font-mono text-blue-400">★ {importance}</span>
        )}
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
  const isSuperseded = props.status === "SUPERSEDED";
  const predicate = props.predicate || "";
  const object = props.object || "";

  return (
    <div
      className={`relative min-w-[170px] max-w-[220px] rounded-lg border bg-card p-2.5 shadow-sm transition-all ${
        isSuperseded
          ? "border-zinc-800 bg-zinc-950/70 text-zinc-500"
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
  const name = props.name || data?.id || "Procedure";

  return (
    <div
      className={`relative min-w-[180px] max-w-[230px] rounded-lg border bg-card p-2.5 shadow-sm transition-all ${
        isCandidate
          ? "border-dashed border-purple-500/80 bg-purple-950/20"
          : "border-solid border-purple-600/80 hover:border-purple-400"
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-purple-500 !w-2 !h-2" />
      <div className="flex items-center justify-between gap-1 mb-1">
        <Badge
          variant="secondary"
          className={`text-[10px] px-1.5 py-0 ${
            isCandidate
              ? "bg-purple-950/60 text-purple-300 border border-dashed border-purple-500"
              : "bg-purple-900/60 text-purple-200 border border-purple-600"
          }`}
        >
          {isCandidate ? "Candidate" : "Procedure"}
        </Badge>
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
    <div className={`relative min-w-[150px] max-w-[200px] rounded-lg border bg-card p-2 shadow-sm ${style.border}`}>
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
