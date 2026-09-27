import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { get, type Verdict } from '@/lib/api'
import { formatNumber } from '@/lib/format'
import { needLabel, usePack } from '@/lib/pack'
import { ACTION_GROUPS, type ActionGroup, inGroup, VERDICT_ORDER, VERDICTS } from '@/lib/verdicts'
import { PageHeader, Segmented } from '@/ui/primitives'
import { EmptyState, ErrorState, Skeleton } from '@/ui/states'

interface MapPoint {
  priority_id: number
  region_name: string
  lat: number
  lon: number
  approximate: boolean
  sector: string
  verdict: Verdict
  score: number
  rank: number
  distinct_reporters: number
  is_emerging: boolean
}

export default function MapPage() {
  const [params, setParams] = useSearchParams()
  const group = (params.get('group') as ActionGroup) || 'all'
  const pack = usePack()
  const query = useQuery({ queryKey: ['map'], queryFn: () => get<MapPoint[]>('/api/v1/map') })

  const points = useMemo(
    // Draw the most important last so they sit on top.
    () => (query.data ?? []).filter((p) => inGroup(p.verdict, group)).sort((a, b) => b.rank - a.rank),
    [query.data, group],
  )
  const center = useMemo<[number, number]>(() => {
    const all = query.data ?? []
    if (!all.length) return [20, 78]
    return [all.reduce((s, p) => s + p.lat, 0) / all.length, all.reduce((s, p) => s + p.lon, 0) / all.length]
  }, [query.data])

  return (
    <>
      <PageHeader
        title="Map"
        description="Each circle is one place and need. Colour is the verdict; size is how many distinct residents reported."
        actions={
          <Segmented
            label="Action"
            value={group}
            onChange={(value) => setParams(value === 'all' ? {} : { group: value }, { replace: true })}
            options={ACTION_GROUPS.map((g) => ({ value: g.key, label: g.label }))}
          />
        }
      />
      {query.isPending ? (
        <Skeleton className="h-[560px]" />
      ) : query.isError ? (
        <ErrorState error={query.error} />
      ) : !query.data.length ? (
        <EmptyState title="Nothing to map yet" />
      ) : (
        <div className="overflow-hidden rounded-lg border border-line">
          <MapContainer center={center} zoom={7} scrollWheelZoom className="h-[560px] w-full">
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {points.map((p) => (
              <CircleMarker
                key={p.priority_id}
                center={[p.lat, p.lon]}
                radius={Math.min(22, 4 + Math.sqrt(p.distinct_reporters) * 1.6)}
                pathOptions={{
                  color: VERDICTS[p.verdict].hex,
                  fillColor: VERDICTS[p.verdict].hex,
                  fillOpacity: 0.35,
                  weight: 1.5,
                  dashArray: p.approximate ? '3 3' : undefined,
                }}
              >
                <Popup>
                  <div className="text-[13px]">
                    <div className="font-semibold">{p.region_name}</div>
                    <div>{needLabel(pack.data, p.sector)} · {VERDICTS[p.verdict].label}</div>
                    <div>{formatNumber(p.distinct_reporters)} residents · rank {p.rank}</div>
                    {p.approximate && <div className="text-[11px] opacity-70">Shown at the containing area's centre</div>}
                    <Link to={`/priorities/${p.priority_id}`}>Open evidence →</Link>
                  </div>
                </Popup>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>
      )}
      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-muted">
        {VERDICT_ORDER.map((v) => (
          <li key={v} className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-full" style={{ background: VERDICTS[v].hex }} />
            {VERDICTS[v].label}
          </li>
        ))}
        <li className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-full border border-dashed border-muted" /> Location approximate
        </li>
      </ul>
    </>
  )
}
