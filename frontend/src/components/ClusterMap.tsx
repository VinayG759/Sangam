import { useEffect, useRef } from 'react'
import L from 'leaflet'
import type { Cluster } from '@/api'

interface ClusterMapProps {
  clusters: Cluster[];
}

const VERDICT_COLORS: Record<string, string> = {
  UNSERVED_GAP:        '#ef4444',
  STALLED_ALLOCATION:  '#f97316',
  UNDERFUNDED_CRITICAL:'#eab308',
  WELL_SERVED:         '#10b981',
}

const SECTOR_SYMBOLS: Record<string, string> = {
  water: '💧', roads: '🛣️', sanitation: '♻️',
  health: '🏥', education: '🏫', electricity: '⚡',
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

export default function ClusterMap({ clusters }: ClusterMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef       = useRef<L.Map | null>(null)
  const layerRef     = useRef<L.LayerGroup | null>(null)

  // Initialize map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = L.map(containerRef.current, {
      center: [15.3173, 75.7139], // Karnataka, India
      zoom: 6,
      zoomControl: true,
    })

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '',
      maxZoom: 19,
    }).addTo(map)

    const layer = L.layerGroup().addTo(map)
    mapRef.current  = map
    layerRef.current = layer

    return () => {
      map.remove()
      mapRef.current  = null
      layerRef.current = null
    }
  }, [])

  // Update markers when clusters change
  useEffect(() => {
    if (!layerRef.current) return
    layerRef.current.clearLayers()

    if (!clusters.length) return

    const bounds: [number, number][] = []

    clusters.forEach(c => {
      // Use Karnataka center + jitter if no real coords (backend returns centroid from PostGIS)
      // In production this will use actual cluster centroids; for demo we jitter around KA
      const lat = 14.5 + (c.id * 0.73) % 3.5 - 1.75 + Math.sin(c.id * 2.4) * 0.5
      const lng = 74.5 + (c.id * 0.91) % 3.0 - 1.5  + Math.cos(c.id * 1.7) * 0.4

      bounds.push([lat, lng])

      const verdict = c.priority?.verdict ?? 'WELL_SERVED'
      const color   = VERDICT_COLORS[verdict] ?? '#60a5fa'
      const emoji   = SECTOR_SYMBOLS[c.sector] ?? '📋'

      const marker = L.marker([lat, lng], { icon: makeMarkerIcon(color, emoji) })
      marker.bindPopup(`
        <div style="min-width: 180px;">
          <div style="font-weight: 700; font-size: 13px; margin-bottom: 6px; color: #f0f6ff;">${c.title}</div>
          <div style="font-size: 11px; color: #8ba4cc; margin-bottom: 4px;">
            ${c.region_name} · ${c.report_count} reports
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
          ` : ''}
        </div>
      `)
      layerRef.current?.addLayer(marker)
    })

    // Fit to bounds if we have markers
    if (bounds.length && mapRef.current) {
      try {
        mapRef.current.fitBounds(bounds, { padding: [40, 40], maxZoom: 9 })
      } catch {
        // ignore fitBounds errors when map not ready
      }
    }
  }, [clusters])

  if (!clusters.length) {
    return (
      <div className="empty-state" style={{ height: 360 }}>
        <span style={{ fontSize: 32 }}>🗺️</span>
        <span>No clusters to display</span>
        <span style={{ fontSize: 11 }}>Ingest citizen reports and run /reprocess to generate clusters</span>
      </div>
    )
  }

  return (
    <div style={{ position: 'relative' }}>
      <div ref={containerRef} style={{ height: 360, width: '100%', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }} />

      {/* Legend */}
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
    </div>
  )
}
