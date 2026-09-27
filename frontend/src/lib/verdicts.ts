import type { Verdict } from './api'

export interface VerdictMeta {
  label: string
  action: 'Fund' | 'Audit' | 'Verify' | 'Monitor'
  meaning: string
  text: string // Tailwind text colour class
  soft: string // Tailwind background class
  hex: string // for the map, which can't use classes
}

export const VERDICTS: Record<Verdict, VerdictMeta> = {
  UNSERVED_GAP: {
    label: 'Unserved gap',
    action: 'Fund',
    meaning: 'Many residents report the problem and official data says the place is not served.',
    text: 'text-unserved',
    soft: 'bg-unserved-soft',
    hex: '#b42318',
  },
  DELIVERY_GAP: {
    label: 'Delivery gap',
    action: 'Audit',
    meaning: 'Official data says the place is served, but many residents say otherwise.',
    text: 'text-delivery',
    soft: 'bg-delivery-soft',
    hex: '#b54708',
  },
  STALLED_ALLOCATION: {
    label: 'Stalled allocation',
    action: 'Audit',
    meaning: 'Money is committed here, yet residents still report the problem.',
    text: 'text-stalled',
    soft: 'bg-stalled-soft',
    hex: '#7a3fb0',
  },
  DEMAND_HOTSPOT: {
    label: 'Demand hotspot',
    action: 'Verify',
    meaning: 'Many residents report the problem, but no official data is loaded yet to confirm the gap.',
    text: 'text-hotspot',
    soft: 'bg-hotspot-soft',
    hex: '#1d5fa8',
  },
  MONITOR: {
    label: 'Monitor',
    action: 'Monitor',
    meaning: 'Demand is close to the typical place.',
    text: 'text-monitor',
    soft: 'bg-monitor-soft',
    hex: '#8a8580',
  },
}

export const VERDICT_ORDER: Verdict[] = ['UNSERVED_GAP', 'DELIVERY_GAP', 'STALLED_ALLOCATION', 'DEMAND_HOTSPOT', 'MONITOR']

export type ActionGroup = 'all' | 'fund' | 'audit' | 'verify' | 'monitor'

export const ACTION_GROUPS: { key: ActionGroup; label: string; verdicts: Verdict[] }[] = [
  { key: 'all', label: 'All', verdicts: VERDICT_ORDER },
  { key: 'fund', label: 'Fund', verdicts: ['UNSERVED_GAP'] },
  { key: 'audit', label: 'Audit', verdicts: ['DELIVERY_GAP', 'STALLED_ALLOCATION'] },
  { key: 'verify', label: 'Verify', verdicts: ['DEMAND_HOTSPOT'] },
  { key: 'monitor', label: 'Monitor', verdicts: ['MONITOR'] },
]

export function inGroup(verdict: Verdict, group: ActionGroup): boolean {
  return (ACTION_GROUPS.find((g) => g.key === group) ?? ACTION_GROUPS[0]).verdicts.includes(verdict)
}
