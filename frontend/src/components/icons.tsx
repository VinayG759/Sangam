// Small hand-drawn line icons for the metric cards -- kept dependency-free
// (no icon library added) and visually consistent with each other, unlike
// the mixed-style platform emoji they replace.

interface IconProps {
  size?: number;
}

const base = {
  fill: 'none' as const,
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

export function InboxIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base}>
      <path d="M4 12h4l1.5 3h5L16 12h4" />
      <path d="M5.5 6h13L20 12v6a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18v-6z" />
    </svg>
  )
}

export function AlertCircleIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 8v5" />
      <circle cx="12" cy="15.8" r="0.9" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function PauseCircleIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M10 9v6" />
      <path d="M14 9v6" />
    </svg>
  )
}

export function WalletIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base}>
      <path d="M4 7.5A1.5 1.5 0 0 1 5.5 6h12A1.5 1.5 0 0 1 19 7.5V9" />
      <rect x="4" y="9" width="16" height="9.5" rx="1.5" />
      <path d="M15.5 13a1 1 0 1 0 0 2.2 1 1 0 0 0 0-2.2z" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function LandmarkIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base}>
      <path d="M4 21h16" />
      <path d="M5.5 21v-8" />
      <path d="M9.5 21v-8" />
      <path d="M14.5 21v-8" />
      <path d="M18.5 21v-8" />
      <path d="M3 13h18l-9-6.5L3 13z" />
    </svg>
  )
}

export function LayoutGridIcon({ size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base}>
      <rect x="3.5" y="3.5" width="7.5" height="7.5" rx="1.3" />
      <rect x="13" y="3.5" width="7.5" height="7.5" rx="1.3" />
      <rect x="3.5" y="13" width="7.5" height="7.5" rx="1.3" />
      <rect x="13" y="13" width="7.5" height="7.5" rx="1.3" />
    </svg>
  )
}

export function ListRankedIcon({ size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base}>
      <path d="M9 6h11" />
      <path d="M9 12h11" />
      <path d="M9 18h11" />
      <path d="M4 5.5v3" />
      <path d="M4 5.5h1" />
      <path d="M3.5 11.5h1.3c.6 0 1 .5.7 1l-1.4 1.7h1.7" />
    </svg>
  )
}

export function SlidersIcon({ size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base}>
      <path d="M5 19V13" /><path d="M5 9V5" />
      <path d="M12 19V15" /><path d="M12 11V5" />
      <path d="M19 19V16" /><path d="M19 12V5" />
      <circle cx="5" cy="11" r="2" />
      <circle cx="12" cy="13" r="2" />
      <circle cx="19" cy="14" r="2" />
    </svg>
  )
}

export function FileTextIcon({ size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base}>
      <path d="M6.5 3.5h8L19 8v11.5a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1v-15a1 1 0 0 1 1-1z" />
      <path d="M14 3.5V8h4.5" />
      <path d="M8.5 12.5h7" />
      <path d="M8.5 15.5h7" />
      <path d="M8.5 18.5h4" />
    </svg>
  )
}
