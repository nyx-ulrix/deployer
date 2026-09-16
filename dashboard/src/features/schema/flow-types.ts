import type { Edge, Node } from "@xyflow/react";
import type { Entity, SourceSchema } from "../../api/types";
import type { GraphEdgeInfo } from "./graph";

export type EntityNodeData = {
  source: Pick<SourceSchema, "source_id" | "name" | "kind" | "engine">;
  entity: Entity;
  issueCount: number;
  issueFields: string[];
  highlight: boolean;
  dimmed: boolean;
  focusField: string | null;
};

export type EntityFlowNode = Node<EntityNodeData, "entity">;

export type SourceGroupData = {
  label: string;
  kind: "sql" | "nosql";
  engine: string;
  width: number;
  height: number;
};

export type SourceGroupFlowNode = Node<SourceGroupData, "sourceGroup">;

export type SchemaFlowNode = EntityFlowNode | SourceGroupFlowNode;

export type RelationEdgeData = {
  info: GraphEdgeInfo;
  highlighted: boolean;
  dimmed: boolean;
};

export type RelationFlowEdge = Edge<RelationEdgeData, "relation">;

export const ENTITY_HANDLE = "__entity";
