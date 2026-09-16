import dagre from "@dagrejs/dagre";
import { readJson, writeStorage } from "../../lib/storage";
import { estimateHeight, NODE_WIDTH, type Graph, type XY } from "./graph";

const GROUP_GAP = 160;
const GROUP_PADDING = 32;

/**
 * Auto-layout with dagre, one source at a time so each database forms its own cluster, then place the
 * clusters left to right. Entities without relationships are arranged in a grid under their cluster.
 */
export function autoLayout(graph: Graph): Record<string, XY> {
  const positions: Record<string, XY> = {};
  const bySource = new Map<string, Graph["nodes"]>();
  for (const n of graph.nodes) {
    const list = bySource.get(n.source.source_id) ?? [];
    list.push(n);
    bySource.set(n.source.source_id, list);
  }

  let offsetX = 0;
  for (const [sourceId, nodes] of bySource) {
    const ids = new Set(nodes.map((n) => n.id));
    const heights = new Map(nodes.map((n) => [n.id, estimateHeight(n.entity)]));
    const intra = graph.edges.filter(
      (e) => e.from.sourceId === sourceId && e.to.sourceId === sourceId && e.from.nodeId !== e.to.nodeId,
    );
    const connected = new Set<string>();
    for (const e of intra) {
      if (ids.has(e.from.nodeId) && ids.has(e.to.nodeId)) {
        connected.add(e.from.nodeId);
        connected.add(e.to.nodeId);
      }
    }

    const local: Record<string, XY> = {};
    let bottom = 0;
    let right = 0;

    if (connected.size > 0) {
      const g = new dagre.graphlib.Graph();
      g.setGraph({ rankdir: "RL", nodesep: 40, ranksep: 110, marginx: 0, marginy: 0 });
      g.setDefaultEdgeLabel(() => ({}));
      for (const id of connected) g.setNode(id, { width: NODE_WIDTH, height: heights.get(id) ?? 100 });
      for (const e of intra) {
        if (connected.has(e.from.nodeId) && connected.has(e.to.nodeId)) g.setEdge(e.from.nodeId, e.to.nodeId);
      }
      dagre.layout(g);
      for (const id of connected) {
        const n = g.node(id);
        const h = heights.get(id) ?? 100;
        const x = (n.x ?? 0) - NODE_WIDTH / 2;
        const y = (n.y ?? 0) - h / 2;
        local[id] = { x, y };
        bottom = Math.max(bottom, y + h);
        right = Math.max(right, x + NODE_WIDTH);
      }
    }

    const isolated = nodes.filter((n) => !connected.has(n.id));
    if (isolated.length > 0) {
      const cols = Math.max(1, Math.min(4, Math.ceil(Math.sqrt(isolated.length))));
      const startY = connected.size > 0 ? bottom + 80 : 0;
      const rowHeights: number[] = [];
      isolated.forEach((n, i) => {
        const row = Math.floor(i / cols);
        rowHeights[row] = Math.max(rowHeights[row] ?? 0, heights.get(n.id) ?? 100);
      });
      isolated.forEach((n, i) => {
        const row = Math.floor(i / cols);
        const col = i % cols;
        const y = startY + rowHeights.slice(0, row).reduce((a, b) => a + b + 40, 0);
        const x = col * (NODE_WIDTH + 40);
        local[n.id] = { x, y };
        right = Math.max(right, x + NODE_WIDTH);
      });
    }

    let minX = Infinity;
    for (const p of Object.values(local)) minX = Math.min(minX, p.x);
    if (!Number.isFinite(minX)) minX = 0;
    for (const [id, p] of Object.entries(local)) {
      positions[id] = { x: p.x - minX + offsetX, y: p.y };
    }
    offsetX += right - minX + GROUP_GAP + GROUP_PADDING;
  }
  return positions;
}

export const GROUP_PAD = GROUP_PADDING;

const storageKey = (projectId: string) => `deployer.schema.positions.${projectId}`;

export function loadPositions(projectId: string): Record<string, XY> {
  const data = readJson<Record<string, XY>>(storageKey(projectId));
  if (!data || typeof data !== "object") return {};
  const clean: Record<string, XY> = {};
  for (const [k, v] of Object.entries(data)) {
    if (v && typeof v.x === "number" && typeof v.y === "number") clean[k] = { x: v.x, y: v.y };
  }
  return clean;
}

export function savePositions(projectId: string, positions: Record<string, XY>): void {
  if (Object.keys(positions).length === 0) writeStorage(storageKey(projectId), null);
  else writeStorage(storageKey(projectId), JSON.stringify(positions));
}
