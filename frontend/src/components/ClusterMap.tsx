import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { Cluster } from '@/api'

interface ClusterMapProps {
  clusters: Cluster[];
  /** Called with a cluster's linked priority id when "View full details" is
   *  clicked in its popup. Optional -- the map still works standalone. */
  onViewDetails?: (priorityId: number) => void;
}

const VERDICT_COLORS: Record<string, string> = {
  UNSERVED_GAP:        '#ef4444',
  STALLED_ALLOCATION:  '#f97316',
  UNDERFUNDED_CRITICAL:'#eab308',
  DELIVERY_GAP:        '#8b5cf6',
  WELL_SERVED:         '#10b981',
}

const SECTOR_SYMBOLS: Record<string, string> = {
  water: '💧', roads: '🛣️', sanitation: '♻️',
  health: '🏥', education: '🏫', electricity: '⚡',
}

function parsePoint(wkt: string | null): [number, number] | null {
  if (!wkt) return null;
  const match = wkt.match(/POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)/i);
  if (match) {
    const lng = parseFloat(match[1]);
    const lat = parseFloat(match[2]);
    return [lat, lng];
  }
  return null;
}

function makeMarkerIcon(color: string, emoji: string) {
  return L.divIcon({
    className: '',
    iconSize: [32, 32],
    iconAnchor: [16, 16],
    popupAnchor: [0, -20],
    html: `
      <div style="
        width: 32px; height: 32px;
        border-radius: 50%;
        background: ${color};
        border: 2.5px solid rgba(255,255,255,0.5);
        box-shadow: 0 2px 12px ${color}60;
        display: flex; align-items: center; justify-content: center;
        font-size: 14px; line-height: 1;
        cursor: pointer;
      ">${emoji}</div>
    `,
  })
}

const EXPAND_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/></svg>`
const COLLAPSE_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3"/><path d="M21 8h-3a2 2 0 0 1-2-2V3"/><path d="M3 16h3a2 2 0 0 1 2 2v3"/><path d="M16 21v-3a2 2 0 0 1 2-2h3"/></svg>`
const RESET_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="2.5"/><path d="M12 2v4"/><path d="M12 18v4"/><path d="M2 12h4"/><path d="M18 12h4"/></svg>`
const LIST_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>`

