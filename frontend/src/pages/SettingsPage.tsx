import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { HostIn, InterestProfile, PreferencesUpdate, Tone, VoiceOut } from '../api/types'
import { Spinner } from '../components/Spinner'
import { GuidedInterview } from '../components/settings/GuidedInterview'
import { ProfileEditor } from '../components/settings/ProfileEditor'
import { HostFields } from '../components/settings/HostFields'
import { buildCron, parseCron, type ScheduleMode } from '../lib/cron'
import { timezoneOptions } from '../lib/timezones'

const TONES: Tone[] = ['conversational', 'focused', 'playful']
const SCHEDULE_MODES: ScheduleMode[] = ['off', 'daily', 'weekdays']

interface Draft {
  interest_profile: InterestProfile
  target_minutes: number
  tone: Tone
  host_a: HostIn
  host_b: HostIn
  schedule_mode: ScheduleMode
  schedule_time: string
  timezone: string
}

function draftToBody(draft: Draft): PreferencesUpdate {
  return {
    interest_profile: draft.interest_profile,
    target_minutes: draft.target_minutes,
    tone: draft.tone,
    host_a: draft.host_a,
    host_b: draft.host_b,
    schedule_cron: buildCron(draft.schedule_mode, draft.schedule_time),
    timezone: draft.timezone,
  }
}

export function SettingsPage() {
  const queryClient = useQueryClient()
  const preferencesQuery = useQuery({ queryKey: ['preferences'], queryFn: api.getPreferences })
  const voicesQuery = useQuery({ queryKey: ['voices'], queryFn: api.voices })
  const lengthOptionsQuery = useQuery({ queryKey: ['length-options'], queryFn: api.lengthOptions })

  const [draft, setDraft] = useState<Draft | null>(null)
  const [savedSnapshot, setSavedSnapshot] = useState<string | null>(null)
  const [savedMessage, setSavedMessage] = useState(false)

  // Seed the draft from the server once, on first load only -- a later
  // background refetch (e.g. on window focus) must never clobber edits the
  // user hasn't saved yet.
  useEffect(() => {
    if (draft || !preferencesQuery.data || !voicesQuery.data) return
    const prefs = preferencesQuery.data
    const defaultVoice = voicesQuery.data[0]?.id ?? ''
    const schedule = parseCron(prefs.schedule_cron)
    const initial: Draft = {
      interest_profile: prefs.interest_profile,
      target_minutes: prefs.target_minutes,
      tone: prefs.tone ?? 'conversational',
      host_a: { name: prefs.host_a.name, voice_id: prefs.host_a.voice_id || defaultVoice },
      host_b: { name: prefs.host_b.name, voice_id: prefs.host_b.voice_id || defaultVoice },
      schedule_mode: schedule.mode,
      schedule_time: schedule.time,
      timezone: prefs.timezone,
    }
    setDraft(initial)
    setSavedSnapshot(JSON.stringify(initial))
  }, [draft, preferencesQuery.data, voicesQuery.data])

  const dirty = draft !== null && JSON.stringify(draft) !== savedSnapshot

  useEffect(() => {
    if (!dirty) return
    function handler(e: BeforeUnloadEvent) {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

  const save = useMutation({
    mutationFn: (body: PreferencesUpdate) => api.updatePreferences(body),
    onSuccess: (updated) => {
      queryClient.setQueryData(['preferences'], updated)
      if (draft) setSavedSnapshot(JSON.stringify(draft))
      setSavedMessage(true)
      setTimeout(() => setSavedMessage(false), 2000)
    },
  })

  if (preferencesQuery.isLoading || voicesQuery.isLoading || !draft) return <Spinner />
  if (preferencesQuery.isError) return <p className="text-sm text-red-600">Could not load preferences.</p>

  const voices: VoiceOut[] = voicesQuery.data ?? []
  const lengthOptions = lengthOptionsQuery.data ?? []
  const storiesEstimate = lengthOptions.find((o) => o.minutes === draft.target_minutes)?.stories

  function update(patch: Partial<Draft>) {
    setDraft((d) => (d ? { ...d, ...patch } : d))
  }

  return (
    <div className="space-y-6 pb-24">
      <h1 className="text-lg font-semibold text-slate-900">Interests &amp; settings</h1>

      <GuidedInterview onExtracted={(profile) => update({ interest_profile: profile })} />

      <ProfileEditor profile={draft.interest_profile} onChange={(p) => update({ interest_profile: p })} />

      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-slate-900">Podcast settings</h2>

        <div className="mb-4">
          <label className="mb-1 block text-xs font-medium text-slate-600">
            Length: ~{draft.target_minutes} min
            {storiesEstimate != null && ` · ~${storiesEstimate} stories`}
          </label>
          <input
            type="range"
            min={3}
            max={12}
            value={draft.target_minutes}
            onChange={(e) => update({ target_minutes: Number(e.target.value) })}
            className="w-full accent-accent"
          />
        </div>

        <div className="mb-4">
          <label className="mb-1 block text-xs font-medium text-slate-600">Tone</label>
          <div className="flex gap-2">
            {TONES.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => update({ tone: t })}
                className={`rounded-full px-3 py-1 text-xs ${
                  draft.tone === t ? 'bg-accent text-white' : 'bg-slate-100 hover:bg-slate-200'
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <HostFields label="Host A" host={draft.host_a} voices={voices} onChange={(h) => update({ host_a: h })} />
          <HostFields label="Host B" host={draft.host_b} voices={voices} onChange={(h) => update({ host_b: h })} />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Schedule</label>
          <div className="mb-2 flex gap-2">
            {SCHEDULE_MODES.map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => update({ schedule_mode: mode })}
                className={`rounded-full px-3 py-1 text-xs ${
                  draft.schedule_mode === mode ? 'bg-accent text-white' : 'bg-slate-100 hover:bg-slate-200'
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
          {draft.schedule_mode !== 'off' && (
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="time"
                value={draft.schedule_time}
                onChange={(e) => update({ schedule_time: e.target.value })}
                className="rounded-md border border-slate-300 px-2 py-1 text-sm focus:border-accent focus:outline-none"
              />
              <select
                value={draft.timezone}
                onChange={(e) => update({ timezone: e.target.value })}
                className="rounded-md border border-slate-300 px-2 py-1 text-sm focus:border-accent focus:outline-none"
              >
                {timezoneOptions(draft.timezone).map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      <div className="fixed inset-x-0 bottom-0 flex items-center gap-3 border-t border-slate-200 bg-white px-4 py-3 shadow-md sm:sticky">
        <button
          type="button"
          onClick={() => save.mutate(draftToBody(draft))}
          disabled={save.isPending || !dirty}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-60"
        >
          {save.isPending ? 'Saving…' : 'Save settings'}
        </button>
        {dirty && !save.isPending && <span className="text-sm text-amber-600">Unsaved changes</span>}
        {savedMessage && <span className="text-sm text-emerald-600">Saved</span>}
        {save.isError && <span className="text-sm text-red-600">Could not save.</span>}
      </div>
    </div>
  )
}
