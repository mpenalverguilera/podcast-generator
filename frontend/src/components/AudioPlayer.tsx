import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { formatDuration } from '../lib/format'

const RATES = [1, 1.25, 1.5] as const

// Sends play telemetry (ARCHITECTURE §7 events): one play_started per playback
// session, play_progress every ~15s while playing and again on pause / leaving
// the page, one play_completed on end. The last play_progress is also the
// resume point the API hands back as resume_position_s (D-46).
export function AudioPlayer({
  episodeId,
  src,
  resumeFrom,
}: {
  episodeId: number
  src: string
  resumeFrom?: number | null
}) {
  // Pinned at mount: every refetch of the episode mints a fresh media token,
  // so audio_url changes, and a new src would restart playback from 0 (D-46).
  // The parent keys this component by episode id, so a new episode remounts.
  const [stableSrc] = useState(src)
  const [startAt] = useState(resumeFrom ?? null)
  const [resumedAt, setResumedAt] = useState<number | null>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const [rate, setRate] = useState<number>(1)
  const startedRef = useRef(false)
  const lastReportedRef = useRef(0)
  const queryClient = useQueryClient()

  // The list's New / In progress / Played badge reads these events back; the
  // list can load before the last one lands when the user navigates away.
  function send(type: 'play_progress' | 'play_completed', payload?: Record<string, unknown>) {
    void api
      .sendEvent({ type, episode_id: episodeId, payload })
      .then(() => queryClient.invalidateQueries({ queryKey: ['episodes'] }))
  }

  function reportProgress(position: number) {
    if (!startedRef.current || Math.floor(position) === Math.floor(lastReportedRef.current)) return
    lastReportedRef.current = position
    send('play_progress', { position_s: Math.floor(position) })
  }

  // Save the position when the user navigates away or closes the tab
  // mid-listen, not just at the last 15s tick.
  useEffect(() => {
    const el = audioRef.current
    if (!el) return
    const onLeave = () => {
      if (!el.paused && !el.ended) reportProgress(el.currentTime)
    }
    window.addEventListener('pagehide', onLeave)
    return () => {
      window.removeEventListener('pagehide', onLeave)
      onLeave()
    }
    // reportProgress only reads refs and per-mount constants.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function setPlaybackRate(next: number) {
    setRate(next)
    if (audioRef.current) audioRef.current.playbackRate = next
  }

  function onLoadedMetadata() {
    const el = audioRef.current
    if (!el || startAt == null || startAt < 1) return
    if (!Number.isFinite(el.duration) || startAt < el.duration - 5) {
      el.currentTime = startAt
      lastReportedRef.current = startAt
      setResumedAt(startAt)
    }
  }

  function onPlay() {
    if (!startedRef.current) {
      startedRef.current = true
      void api.sendEvent({ type: 'play_started', episode_id: episodeId })
    }
  }

  function onTimeUpdate() {
    const position = audioRef.current?.currentTime ?? 0
    // abs: a backwards seek shouldn't stall reporting until it catches up.
    if (Math.abs(position - lastReportedRef.current) >= 15) reportProgress(position)
  }

  function onPause() {
    const el = audioRef.current
    if (el && !el.ended) reportProgress(el.currentTime)
  }

  function onEnded() {
    send('play_completed')
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <audio
        ref={audioRef}
        src={stableSrc}
        controls
        className="w-full"
        onLoadedMetadata={onLoadedMetadata}
        onPlay={onPlay}
        onTimeUpdate={onTimeUpdate}
        onPause={onPause}
        onEnded={onEnded}
      />
      <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
        <span>Speed:</span>
        {RATES.map((r) => (
          <button
            key={r}
            onClick={() => setPlaybackRate(r)}
            className={`rounded-md px-2 py-1 font-medium ${
              rate === r ? 'bg-accent text-white' : 'bg-slate-100 hover:bg-slate-200'
            }`}
          >
            {r}×
          </button>
        ))}
        {resumedAt != null && (
          <span className="ml-auto text-sky-700">Picking up where you left off · {formatDuration(resumedAt)}</span>
        )}
      </div>
    </div>
  )
}
