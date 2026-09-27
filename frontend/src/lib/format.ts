// Number, money and date formatting. Indian grouping (lakh/crore) for INR.

const indian = new Intl.NumberFormat('en-IN')

export function formatNumber(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: decimals, minimumFractionDigits: 0 }).format(value)
}

export function formatMoney(amount: number | null | undefined, currency: string, symbol: string): string {
  if (amount === null || amount === undefined) return '—'
  if (currency === 'INR') {
    if (Math.abs(amount) >= 1e7) return `${symbol}${formatNumber(amount / 1e7, 2)} crore`
    if (Math.abs(amount) >= 1e5) return `${symbol}${formatNumber(amount / 1e5, 2)} lakh`
    return `${symbol}${indian.format(Math.round(amount))}`
  }
  return new Intl.NumberFormat('en', { style: 'currency', currency, notation: 'compact' }).format(amount)
}

export function formatRatio(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${formatNumber(value, 1)}×`
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English', kn: 'Kannada', hi: 'Hindi', te: 'Telugu', ta: 'Tamil', ur: 'Urdu', mr: 'Marathi',
  bn: 'Bengali', ml: 'Malayalam', pt: 'Portuguese', es: 'Spanish', ru: 'Russian', zh: 'Chinese',
}

export function languageName(code: string | null | undefined): string {
  if (!code) return 'Unknown'
  return LANGUAGE_NAMES[code] ?? code.toUpperCase()
}
