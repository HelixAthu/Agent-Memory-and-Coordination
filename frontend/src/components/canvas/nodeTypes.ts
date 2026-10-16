import { NodeTypes } from "@xyflow/react";
import { EpisodeNode, FactNode, ProcedureNode, GenericNode } from "./nodeComponents";

export const nodeTypes: NodeTypes = {
  episode: EpisodeNode,
  fact: FactNode,
  procedure: ProcedureNode,
  user: GenericNode,
  session: GenericNode,
  agent: GenericNode,
  task: GenericNode,
  handoff: GenericNode,
  entity: GenericNode,
};
