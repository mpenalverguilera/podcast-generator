import { useRef, useState } from 'react'
import { api } from '../api/client'

const RATES = [1, 1.25, 1.5] as const

// Sends play telemetry (ARCHITECTURE §7 events): one play_started per playback
// session, play_progress every ~15s while playing, one play_completed on end.
export function AudioPlayer({ episodeId, src }: { episodeId: number; src: string }) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [rate, setRate] = useState<number>(1)
  const startedRef = useRef(false)
  const lastReportedRef = useRef(0)

  function setPlaybackRate(next: number) {
    setRate(next)
    if (audioRef.current) audioRef.current.playbackRate = next
  }

  function onPlay() {
    if (!startedRef.current) {
      startedRef.current = true
      void api.sendEvent({ type: 'play_started', episode_id: episodeId })
    }
  }

  function onTimeUpdate() {
    const position = audioRef.current?.currentTime ?? 0
    if (position - lastReportedRef.current >= 15) {
      lastReportedRef.current = position
      void api.sendEvent({
        type: 'play_progress',
        episode_id: episodeId,
        payload: { position_s: Math.floor(position) },
      })
    }
  }

  function onEnded() {
    void api.sendEvent({ type: 'play_completed', episode_id: episodeId })
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <audio
        ref={audioRef}
        src={src}
        controls
        className="w-full"
        onPlay={onPlay}
        onTimeUpdate={onTimeUpdate}
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
      </div>
    </div>
  )
}
