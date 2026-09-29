/** Evenly spaced label positions that always include the last point, never crowding it. */
export function xTicks(count: number, maxLabels: number): number[] {
  if (count <= 0) return []
  const step = Math.max(1, Math.ceil(count / maxLabels))
  const ticks: number[] = []
  for (let i = 0; i < count; i += step) ticks.push(i)
  const last = count - 1
  if (ticks[ticks.length - 1] !== last) {
    if (last - ticks[ticks.length - 1] < step * 0.6 && ticks.length > 1) ticks.pop() // too close to the last label
    ticks.push(last)
  }
  return ticks
}
