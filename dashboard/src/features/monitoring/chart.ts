/**
 * SVG path for a line chart of `values` in a `width` x `height` box (y grows downwards).
 * `null` values leave gaps; `max` defaults to the largest value (at least 1).
 */
export function linePath(
  values: (number | null)[],
  width: number,
  height: number,
  max?: number,
): string {
  const top =
    max ?? Math.max(1, ...values.filter((v): v is number => v !== null));
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  let path = "";
  let pen = false;
  values.forEach((v, i) => {
    if (v === null) {
      pen = false;
      return;
    }
    const x = +(i * step).toFixed(2);
    const y = +(height - (Math.min(v, top) / top) * height).toFixed(2);
    path += `${pen ? "L" : "M"}${x} ${y}`;
    pen = true;
  });
  return path;
}
