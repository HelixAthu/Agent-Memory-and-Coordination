import { useEffect, useMemo, type MouseEvent } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { GraphNode, GraphEdge } from "../types";
import { layoutGraph } from "../lib/layout";
import { nodeTypes } from "./canvas/nodeTypes";

interface MemoryGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick?: (event: MouseEvent, node: any) => void;
  isLoading?: boolean;
}

export function MemoryGraph({
  nodes,
  edges,
  onNodeClick,
  isLoading,
}: MemoryGraphProps): JSX.Element {
  const layout = useMemo(() => layoutGraph(nodes, edges), [nodes, edges]);

  const [flowNodes, setNodes, onNodesChange] = useNodesState(layout.nodes);
  const [flowEdges, setEdges, onEdgesChange] = useEdgesState(layout.edges);

  useEffect(() => {
    setNodes(layout.nodes);
    setEdges(layout.edges);
  }, [layout, setNodes, setEdges]);

  return (
    <div className="relative h-full w-full bg-slate-950 overflow-hidden">
      {isLoading && (
        <div className="absolute top-3 right-3 z-10 flex items-center gap-2 rounded bg-slate-900/90 px-3 py-1.5 text-xs text-blue-400 border border-blue-800 shadow">
          <span className="animate-spin">⟳</span> Loading memory graph...
        </div>
      )}
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.2}
        maxZoom={1.5}
      >
        <Background color="#1e293b" gap={18} size={1} variant={BackgroundVariant.Dots} />
        <Controls className="!bg-slate-900 !border-slate-800 !text-slate-200" />
        <MiniMap
          nodeColor={(n) => {
            if (n.type === "episode") return "#3b82f6";
            if (n.type === "fact") return "#10b981";
            if (n.type === "procedure") return "#a855f7";
            return "#64748b";
          }}
          className="!bg-slate-900 !border-slate-800"
          maskColor="rgba(15, 23, 42, 0.7)"
        />
      </ReactFlow>
    </div>
  );
}
