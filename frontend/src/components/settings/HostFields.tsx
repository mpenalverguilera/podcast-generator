import { useRef } from 'react'
import { absoluteUrl } from '../../api/client'
import type { HostIn, VoiceOut } from '../../api/types'

function VoicePreviewButton({ url }: { url: string | null }) {
  const audioRef = useRef<HTMLAudioElement>(null)
  if (!url) return null
  return (
    <button
      type="button"
      onClick={() => audioRef.current?.play()}
      aria-label="Preview voice"
      className="rounded-md px-2 py-1 text-sm hover:bg-slate-100"
    >
      ▶
      <audio ref={audioRef} src={absoluteUrl(url)} preload="none" className="hidden" />
    </button>
  )
}

export function HostFields({
  label,
  host,
  voices,
  onChange,
}: {
  label: string
  host: HostIn
  voices: VoiceOut[]
  onChange: (host: HostIn) => void
}) {
  const selected = voices.find((v) => v.id === host.voice_id)
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-600">{label} name</label>
      <input
        value={host.name}
        onChange={(e) => onChange({ ...host, name: e.target.value })}
        className="mb-2 w-full rounded-md border border-slate-300 px-2 py-1 text-sm focus:border-accent focus:outline-none"
      />
      <label className="mb-1 block text-xs font-medium text-slate-600">Voice</label>
      <div className="flex items-center gap-1">
        <select
          value={host.voice_id}
          onChange={(e) => onChange({ ...host, voice_id: e.target.value })}
          className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-sm focus:border-accent focus:outline-none"
        >
          {voices.map((v) => (
            <option key={v.id} value={v.id}>
              {v.label}
            </option>
          ))}
        </select>
        <VoicePreviewButton url={selected?.preview_url ?? null} />
      </div>
    </div>
  )
}
