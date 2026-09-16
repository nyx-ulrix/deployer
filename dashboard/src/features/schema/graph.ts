import type { ConventionIssue, Entity, Field, ProjectSchema, SourceSchema } from "../../api/types";
import { edgeEnds, type Cardinality, type EdgeEnds } from "./crowsfoot";

export const NODE_WIDTH = 280;
export const HEADER_HEIGHT = 50;
export const ROW_HEIGHT = 24;
export const NODE_PADDING = 8;

export type EdgeKind = "fk" | "inferred" | "link";

export type EntityRef = { nodeId: string; sourceId: string; entity: string; field: string };

export type GraphNodeInfo = {
  id: string;
  source: SourceSchema;
  entity: Entity;
  issues: ConventionIssue[];
};

export type GraphEdgeInfo = {
  id: string;
  kind: EdgeKind;
  from: EntityRef;
  to: EntityRef;
  cardinality: Cardinality;
  ends: EdgeEnds;
  linkId: string | null;
  note: string | null;
};

export type Graph = {
  nodes: GraphNodeInfo[];
  edges: GraphEdgeInfo[];
};

export function nodeIdFor(sourceId: string, entity: string): string {
  return `${sourceId}::${entity}`;
}

export function estimateHeight(entity: Entity): number {
  return HEADER_HEIGHT + Math.max(1, entity.fields.length) * ROW_HEIGHT + NODE_PADDING;
}

/** A Mongo field missing from some sampled documents behaves like a nullable column. */
export function isOptional(field: Field | undefined): boolean {
  if (!field) return true;
  return field.nullable || (field.occurrence !== null && field.occurrence < 1);
}

function findField(entity: Entity | undefined, name: string): Field | undefined {
  return entity?.fields.find((f) => f.name === name);
}

/** Build the ERD graph (entities + relationships + cross-database links) for the enabled sources. */
export function buildGraph(schema: ProjectSchema, enabledSources: ReadonlySet<string>): Graph {
  const nodes: GraphNodeInfo[] = [];
  const entityLookup = new Map<string, Entity>();
  const sources = schema.sources.filter((s) => enabledSources.has(s.source_id) && s.status === "ok");

  for (const source of sources) {
    for (const entity of source.entities) {
      const id = nodeIdFor(source.source_id, entity.name);
      entityLookup.set(id, entity);
      nodes.push({
        id,
        source,
        entity,
        issues: schema.conventions.filter((c) => c.source_id === source.source_id && c.entity === entity.name),
      });
    }
  }

  const edges: GraphEdgeInfo[] = [];
  const seen = new Set<string>();

  const pushRelationship = (
    source: SourceSchema,
    fromEntity: string,
    fromField: string,
    toEntity: string,
    toField: string,
    cardinality: "one_to_one" | "many_to_one",
    kind: "fk" | "inferred",
  ) => {
    const fromId = nodeIdFor(source.source_id, fromEntity);
    const toId = nodeIdFor(source.source_id, toEntity);
    const from = entityLookup.get(fromId);
    const to = entityLookup.get(toId);
    if (!from || !to) return;
    const key = `${fromId}.${fromField}->${toId}.${toField}`;
    if (seen.has(key)) return;
    seen.add(key);
    edges.push({
      id: `${kind}:${key}`,
      kind,
      from: { nodeId: fromId, sourceId: source.source_id, entity: fromEntity, field: fromField },
      to: { nodeId: toId, sourceId: source.source_id, entity: toEntity, field: toField },
      cardinality,
      ends: edgeEnds(cardinality, {
        fromNullable: isOptional(findField(from, fromField)),
        toNullable: isOptional(findField(to, toField)),
      }),
      linkId: null,
      note: null,
    });
  };

  for (const source of sources) {
    for (const rel of source.relationships) {
      const fromField = rel.from_fields[0];
      const toField = rel.to_fields[0];
      if (!fromField || !toField) continue;
      pushRelationship(
        source,
        rel.from_entity,
        fromField,
        rel.to_entity,
        toField,
        rel.cardinality,
        rel.origin === "foreign_key" ? "fk" : "inferred",
      );
    }
    // Declared FKs on fields that the API didn't list as relationships.
    for (const entity of source.entities) {
      for (const field of entity.fields) {
        if (!field.foreign_key) continue;
        pushRelationship(
          source,
          entity.name,
          field.name,
          field.foreign_key.entity,
          field.foreign_key.field,
          field.unique ? "one_to_one" : "many_to_one",
          "fk",
        );
      }
    }
  }

  for (const link of schema.links) {
    const fromId = nodeIdFor(link.from_source_id, link.from_entity);
    const toId = nodeIdFor(link.to_source_id, link.to_entity);
    const from = entityLookup.get(fromId);
    const to = entityLookup.get(toId);
    if (!from || !to) continue;
    edges.push({
      id: `link:${link.id}`,
      kind: "link",
      from: { nodeId: fromId, sourceId: link.from_source_id, entity: link.from_entity, field: link.from_field },
      to: { nodeId: toId, sourceId: link.to_source_id, entity: link.to_entity, field: link.to_field },
      cardinality: link.cardinality,
      ends: edgeEnds(link.cardinality, {
        fromNullable: isOptional(findField(from, link.from_field)),
        toNullable: isOptional(findField(to, link.to_field)),
      }),
      linkId: link.id,
      note: link.note,
    });
  }

  return { nodes, edges };
}

export type XY = { x: number; y: number };

/** Pick which side of each entity an edge attaches to, based on current positions. */
export function chooseSides(
  from: XY,
  to: XY,
  sameNode: boolean,
): { fromSide: "L" | "R"; toSide: "L" | "R" } {
  if (sameNode) return { fromSide: "R", toSide: "R" };
  const fromCenter = from.x + NODE_WIDTH / 2;
  const toCenter = to.x + NODE_WIDTH / 2;
  if (Math.abs(fromCenter - toCenter) < NODE_WIDTH * 0.6) {
    // Stacked vertically: route both on the right for a cleaner loop.
    return { fromSide: "R", toSide: "R" };
  }
  return fromCenter < toCenter ? { fromSide: "R", toSide: "L" } : { fromSide: "L", toSide: "R" };
}

export function handleId(field: string, side: "L" | "R"): string {
  return `${field}|${side}`;
}
