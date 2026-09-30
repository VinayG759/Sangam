import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { CircleMarker, MapContainer, Popup, TileLayer, useMapEvents } from 'react-leaflet'
import type { LatLngBoundsExpression } from 'leaflet'
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
  // The area the data covers, with a margin: the map opens on it and cannot be dragged far away.
  const bounds = useMemo(() => {
    const all = query.data ?? []
    if (!all.length) return null
    const lats = all.map((p) => p.lat)
    const lons = all.map((p) => p.lon)
    const pad = 1.5 // degrees
    return {
      fit: [[Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]] as LatLngBoundsExpression,
      max: [[Math.min(...lats) - pad * 3, Math.min(...lons) - pad * 3], [Math.max(...lats) + pad * 3, Math.max(...lons) + pad * 3]] as LatLngBoundsExpression,
    }
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
          <MapContainer
            bounds={bounds?.fit}
            boundsOptions={{ padding: [24, 24] }}
            maxBounds={bounds?.max}
            maxBoundsViscosity={1}
            minZoom={5}
            maxZoom={12}
            worldCopyJump={false}
            scrollWheelZoom
            className="h-[60vh] min-h-[360px] w-full md:h-[560px]"
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
              noWrap
            />
            <Markers points={points} pack={pack.data} />
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

/**
 * Circle size follows the zoom: small dots when zoomed out (where hundreds overlap), growing
 * with how many residents reported as you zoom in. A thin ring in the surface colour keeps
 * overlapping dots apart.
 */
function Markers({ points, pack }: { points: MapPoint[]; pack: Parameters<typeof needLabel>[0] }) {
  const [zoom, setZoom] = useState<number | null>(null)
  const map = useMapEvents({ zoomend: () => setZoom(map.getZoom()) })
  const z = zoom ?? map.getZoom()
  const scale = z <= 6 ? 0.45 : z === 7 ? 0.7 : z === 8 ? 0.9 : 1.1
  return (
    <>
      {points.map((p) => (
        <CircleMarker
          key={p.priority_id}
          center={[p.lat, p.lon]}
          radius={Math.max(3, Math.min(18, (3 + Math.sqrt(p.distinct_reporters) * 1.3) * scale))}
          pathOptions={{
            color: '#ffffff',
            weight: z <= 6 ? 0.75 : 1.25,
            fillColor: VERDICTS[p.verdict].hex,
            fillOpacity: 0.85,
            dashArray: p.approximate ? '2 2' : undefined,
          }}
        >
          <Popup>
            <div className="text-[13px]">
              <div className="font-semibold">{p.region_name}</div>
              <div>{needLabel(pack, p.sector)} · {VERDICTS[p.verdict].label}</div>
              <div>{formatNumber(p.distinct_reporters)} residents · rank {p.rank}</div>
              {p.approximate && <div className="text-[11px] opacity-70">Shown at the containing area's centre</div>}
              <Link to={`/priorities/${p.priority_id}`}>Open evidence →</Link>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </>
  )
}
