/** The offset to show: steps back to the last page when `offset` is past the end
 *  (e.g. the only row on the last page was just deleted), else `offset` unchanged. */
export function clampOffset(offset: number, total: number, limit: number): number {
  if (offset === 0 || offset < total) return offset;
  return Math.max(0, Math.floor((total - 1) / limit) * limit);
}
