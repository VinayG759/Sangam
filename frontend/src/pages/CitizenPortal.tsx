import React, { useState, useRef } from 'react'
import { api } from '@/api'

export default function CitizenPortal() {
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  
  // Audio recording
  const [isRecording, setIsRecording] = useState(false)
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<BlobPart[]>([])

  const [loading, setLoading] = useState(false)
  const [trackingId, setTrackingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Status check
  const [checkId, setCheckId] = useState('')
  const [statusResult, setStatusResult] = useState<any>(null)
  const [statusError, setStatusError] = useState<string | null>(null)

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaRecorderRef.current = new MediaRecorder(stream)
      audioChunksRef.current = []

      mediaRecorderRef.current.ondataavailable = e => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data)
      }

      mediaRecorderRef.current.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
        setAudioBlob(blob)
      }

      mediaRecorderRef.current.start()
      setIsRecording(true)
    } catch (err) {
      setError('Could not access microphone.')
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop()
      mediaRecorderRef.current.stream.getTracks().forEach(t => t.stop())
      setIsRecording(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!text && !file && !audioBlob) {
      setError('Please provide text, a photo, or an audio recording.')
      return
    }

    setLoading(true)
    setError(null)
    try {
      const fd = new FormData()
      if (text) fd.append('text', text)
      if (file) fd.append('file', file)
      else if (audioBlob) fd.append('file', audioBlob, 'recording.webm')

      const res = await api.submitCitizenReport(fd)
      setTrackingId(res.tracking_id)
      setText('')
      setFile(null)
      setAudioBlob(null)
    } catch (err: any) {
      setError(err.message || 'Submission failed')
    } finally {
      setLoading(false)
    }
  }

  const handleCheckStatus = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!checkId) return
    setStatusError(null)
    setStatusResult(null)
    try {
      const res = await api.checkStatus(checkId)
      setStatusResult(res)
    } catch (err: any) {
      setStatusError('Could not find tracking ID.')
    }
  }

  return (
    <div style={{ maxWidth: 600, margin: '40px auto', padding: '0 20px', fontFamily: 'var(--font-sans)' }}>
      <h1 style={{ fontSize: 24, marginBottom: 8 }}>Sangam Citizen Voice</h1>
      <p style={{ color: 'var(--text-secondary)', marginBottom: 24 }}>
        Report local infrastructure issues. Your report will be translated and prioritized automatically.
      </p>

      {error && <div style={{ color: 'red', marginBottom: 16 }}>{error}</div>}

      {trackingId ? (
        <div style={{ padding: 24, background: '#e0f2fe', borderRadius: 8, marginBottom: 24, border: '1px solid #bae6fd' }}>
          <h2 style={{ fontSize: 18, color: '#0369a1', marginBottom: 8 }}>Report Submitted Successfully</h2>
          <p style={{ marginBottom: 8 }}>Your secure tracking ID is:</p>
          <div style={{ fontSize: 32, fontWeight: 'bold', fontFamily: 'monospace', letterSpacing: 2 }}>{trackingId}</div>
          <p style={{ fontSize: 13, color: '#0369a1', marginTop: 8 }}>Save this ID to check on your report later.</p>
          <button onClick={() => setTrackingId(null)} className="btn btn-ghost" style={{ marginTop: 16 }}>
            Submit Another Report
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 40 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <label style={{ fontWeight: 600 }}>Describe the issue</label>
            <textarea
              className="input"
              style={{ minHeight: 100, padding: 12 }}
              placeholder="e.g. The water pipe on Main St has been broken for two weeks..."
              value={text}
              onChange={e => setText(e.target.value)}
            />
          </div>

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={{ fontWeight: 600 }}>Attach a Photo</label>
              <input
                type="file"
                accept="image/*"
                onChange={e => setFile(e.target.files?.[0] || null)}
                style={{ padding: '8px 0' }}
              />
            </div>
            
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={{ fontWeight: 600 }}>Record Voice Note</label>
              {isRecording ? (
                <button type="button" onClick={stopRecording} style={{ background: '#ef4444', color: 'white', padding: '8px 16px', borderRadius: 4, border: 'none', cursor: 'pointer' }}>
                  Stop Recording
                </button>
              ) : (
                <button type="button" onClick={startRecording} style={{ background: '#3b82f6', color: 'white', padding: '8px 16px', borderRadius: 4, border: 'none', cursor: 'pointer' }}>
                  Start Recording
                </button>
              )}
              {audioBlob && <span style={{ fontSize: 12, color: 'green' }}>Voice note attached!</span>}
            </div>
          </div>

          <button type="submit" disabled={loading} style={{ background: 'var(--accent-blue)', color: 'white', padding: '12px', borderRadius: 4, border: 'none', cursor: 'pointer', fontWeight: 'bold', fontSize: 16, marginTop: 16 }}>
            {loading ? 'Submitting...' : 'Submit Report'}
          </button>
        </form>
      )}

      <hr style={{ border: 'none', borderTop: '1px solid var(--border)', marginBottom: 24 }} />

      <h2 style={{ fontSize: 20, marginBottom: 16 }}>Check Status</h2>
      <form onSubmit={handleCheckStatus} style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <input
          type="text"
          className="input"
          placeholder="Enter Tracking ID (e.g. SNG-...)"
          value={checkId}
          onChange={e => setCheckId(e.target.value)}
          style={{ flex: 1 }}
        />
        <button type="submit" className="btn btn-primary" style={{ padding: '0 16px' }}>Check</button>
      </form>
      {statusError && <div style={{ color: 'red' }}>{statusError}</div>}
      {statusResult && (
        <div style={{ padding: 16, background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 8 }}>
          <div style={{ marginBottom: 8 }}><strong>Status:</strong> {statusResult.status}</div>
          <div style={{ marginBottom: 8 }}><strong>Sector:</strong> {statusResult.sector}</div>
          {statusResult.cluster_id ? (
             <div style={{ color: 'green' }}>Clustered and analyzed! (Cluster ID: {statusResult.cluster_id})</div>
          ) : (
             <div style={{ color: 'orange' }}>Pending grouping with other reports.</div>
          )}
        </div>
      )}
    </div>
  )
}
