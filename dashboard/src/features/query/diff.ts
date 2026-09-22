// Line diff for the conflict and version dialogs (QUERY_EDITOR.md → phase 2). Pure, so it is unit-tested.

export type DiffLine = { kind: "same" | "add" | "del"; text: string };

/** Above this many lines on either side the dialog says "too large to diff" instead of hanging the tab. */
export const DIFF_MAX_LINES = 5_000;

function lines(text: string): string[] {
  return text === "" ? [] : text.split("\n");
}

/**
 * `a` → `b` as a list of unchanged, added and removed lines (classic LCS). Returns null when either side is
 * over `DIFF_MAX_LINES`. The common prefix and suffix are stripped first, so the O(n·m) table only covers the
 * edited region — a typical save touches a few lines of a long document.
 */
export function lineDiff(a: string, b: string): DiffLine[] | null {
  const xs = lines(a);
  const ys = lines(b);
  if (xs.length > DIFF_MAX_LINES || ys.length > DIFF_MAX_LINES) return null;

  let start = 0;
  while (start < xs.length && start < ys.length && xs[start] === ys[start]) start++;
  let endX = xs.length;
  let endY = ys.length;
  while (endX > start && endY > start && xs[endX - 1] === ys[endY - 1]) {
    endX--;
    endY--;
  }

  const n = endX - start;
  const m = endY - start;
  // ponytail: full (n+1)·(m+1) table; capped sides keep it ≤ ~100 MB worst case. Switch to Myers if that bites.
  const width = m + 1;
  const table = new Uint32Array((n + 1) * width);
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      table[i * width + j] =
        xs[start + i] === ys[start + j] ? table[(i + 1) * width + j + 1] + 1 : Math.max(table[(i + 1) * width + j], table[i * width + j + 1]);
    }
  }

  const out: DiffLine[] = xs.slice(0, start).map((text) => ({ kind: "same", text }));
  let i = 0;
  let j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && xs[start + i] === ys[start + j]) {
      out.push({ kind: "same", text: xs[start + i] });
      i++;
      j++;
    } else if (i < n && (j === m || table[(i + 1) * width + j] >= table[i * width + j + 1])) {
      // Deletions before additions, the way people read a diff.
      out.push({ kind: "del", text: xs[start + i] });
      i++;
    } else {
      out.push({ kind: "add", text: ys[start + j] });
      j++;
    }
  }
  for (const text of xs.slice(endX)) out.push({ kind: "same", text });
  return out;
}

/** Counts for a "+3 −1" summary. */
export function diffStats(diff: readonly DiffLine[]): { add: number; del: number } {
  let add = 0;
  let del = 0;
  for (const l of diff) {
    if (l.kind === "add") add++;
    else if (l.kind === "del") del++;
  }
  return { add, del };
}
