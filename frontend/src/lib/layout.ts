import dagre from "@dagrejs/dagre";
import { type Node as FlowNode, type Edge as FlowEdge } from "@xyflow/react";
import { GraphNode, GraphEdge } from "../types";

export const NODE_WIDTH = 200;
export const NODE_HEIGHT = 70;
export const RANK_SEP = 70;
export const NODE_SEP = 30;

export interface GraphHighlightState {
  visitedNodeIds?: string[];
  visitedEdgeKeys?: string[];
  recallEpisodes?: Array<{ id: string; score: number }>;
  promotedProcedureId?: string | null;
}

export function getNodeRank(label: string): number {
  switch (label) {
    case "User":
      return 0;
    case "Session":
      return 1;
    case "Episode":
      return 2;
    case "Fact":
    case "Procedure":
      return 3;
    case "Entity":
      return 4;
    case "Agent":
    case "Handoff":
    case "Task":
      return 5;
    default:
      return 3;
  }
}

export function layoutGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  highlight?: GraphHighlightState
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setGraph({
    rankdir: "LR",
    ranksep: RANK_SEP,
    nodesep: NODE_SEP,
  });
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  for (const node of nodes) {
    dagreGraph.setNode(node.id, {
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      rank: getNodeRank(node.label),
    });
  }

  for (const edge of edges) {
    dagreGraph.setEdge(edge.source, edge.target);
  }

  dagre.layout(dagreGraph);

  const visitedSet = new Set(highlight?.visitedNodeIds || []);
  const visitedEdgeSet = new Set(highlight?.visitedEdgeKeys || []);
  const recallMap = new Map<string, number>();
  for (const ep of highlight?.recallEpisodes || []) {
    recallMap.set(ep.id, ep.score);
  }

  const flowNodes: FlowNode[] = nodes.map((n) => {
    const nodeWithPos = dagreGraph.node(n.id);
    const x = nodeWithPos ? nodeWithPos.x - NODE_WIDTH / 2 : 0;
    const y = nodeWithPos ? nodeWithPos.y - NODE_HEIGHT / 2 : 0;

    return {
      id: n.id,
      type: n.label.toLowerCase(),
      position: { x, y },
      data: {
        id: n.id,
        label: n.label,
        props: n.props || {},
        isVisited: visitedSet.has(n.id),
        recallScore: recallMap.get(n.id) ?? null,
        isPromoted: highlight?.promotedProcedureId === n.id,
        isSuperseded: n.props?.status === "SUPERSEDED",
        ...n.data,
      },
    };
  });

  const flowEdges: FlowEdge[] = edges.map((e) => {
    const edgeId = `${e.source}|${e.type}|${e.target}`;
    const isVisited = visitedEdgeSet.has(edgeId) || visitedEdgeSet.has(e.type);
    const isHandoff = e.type === "HANDOFF";
    const isSupersedes = e.type === "SUPERSEDES";

    let stroke = "#64748b";
    let strokeWidth = 1.5;
    let animated = e.animated ?? false;

    if (isHandoff) {
      stroke = "#ec4899";
      strokeWidth = 2.5;
      animated = true;
    } else if (isSupersedes) {
      stroke = "#ef4444";
      strokeWidth = 2;
    } else if (isVisited) {
      stroke = "#a855f7";
      strokeWidth = 2.5;
      animated = true;
    }

    return {
      id: edgeId,
      source: e.source,
      target: e.target,
      label: e.type,
      animated,
      style: {
        stroke,
        strokeWidth,
        strokeDasharray: isSupersedes ? "4 2" : undefined,
      },
      labelStyle: {
        fill: isHandoff ? "#f472b6" : isSupersedes ? "#f87171" : "#94a3b8",
        fontSize: 10,
        fontWeight: isHandoff || isSupersedes ? 600 : 500,
      },
      labelBgStyle: { fill: "#0f172a", fillOpacity: 0.85 },
    };
  });

  return { nodes: flowNodes, edges: flowEdges };
}