export default function ClusterMap({ clusters, onViewDetails }: ClusterMapProps) {
  const wrapperRef   = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef       = useRef<L.Map | null>(null)
  const layerRef     = useRef<L.LayerGroup | null>(null)
  const boundsRef    = useRef<[number, number][]>([])
  const markersRef   = useRef<Map<number, L.Marker>>(new Map())
  const onViewDetailsRef = useRef(onViewDetails)
  onViewDetailsRef.current = onViewDetails

  const [showList, setShowList] = useState(false)

  // Initialize map once, on mount. This must run every time regardless of
  // whether `clusters` is empty on that first render -- previously the
  // container div itself was only rendered when clusters.length > 0 (see
  // the render below), so on a real page load (clusters starts as [] until
  // the parent's fetch resolves) this effect fired with
  // containerRef.current still null, found nothing to attach to, and
  // never got a second chance since its dependency array is empty. The
  // container is now always rendered (see below) so the ref is always
  // attached by the time this runs.
  useEffect(() => {
    const container = containerRef.current
    const wrapper = wrapperRef.current
    if (!container || !wrapper || mapRef.current) return

    const map = L.map(container, {
      center: [15.3173, 75.7139], // Karnataka, India
      zoom: 6,
      zoomControl: true,
    })

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '',
      maxZoom: 19,
    }).addTo(map)

    L.control.scale({ position: 'bottomright', imperial: false }).addTo(map)

    // Themed tooltip shared by all three custom controls below, replacing
    // the browser's plain native title="" tooltip -- everything else on
    // this map is custom-styled to match the dashboard's dark theme, and
    // an OS tooltip stood out as the one thing that wasn't.
    const tooltip = L.DomUtil.create('div', 'map-control-tooltip', wrapper)
    tooltip.style.display = 'none'
    function bindTooltip(a: HTMLAnchorElement, text: string) {
      L.DomEvent.on(a, 'mouseenter focus', () => {
        tooltip.textContent = text
        tooltip.style.display = 'block'
        const wrapperRect = wrapper!.getBoundingClientRect()
        const btnRect = a.getBoundingClientRect()
        tooltip.style.top = `${btnRect.top - wrapperRect.top + btnRect.height / 2}px`
        tooltip.style.right = `${wrapperRect.right - btnRect.left + 8}px`
      })
      L.DomEvent.on(a, 'mouseleave blur', () => {
        tooltip.style.display = 'none'
      })
    }

    // "Reset view" -- re-fits to the current cluster bounds. Useful after
    // a policymaker has panned/zoomed around looking at one region.
    const ResetControl = L.Control.extend({
      options: { position: 'topright' },
      onAdd() {
        const div = L.DomUtil.create('div', 'leaflet-bar leaflet-control')
        const a = L.DomUtil.create('a', '', div)
        a.href = '#'
        a.innerHTML = RESET_ICON
        a.style.display = 'flex'
        a.style.alignItems = 'center'
        a.style.justifyContent = 'center'
        L.DomEvent.disableClickPropagation(div)
        bindTooltip(a, 'Reset view')
        L.DomEvent.on(a, 'click', (e) => {
          L.DomEvent.preventDefault(e)
          if (boundsRef.current.length) {
            map.fitBounds(boundsRef.current, { padding: [40, 40], maxZoom: 9 })
          }
        })
        return div
      },
    })
    new ResetControl().addTo(map)

    // Fullscreen -- toggles the native Fullscreen API on the whole card
    // (map + legend), not just the tile layer, so the legend stays visible.
    // No plugin dependency -- the browser API is enough for a toggle button.
    let fullscreenBtn: HTMLAnchorElement
    const FullscreenControl = L.Control.extend({
      options: { position: 'topright' },
      onAdd() {
        const div = L.DomUtil.create('div', 'leaflet-bar leaflet-control')
        const a = L.DomUtil.create('a', '', div)
        a.href = '#'
        a.innerHTML = EXPAND_ICON
        a.style.display = 'flex'
        a.style.alignItems = 'center'
        a.style.justifyContent = 'center'
        L.DomEvent.disableClickPropagation(div)
        bindTooltip(a, 'Toggle fullscreen')
        L.DomEvent.on(a, 'click', (e) => {
          L.DomEvent.preventDefault(e)
          if (document.fullscreenElement === wrapper) {
            document.exitFullscreen()
          } else {
            wrapper.requestFullscreen().catch(() => {
              // Fullscreen can be denied (e.g. iframe without the
              // allowfullscreen attribute) -- fail quietly, the map is
              // still fully usable at its normal size.
            })
          }
        })
        fullscreenBtn = a
        return div
      },
    })
    new FullscreenControl().addTo(map)

    // "List all issues" -- toggles a React-rendered panel (below) listing
    // every cluster; clicking a row flies the map to it and opens its
    // popup. Kept in React state rather than raw DOM since the panel's
    // rows need real click handlers per row, not string-templated HTML.
    const ListControl = L.Control.extend({
      options: { position: 'topright' },
      onAdd() {
        const div = L.DomUtil.create('div', 'leaflet-bar leaflet-control')
        const a = L.DomUtil.create('a', '', div)
        a.href = '#'
        a.innerHTML = LIST_ICON
        a.style.display = 'flex'
        a.style.alignItems = 'center'
        a.style.justifyContent = 'center'
        L.DomEvent.disableClickPropagation(div)
        bindTooltip(a, 'List all issues')
        L.DomEvent.on(a, 'click', (e) => {
          L.DomEvent.preventDefault(e)
          setShowList(v => !v)
          tooltip.style.display = 'none'
        })
        return div
      },
    })
    new ListControl().addTo(map)

    const onFullscreenChange = () => {
      const isFullscreen = document.fullscreenElement === wrapper
      wrapper.classList.toggle('map-fullscreen', isFullscreen)
      fullscreenBtn.innerHTML = isFullscreen ? COLLAPSE_ICON : EXPAND_ICON
      // Leaflet must re-measure the container after the browser finishes
      // resizing it for fullscreen, and re-center on what was visible.
      requestAnimationFrame(() => {
        map.invalidateSize()
        if (boundsRef.current.length) {
          map.fitBounds(boundsRef.current, { padding: [40, 40], maxZoom: 9 })
        }
      })
    }
    document.addEventListener('fullscreenchange', onFullscreenChange)

    const layer = L.layerGroup().addTo(map)
    mapRef.current  = map
    layerRef.current = layer

    // "View full details" links live inside raw HTML popup content, so
    // they can't take a React onClick -- delegate via Leaflet's own
    // popupopen event instead.
    map.on('popupopen', (e) => {
      const el = e.popup.getElement()?.querySelector<HTMLElement>('[data-view-details]')
      if (!el) return
      el.addEventListener('click', (evt) => {
        evt.preventDefault()
        const id = Number(el.dataset.viewDetails)
        if (!Number.isNaN(id)) onViewDetailsRef.current?.(id)
      })
    })

    return () => {
      document.removeEventListener('fullscreenchange', onFullscreenChange)
      tooltip.remove()
      map.remove()
      mapRef.current  = null
      layerRef.current = null
    }
  }, [])

  // Update markers when clusters change
  useEffect(() => {
    if (!layerRef.current) return
    layerRef.current.clearLayers()
    markersRef.current.clear()

    if (!clusters.length) {
      boundsRef.current = []
      return
    }

    const bounds: [number, number][] = []

    clusters.forEach(c => {
      // Skip plotting clusters that don't have a centroid (due to aggregation floor)
      const coords = parsePoint(c.centroid);
      if (!coords) return;
      const [lat, lng] = coords;

      bounds.push([lat, lng])

      const verdict = c.priority?.verdict ?? 'WELL_SERVED'
      const color   = VERDICT_COLORS[verdict] ?? '#60a5fa'
      const emoji   = SECTOR_SYMBOLS[c.sector] ?? '📋'

      const marker = L.marker([lat, lng], { icon: makeMarkerIcon(color, emoji) })
      marker.bindPopup(`
        <div style="min-width: 180px;">
          <div style="font-weight: 700; font-size: 13px; margin-bottom: 6px; color: #f0f6ff;">${c.title}</div>
          <div style="font-size: 11px; color: #8ba4cc; margin-bottom: 4px;">
            ${c.region_name} · ${c.report_count} reports ${c.is_approximate_location ? '<br/><span style="color: #fbbf24;">(Approximate Location)</span>' : ''}
          </div>
          ${c.priority ? `
            <div style="display:flex; align-items:center; gap:6px; margin-top:8px;">
              <div style="width:8px;height:8px;border-radius:50%;background:${color};"></div>
              <span style="font-size:11px; color:${color}; font-weight:600;">
                ${verdict.replace('_', ' ')}
              </span>
              <span style="font-size:11px; color:#8ba4cc;">·</span>
              <span style="font-size:11px; color:#8ba4cc;">Score ${c.priority.score.toFixed(0)}</span>
            </div>
            ${onViewDetailsRef.current ? `
              <a href="#" data-view-details="${c.priority.id}" style="display:block; margin-top:10px; font-size:11px; font-weight:600; color:#60a5fa; text-decoration:none;">
                View full details →
              </a>
            ` : ''}
          ` : ''}
        </div>
      `)
      layerRef.current?.addLayer(marker)
      markersRef.current.set(c.id, marker)
    })

    boundsRef.current = bounds

    // Fit to bounds if we have markers
    if (bounds.length && mapRef.current) {
      try {
        mapRef.current.fitBounds(bounds, { padding: [40, 40], maxZoom: 9 })
      } catch {
        // ignore fitBounds errors when map not ready
      }
    }
  }, [clusters])

  function flyToCluster(c: Cluster) {
    const coords = parsePoint(c.centroid)
    if (!coords || !mapRef.current) return
    mapRef.current.flyTo(coords, 12, { duration: 1.2 })
    markersRef.current.get(c.id)?.openPopup()
    setShowList(false)
  }

  // Worst-first, matching how the rest of the dashboard ranks issues --
  // a policymaker scanning this list should see the most urgent one first.
  const sortedClusters = [...clusters].sort((a, b) => (b.priority?.score ?? 0) - (a.priority?.score ?? 0))

  return (
    <div ref={wrapperRef} style={{ position: 'relative', isolation: 'isolate' }}>
      <div ref={containerRef} className="cluster-map-surface" style={{ height: 360, width: '100%', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }} />

      {/* Overlaid rather than replacing the map above -- the container div
          must always render so the init effect above always has something
          to attach to on mount, even before cluster data has arrived. */}
      {!clusters.length && (
        <div className="empty-state" style={{
          position: 'absolute', inset: 0, zIndex: 900,
          background: 'var(--bg-surface)', borderRadius: 'var(--radius-lg)',
        }}>
          <span style={{ fontSize: 32 }}>🗺️</span>
          <span>No clusters to display</span>
          <span style={{ fontSize: 11 }}>Ingest citizen reports and run /reprocess to generate clusters</span>
        </div>
      )}

      {/* Legend */}
      {clusters.length > 0 && (
        <div style={{
          position: 'absolute', bottom: 12, left: 12, zIndex: 1000,
          background: 'rgba(6,13,26,0.85)', backdropFilter: 'blur(10px)',
          border: '1px solid var(--border)', borderRadius: 10,
          padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6,
        }}>
          {Object.entries(VERDICT_COLORS).map(([verdict, color]) => (
            <div key={verdict} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
              <span style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'capitalize' }}>
                {verdict.replace(/_/g, ' ').toLowerCase()}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Issue list -- toggled by the "List all issues" control above.
          top:138 clears the 3-button control stack above it (measured:
          reset 12-42, fullscreen 56-86, list 100-130) -- at top:92 this
          panel used to overlap the list button itself, so a second click
          meant to close it actually hit the panel's first row instead,
          which is why it only ever closed via selecting a row. Also has
          its own explicit close button now, rather than relying on
          re-hitting the exact toggle position. */}
      {showList && clusters.length > 0 && (
        <div style={{
          position: 'absolute', top: 138, right: 12, zIndex: 1000,
          width: 240, maxHeight: 205, overflowY: 'auto',
          background: 'rgba(6,13,26,0.92)', backdropFilter: 'blur(10px)',
          border: '1px solid var(--border)', borderRadius: 10,
          padding: 8, display: 'flex', flexDirection: 'column', gap: 4,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '2px 4px 6px' }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              All Issues
            </span>
            <button
              onClick={() => setShowList(false)}
              title="Close"
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 20, height: 20, borderRadius: 6, border: 'none',
                background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer',
              }}
              onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.08)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M18 6 6 18"/><path d="M6 6l12 12"/></svg>
            </button>
          </div>
          {sortedClusters.map(c => {
            const verdict = c.priority?.verdict ?? 'WELL_SERVED'
            const color   = VERDICT_COLORS[verdict] ?? '#60a5fa'
            const emoji   = SECTOR_SYMBOLS[c.sector] ?? '📋'
            const hasLocation = !!parsePoint(c.centroid)
            return (
              <button
                key={c.id}
                onClick={() => flyToCluster(c)}
                disabled={!hasLocation}
                title={hasLocation ? undefined : 'No map location for this cluster'}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '6px 8px', borderRadius: 8, border: 'none',
                  background: 'transparent', textAlign: 'left',
                  cursor: hasLocation ? 'pointer' : 'not-allowed',
                  opacity: hasLocation ? 1 : 0.45,
                }}
                onMouseEnter={e => { if (hasLocation) e.currentTarget.style.background = 'rgba(255,255,255,0.06)' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
              >
                <span style={{ fontSize: 14, flexShrink: 0 }}>{emoji}</span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {c.region_name}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                    {c.report_count} reports
                  </div>
                </span>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
