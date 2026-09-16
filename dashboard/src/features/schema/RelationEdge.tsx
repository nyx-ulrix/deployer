import { memo } from "react";
import { BaseEdge, getSmoothStepPath, Position, type EdgeProps } from "@xyflow/react";
import { describeEnds, markerPath, type EndMarker } from "./crowsfoot";
import type { RelationFlowEdge } from "./flow-types";

const STYLE = {
  fk: { stroke: "var(--edge)", dash: undefined, width: 1.5 },
  inferred: { stroke: "var(--edge)", dash: "6 4", width: 1.5 },
  link: { stroke: "var(--link)", dash: "1 5", width: 2.25 },
} as const;

function dirFor(position: Position) {
  switch (position) {
    case Position.Left:
      return { x: -1, y: 0 };
    case Position.Right:
      return { x: 1, y: 0 };
    case Position.Top:
      return { x: 0, y: -1 };
    case Position.Bottom:
      return { x: 0, y: 1 };
  }
}

function Marker({ kind, x, y, position, color }: { kind: EndMarker; x: number; y: number; position: Position; color: string }) {
  const { lines, circle } = markerPath(kind, { x, y }, dirFor(position));
  return (
    <g className="pointer-events-none">
      <path d={lines} stroke={color} strokeWidth={1.5} fill="none" strokeLinecap="round" />
      {circle && <circle cx={circle.x} cy={circle.y} r={4} fill="var(--bg)" stroke={color} strokeWidth={1.5} />}
    </g>
  );
}

function RelationEdgeImpl({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}: EdgeProps<RelationFlowEdge>) {
  if (!data) return null;
  const { info, highlighted, dimmed } = data;
  const style = STYLE[info.kind];
  const color = selected || highlighted ? "var(--accent)" : style.stroke;
  const [path] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 10,
    offset: 32,
  });
  const title =
    `${info.kind === "fk" ? "Foreign key" : info.kind === "inferred" ? "Inferred relationship" : "Cross-database link"}: ` +
    `${info.from.entity}.${info.from.field} → ${info.to.entity}.${info.to.field}\n` +
    describeEnds(info.from.entity, info.to.entity, info.ends) +
    (info.note ? `\n${info.note}` : "");

  return (
    <g style={{ opacity: dimmed ? 0.25 : 1 }}>
      <title>{title}</title>
      <BaseEdge
        id={id}
        path={path}
        className="erd-edge-path"
        interactionWidth={18}
        style={{
          stroke: color,
          strokeWidth: selected || highlighted ? style.width + 0.75 : style.width,
          strokeDasharray: style.dash,
          strokeLinecap: "round",
        }}
      />
      <Marker kind={info.ends.source} x={sourceX} y={sourceY} position={sourcePosition} color={color} />
      <Marker kind={info.ends.target} x={targetX} y={targetY} position={targetPosition} color={color} />
    </g>
  );
}

export const RelationEdge = memo(RelationEdgeImpl);
