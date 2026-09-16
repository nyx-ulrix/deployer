import { MARKER_LABEL, MARKER_NOTATION, markerPath, type EndMarker } from "./crowsfoot";

function MarkerSample({ kind }: { kind: EndMarker }) {
  const { lines, circle } = markerPath(kind, { x: 4, y: 10 }, { x: 1, y: 0 });
  return (
    <svg width="56" height="20" viewBox="0 0 56 20" aria-hidden="true" className="shrink-0">
      <line x1="4" y1="10" x2="54" y2="10" stroke="var(--edge)" strokeWidth="1.5" />
      <rect x="0" y="2" width="4" height="16" fill="var(--border-strong)" />
      <path d={lines} stroke="var(--fg)" strokeWidth="1.5" fill="none" strokeLinecap="round" />
      {circle && <circle cx={circle.x} cy={circle.y} r="4" fill="var(--surface)" stroke="var(--fg)" strokeWidth="1.5" />}
    </svg>
  );
}

function LineSample({ dash, color, width = 1.5 }: { dash?: string; color: string; width?: number }) {
  return (
    <svg width="56" height="12" viewBox="0 0 56 12" aria-hidden="true" className="shrink-0">
      <line x1="2" y1="6" x2="54" y2="6" stroke={color} strokeWidth={width} strokeDasharray={dash} strokeLinecap="round" />
    </svg>
  );
}

const FLAGS: { flag: string; className: string; meaning: string }[] = [
  { flag: "PK", className: "bg-warning-soft text-warning", meaning: "Primary key (_id for MongoDB)" },
  { flag: "FK", className: "bg-sql-soft text-sql", meaning: "Foreign key (declared constraint)" },
  { flag: "UQ", className: "bg-accent-soft text-accent", meaning: "Unique constraint / unique index" },
  { flag: "NN", className: "bg-surface-2 text-muted", meaning: "Not null" },
  { flag: "IDX", className: "bg-info-soft text-info", meaning: "Indexed (non-unique)" },
];

export function Legend() {
  return (
    <div className="space-y-4 p-3 text-sm">
      <section>
        <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">Entities</h3>
        <ul className="space-y-1.5">
          <li className="flex items-center gap-2">
            <span className="h-4 w-8 shrink-0 rounded border-t-4 border-t-sql bg-sql-soft" /> SQL table (header shows
            engine · source)
          </li>
          <li className="flex items-center gap-2">
            <span className="h-4 w-8 shrink-0 rounded border-t-4 border-t-nosql bg-nosql-soft" /> NoSQL collection
          </li>
          <li className="flex items-center gap-2">
            <span className="w-8 shrink-0 text-center font-mono font-bold text-warning">?</span> Mongo field present in
            fewer than 100% of sampled documents
          </li>
        </ul>
      </section>
      <section>
        <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">Field badges</h3>
        <ul className="space-y-1.5">
          {FLAGS.map((f) => (
            <li key={f.flag} className="flex items-center gap-2">
              <span className={`w-8 shrink-0 rounded px-1 text-center text-[10px] leading-4 font-bold ${f.className}`}>
                {f.flag}
              </span>
              {f.meaning}
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">Lines</h3>
        <ul className="space-y-1.5">
          <li className="flex items-center gap-2">
            <LineSample color="var(--edge)" /> Declared relationship (SQL foreign key)
          </li>
          <li className="flex items-center gap-2">
            <LineSample color="var(--edge)" dash="6 4" /> Inferred (naming convention / Mongo reference)
          </li>
          <li className="flex items-center gap-2">
            <LineSample color="var(--link)" dash="1 5" width={2.25} /> Cross-database link (declared by a user)
          </li>
        </ul>
      </section>
      <section>
        <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">Line ends (crow's foot)</h3>
        <ul className="space-y-1.5">
          {(["one", "zero_or_one", "one_or_many", "zero_or_many"] as EndMarker[]).map((k) => (
            <li key={k} className="flex items-center gap-2">
              <MarkerSample kind={k} />
              <code className="w-6 font-mono text-xs text-muted">{MARKER_NOTATION[k]}</code>
              {MARKER_LABEL[k]}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted">
          The symbol next to an entity tells how many of its rows relate to one row at the other end of the line.
        </p>
      </section>
    </div>
  );
}
