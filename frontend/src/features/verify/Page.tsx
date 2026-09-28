import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react'
import { postForm } from '@/lib/api'
import { Button, PageHeader, Panel } from '@/ui/primitives'
import { ErrorState } from '@/ui/states'

type Status = 'valid' | 'tampered' | 'unsigned' | 'other_key'

interface Result {
  status: Status
  key_id: string | null
  server_key_id: string
}

const RESULTS: Record<Status, { title: string; body: string; tone: string; Icon: typeof ShieldCheck }> = {
  valid: {
    title: 'Authentic and unchanged',
    body: 'This brief was exported by Sangam and not one byte has changed since.',
    tone: 'text-accent',
    Icon: ShieldCheck,
  },
  tampered: {
    title: 'Altered after export',
    body: 'This file carries a Sangam signature, but its contents no longer match it. Do not rely on its figures.',
    tone: 'text-unserved',
    Icon: ShieldAlert,
  },
  unsigned: {
    title: 'No Sangam signature',
    body: 'Either it was never signed, or it was re-saved by another program (which removes the signature). Download the brief again from Sangam.',
    tone: 'text-delivery',
    Icon: ShieldQuestion,
  },
  other_key: {
    title: 'Signed by a different key',
    body: 'This file was signed, but not by this Sangam server. It may come from another deployment, or be a forgery.',
    tone: 'text-unserved',
    Icon: ShieldAlert,
  },
}

export default function VerifyPage() {
  const [file, setFile] = useState<File | null>(null)
  const check = useMutation({
    mutationFn: (f: File) => {
      const form = new FormData()
      form.append('file', f)
      return postForm<Result>('/api/v1/verify', form)
    },
  })

  return (
    <>
      <PageHeader
        title="Verify a brief"
        description="Every brief Sangam exports is digitally signed. Check that a PDF you received is exactly as Sangam produced it. The file is checked and discarded; nothing is stored."
      />
      <Panel className="max-w-2xl">
        <form
          className="flex flex-wrap items-center gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (file) check.mutate(file)
          }}
        >
          <input
            type="file"
            accept="application/pdf"
            aria-label="Brief PDF"
            className="text-[13px] text-muted file:mr-3 file:rounded-md file:border file:border-line file:bg-surface file:px-3 file:py-1.5 file:text-ink"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null)
              check.reset()
            }}
          />
          <Button type="submit" variant="primary" disabled={!file || check.isPending}>
            {check.isPending ? 'Checking…' : 'Check'}
          </Button>
        </form>

        {check.isError && <div className="mt-4"><ErrorState error={check.error} title="Could not check this file" /></div>}
        {check.data && <Outcome result={check.data} />}

        <p className="mt-6 text-[12px] text-faint">
          You can also check a brief offline, without trusting this website: the public key is published in the
          project repository (docs/brief-signing-key.pub), with a script that verifies any brief against it.
        </p>
      </Panel>
    </>
  )
}

function Outcome({ result }: { result: Result }) {
  const { title, body, tone, Icon } = RESULTS[result.status]
  return (
    <div role="status" className="mt-5 flex gap-3 rounded-lg border border-line p-4">
      <Icon className={`size-6 shrink-0 ${tone}`} />
      <div>
        <div className={`font-semibold ${tone}`}>{title}</div>
        <p className="mt-1 text-muted">{body}</p>
        <p className="mt-2 text-[11px] text-faint">Signing key {result.key_id ?? '—'} · this server {result.server_key_id}</p>
      </div>
    </div>
  )
}
