import { useQuery } from '@tanstack/react-query'
import { get, type Pack } from './api'

/** The active country pack. Loaded once and cached for the session. */
export function usePack() {
  return useQuery({ queryKey: ['pack'], queryFn: () => get<Pack>('/api/v1/pack'), staleTime: Infinity })
}

export function needLabel(pack: Pack | undefined, key: string): string {
  return pack?.needs.find((n) => n.key === key)?.label ?? key
}
