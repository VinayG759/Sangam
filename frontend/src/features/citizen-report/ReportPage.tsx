import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Camera, CheckCircle2, LocateFixed, Mic, Square } from 'lucide-react'
import { get, postForm, type Region } from '@/lib/api'
import { usePack } from '@/lib/pack'
import { Button, inputStyle } from '@/ui/primitives'
import { ErrorState } from '@/ui/states'

interface Receipt {
  tracking_id: string | null
  status: string | null
  sector: string | null
  region_name: string | null
  message: string
}

/** A random ID this browser keeps, so the daily report limit works without an account. */
function clientId(): string {
  const make = () => (crypto.randomUUID?.() ?? `${Date.now()}-${Math.random()}`).replace(/[^\w-]/g, '')
  try {
    const existing = localStorage.getItem('sangam-client-id')
    if (existing) return existing
    const id = make()
    localStorage.setItem('sangam-client-id', id)
    return id
  } catch {
    return make()
  }
}

export default function CitizenReportPage() {
  const pack = usePack()
  const regions = useQuery({ queryKey: ['regions'], queryFn: () => get<Region[]>('/api/v1/regions'), staleTime: Infinity })

  const [text, setText] = useState('')
  const [area, setArea] = useState('')
  const [subArea, setSubArea] = useState('')
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null)
  const [locating, setLocating] = useState(false)
  const [locationError, setLocationError] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [voice, setVoice] = useState<Blob | null>(null)
  const [recording, setRecording] = useState(false)
  const recorder = useRef<MediaRecorder | null>(null)

  const levels = pack.data?.admin_levels ?? []
  const upper = useMemo(() => (regions.data ?? []).filter((r) => r.level === 2), [regions.data])
  const lower = useMemo(() => (regions.data ?? []).filter((r) => r.level === 3 && r.parent_id === area), [regions.data, area])

  const submit = useMutation({
    mutationFn: () => {
      const form = new FormData()
      form.set('client_id', clientId())
      if (text.trim()) form.set('text', text.trim())
      if (subArea || area) form.set('region_id', subArea || area)
      else if (coords) {
        form.set('lat', String(coords.lat))
        form.set('lon', String(coords.lon))
      }
      if (voice) form.set('file', voice, 'voice-note.webm')
      else if (photo) form.set('file', photo)
      return postForm<Receipt>('/api/v1/reports', form)
    },
  })

  useEffect(() => () => recorder.current?.stream.getTracks().forEach((t) => t.stop()), [])

  async function toggleRecording() {
    if (recording) {
      recorder.current?.stop()
      setRecording(false)
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const rec = new MediaRecorder(stream)
      const chunks: Blob[] = []
      rec.ondataavailable = (e) => chunks.push(e.data)
      rec.onstop = () => {
        setVoice(new Blob(chunks, { type: rec.mimeType || 'audio/webm' }))
        stream.getTracks().forEach((t) => t.stop())
      }
      rec.start()
      recorder.current = rec
      setRecording(true)
      setPhoto(null)
    } catch {
      setLocationError('Microphone not available. You can type instead.')
    }
  }

  function useMyLocation() {
    setLocating(true)
    setLocationError('')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lon: pos.coords.longitude })
        setArea('')
        setSubArea('')
        setLocating(false)
      },
      () => {
        setLocationError('Could not get your location. Please choose your area from the list.')
        setLocating(false)
      },
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }

  const hasProblem = Boolean(text.trim() || voice || photo)
  const hasPlace = Boolean(area || coords)

  if (submit.data?.tracking_id) {
    const r = submit.data
    return (
      <Shell>
        <div className="rounded-lg border border-line bg-surface p-6 text-center">
          <CheckCircle2 className="mx-auto size-8 text-accent" strokeWidth={1.5} />
          <h1 className="mt-3 text-lg font-semibold">Your report is recorded</h1>
          <p className="mt-1 text-muted">Keep this tracking ID to check what happens next.</p>
          <div className="num mt-4 rounded-md bg-subtle py-3 text-2xl font-semibold tracking-wider">{r.tracking_id}</div>
          {r.region_name && <p className="mt-3 text-[13px] text-muted">Place: {r.region_name}</p>}
          <div className="mt-6 flex justify-center gap-2">
            <Link to={`/track/${r.tracking_id}`} className="inline-flex h-9 items-center rounded-md bg-accent px-3 text-[13px] font-medium text-white">
              Track this report
            </Link>
            <Button onClick={() => window.location.reload()}>Report another problem</Button>
          </div>
        </div>
      </Shell>
    )
  }

  return (
    <Shell>
      <h1 className="text-xl font-semibold tracking-tight">Report a problem in your area</h1>
      <p className="mt-1 text-muted">
        Water, roads, electricity, health, schools or sanitation. Write or speak in any language. No account needed, and
        your name or number is never stored.
      </p>

      <form
        className="mt-6 space-y-5"
        onSubmit={(e) => {
          e.preventDefault()
          submit.mutate()
        }}
      >
        <fieldset className="space-y-2">
          <legend className="mb-1 text-[13px] font-medium">1. What is the problem?</legend>
          <textarea
            className={`${inputStyle} h-28 w-full py-2`}
            placeholder="For example: no drinking water in our village for ten days"
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={4000}
          />
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={toggleRecording} aria-pressed={recording}>
              {recording ? <Square className="size-4 text-unserved" /> : <Mic className="size-4" />}
              {recording ? 'Stop recording' : voice ? 'Record again' : 'Record a voice note'}
            </Button>
            <label className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-md border border-line bg-surface px-3 text-[13px] font-medium hover:bg-subtle">
              <Camera className="size-4" /> {photo ? 'Change photo' : 'Add a photo'}
              <input
                type="file"
                accept="image/*"
                capture="environment"
                className="sr-only"
                onChange={(e) => {
                  setPhoto(e.target.files?.[0] ?? null)
                  setVoice(null)
                }}
              />
            </label>
          </div>
          {voice && !recording && <audio controls src={URL.createObjectURL(voice)} className="h-9 w-full" />}
          {photo && <p className="text-[12px] text-muted">Photo attached: {photo.name}</p>}
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="mb-1 text-[13px] font-medium">2. Where is it?</legend>
          <Button type="button" onClick={useMyLocation} disabled={locating}>
            <LocateFixed className="size-4" /> {locating ? 'Finding you…' : coords ? 'Location shared' : 'Use my location'}
          </Button>
          <div className="text-[12px] text-faint">or choose</div>
          <select
            aria-label={levels[2] ?? 'Area'}
            className={`${inputStyle} w-full`}
            value={area}
            onChange={(e) => {
              setArea(e.target.value)
              setSubArea('')
              setCoords(null)
            }}
          >
            <option value="">Choose {levels[2] ?? 'area'}</option>
            {upper.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
          {lower.length > 0 && (
            <select aria-label={levels[3] ?? 'Sub-area'} className={`${inputStyle} w-full`} value={subArea} onChange={(e) => setSubArea(e.target.value)}>
              <option value="">{levels[3] ? `Choose ${levels[3]} (optional)` : 'Optional'}</option>
              {lower.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          )}
          {locationError && <p className="text-[12px] text-unserved">{locationError}</p>}
        </fieldset>

        {submit.isError && <ErrorState error={submit.error} title="Could not send your report" />}

        <Button variant="primary" type="submit" className="w-full" disabled={!hasProblem || !hasPlace || submit.isPending || recording}>
          {submit.isPending ? 'Sending…' : 'Send report'}
        </Button>
        <p className="text-center text-[12px] text-faint">
          You can also report on WhatsApp or Telegram. Already reported? <Link to="/track" className="text-accent">Track it</Link>
        </p>
      </form>
    </Shell>
  )
}

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-canvas">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-lg items-center gap-2 px-4 py-3">
          <img src="/favicon.svg" alt="" className="size-6" />
          <span className="font-semibold">Sangam</span>
        </div>
      </header>
      <main className="mx-auto max-w-lg px-4 py-6">{children}</main>
    </div>
  )
}
