import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useBlocker } from 'react-router'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Camera, CheckCircle2, Languages, LocateFixed, Mic, RefreshCw, Square, Trash2 } from 'lucide-react'
import { get, postForm, type Region } from '@/lib/api'
import { Button, inputStyle } from '@/ui/primitives'
import { ErrorState } from '@/ui/states'
import { isRtl, type Lang, LANGUAGES, type Strings, useLanguage } from './i18n'

interface Receipt {
  tracking_id: string | null
  status: string | null
  sector: string | null
  region_name: string | null
  message: string
}

const MAX_PHOTO_BYTES = 10 * 1024 * 1024

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

/** A preview URL for a file or recording, released when it changes or the page closes. */
function useObjectUrl(blob: Blob | null): string | null {
  const url = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob])
  useEffect(() => () => { if (url) URL.revokeObjectURL(url) }, [url])
  return url
}

export default function CitizenReportPage() {
  const [lang, setLang, t] = useLanguage()
  const regions = useQuery({ queryKey: ['regions'], queryFn: () => get<Region[]>('/api/v1/regions'), staleTime: Infinity })

  const [text, setText] = useState('')
  const [area, setArea] = useState('')
  const [subArea, setSubArea] = useState('')
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null)
  const [locating, setLocating] = useState(false)
  const [notice, setNotice] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [voice, setVoice] = useState<Blob | null>(null)
  const [recording, setRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const recorder = useRef<MediaRecorder | null>(null)
  const photoInput = useRef<HTMLInputElement>(null)
  const photoUrl = useObjectUrl(photo)
  const voiceUrl = useObjectUrl(voice)

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

  // Anything entered and not yet sent counts as unsaved work.
  const dirty = Boolean(text.trim() || voice || photo || area || coords || recording) && !submit.data?.tracking_id
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname)
  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => e.preventDefault() // browser shows its own "leave site?" prompt
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  useEffect(() => () => recorder.current?.stream.getTracks().forEach((track) => track.stop()), [])
  useEffect(() => {
    if (!recording) return
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(timer)
  }, [recording])

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
        stream.getTracks().forEach((track) => track.stop())
      }
      rec.start()
      recorder.current = rec
      setSeconds(0)
      setRecording(true)
      setPhoto(null) // one attachment per report
      setNotice('')
    } catch {
      setNotice(t.micUnavailable)
    }
  }

  function choosePhoto(file: File | undefined) {
    if (!file) return
    if (file.size > MAX_PHOTO_BYTES) {
      setNotice(t.photoTooBig)
      return
    }
    setPhoto(file)
    setVoice(null) // one attachment per report
    setNotice('')
  }

  function useMyLocation() {
    setLocating(true)
    setNotice('')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lon: pos.coords.longitude })
        setArea('')
        setSubArea('')
        setLocating(false)
      },
      () => {
        setNotice(t.locationFailed)
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
      <Shell lang={lang} onLang={setLang} t={t}>
        <div className="rounded-lg border border-line bg-surface p-6 text-center">
          <CheckCircle2 className="mx-auto size-8 text-accent" strokeWidth={1.5} />
          <h1 className="mt-3 text-lg font-semibold">{t.doneTitle}</h1>
          <p className="mt-1 text-muted">{t.doneKeep}</p>
          <div dir="ltr" className="num mt-4 rounded-md bg-subtle py-3 text-2xl font-semibold tracking-wider">{r.tracking_id}</div>
          {r.region_name && <p className="mt-3 text-[13px] text-muted">{t.place}: {r.region_name}</p>}
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            <Link to={`/track/${r.tracking_id}`} className="inline-flex h-9 items-center rounded-md bg-accent px-3 text-[13px] font-medium text-white">
              {t.trackButton}
            </Link>
            <Button onClick={() => window.location.reload()}>{t.another}</Button>
          </div>
        </div>
      </Shell>
    )
  }

  return (
    <Shell lang={lang} onLang={setLang} t={t}>
      <h1 className="text-xl font-semibold tracking-tight">{t.title}</h1>
      <p className="mt-1 text-muted">{t.intro}</p>

      <form
        className="mt-6 space-y-5"
        onSubmit={(e) => {
          e.preventDefault()
          submit.mutate()
        }}
      >
        <fieldset className="space-y-2">
          <legend className="mb-1 text-[13px] font-medium">{t.step1}</legend>
          <textarea
            className={`${inputStyle} h-28 w-full py-2`}
            placeholder={t.placeholder}
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={4000}
          />
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={toggleRecording} aria-pressed={recording}>
              {recording ? <Square className="size-4 text-unserved" /> : <Mic className="size-4" />}
              {recording ? t.stop : voice ? t.recordAgain : t.record}
            </Button>
            {!photo && (
              <Button type="button" onClick={() => photoInput.current?.click()} disabled={recording}>
                <Camera className="size-4" /> {t.addPhoto}
              </Button>
            )}
            <input
              ref={photoInput}
              type="file"
              accept="image/*"
              capture="environment"
              className="sr-only"
              tabIndex={-1}
              onChange={(e) => {
                choosePhoto(e.target.files?.[0])
                e.target.value = '' // choosing the same file again still fires
              }}
            />
          </div>

          {recording && (
            <p role="status" className="flex items-center gap-2 text-[13px] text-unserved">
              <span className="size-2 animate-pulse rounded-full bg-unserved" />
              {t.recording} <span dir="ltr" className="num">{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}</span>
            </p>
          )}

          {voiceUrl && !recording && (
            <div className="flex items-center gap-2 rounded-md border border-line bg-surface p-2">
              <audio controls src={voiceUrl} className="h-9 min-w-0 flex-1" />
              <button
                type="button"
                onClick={() => setVoice(null)}
                className="inline-flex size-9 shrink-0 items-center justify-center rounded-md text-muted hover:bg-subtle hover:text-unserved"
                title={t.removeVoice}
              >
                <Trash2 className="size-4" />
                <span className="sr-only">{t.removeVoice}</span>
              </button>
            </div>
          )}

          {photoUrl && photo && (
            <div className="overflow-hidden rounded-md border border-line bg-surface">
              <img src={photoUrl} alt={photo.name} className="max-h-72 w-full bg-subtle object-contain" />
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line p-2">
                <span className="min-w-0 truncate text-[12px] text-muted">{photo.name}</span>
                <div className="flex gap-2">
                  <Button type="button" onClick={() => photoInput.current?.click()}>
                    <RefreshCw className="size-4" /> {t.changePhoto}
                  </Button>
                  <Button type="button" onClick={() => setPhoto(null)}>
                    <Trash2 className="size-4" /> {t.removePhoto}
                  </Button>
                </div>
              </div>
            </div>
          )}
          <p className="text-[12px] text-faint">{t.oneAttachment}</p>
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="mb-1 text-[13px] font-medium">{t.step2}</legend>
          <Button type="button" onClick={useMyLocation} disabled={locating}>
            <LocateFixed className="size-4" /> {locating ? t.finding : coords ? t.locationShared : t.useLocation}
          </Button>
          <div className="text-[12px] text-faint">{t.orChoose}</div>
          <select
            aria-label={t.chooseDistrict}
            className={`${inputStyle} w-full`}
            value={area}
            onChange={(e) => {
              setArea(e.target.value)
              setSubArea('')
              setCoords(null)
            }}
          >
            <option value="">{t.chooseDistrict}</option>
            {upper.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
          {lower.length > 0 && (
            <select aria-label={t.chooseBlock} className={`${inputStyle} w-full`} value={subArea} onChange={(e) => setSubArea(e.target.value)}>
              <option value="">{t.chooseBlock}</option>
              {lower.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          )}
        </fieldset>

        {notice && <p role="alert" className="text-[13px] text-unserved">{notice}</p>}
        {submit.isError && <ErrorState error={submit.error} title={t.sendError} />}

        <Button variant="primary" type="submit" className="w-full" disabled={!hasProblem || !hasPlace || submit.isPending || recording}>
          {submit.isPending ? t.sending : t.send}
        </Button>
        <p className="text-center text-[12px] text-faint">
          {t.otherChannels} {t.alreadyReported} <Link to="/track" className="text-accent">{t.trackIt}</Link>
        </p>
      </form>

      {blocker.state === 'blocked' && (
        <LeaveDialog t={t} onStay={() => blocker.reset()} onLeave={() => blocker.proceed()} />
      )}
    </Shell>
  )
}

function LeaveDialog({ t, onStay, onLeave }: { t: Strings; onStay: () => void; onLeave: () => void }) {
  const stay = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    stay.current?.focus()
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onStay()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onStay])
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center" onClick={onStay}>
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="leave-title"
        aria-describedby="leave-body"
        className="w-full max-w-sm rounded-lg border border-line bg-surface p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="leave-title" className="font-semibold">{t.leaveTitle}</h2>
        <p id="leave-body" className="mt-1 text-muted">{t.leaveBody}</p>
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <Button onClick={onLeave} className="text-unserved">{t.discard}</Button>
          <Button ref={stay} variant="primary" onClick={onStay}>{t.keepEditing}</Button>
        </div>
      </div>
    </div>
  )
}

export function Shell({ children, lang, onLang, t }: {
  children: React.ReactNode
  lang: Lang
  onLang: (lang: Lang) => void
  t: Strings
}) {
  return (
    <div className="min-h-screen bg-canvas" dir={isRtl(lang) ? 'rtl' : 'ltr'} lang={lang}>
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-lg items-center justify-between gap-3 px-4 py-3">
          <span className="flex items-center gap-2">
            <img src="/favicon.svg" alt="" className="size-6" />
            <span className="font-semibold">Sangam</span>
          </span>
          <label className="flex items-center gap-1.5 text-[13px] text-muted">
            <Languages className="size-4" aria-hidden />
            <span className="sr-only">{t.language}</span>
            <select
              value={lang}
              onChange={(e) => onLang(e.target.value as Lang)}
              className="h-8 rounded-md border border-line bg-surface px-2 text-[13px] text-ink"
            >
              {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
            </select>
          </label>
        </div>
      </header>
      <main className="mx-auto max-w-lg px-4 py-6">{children}</main>
    </div>
  )
}
