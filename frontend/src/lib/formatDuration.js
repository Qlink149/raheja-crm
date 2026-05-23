/** Format seconds as "Xm Ys" or "Ys". */
export function formatDuration(seconds) {
  const n = Math.floor(Number(seconds) || 0);
  if (n <= 0) return "0s";
  const mins = Math.floor(n / 60);
  const secs = n % 60;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}
