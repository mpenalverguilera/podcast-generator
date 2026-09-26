import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../api/client'
import { isTerminal, type EpisodeListItem } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Spinner } from '../components/Spinner'
import { EpisodeListBadge, StageStepper } from '../components/StatusBadge'
import { formatDuration } from '../lib/format'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

// "5h 12m", "3m", "2d 4h": coarse on purpose, it re-renders every 30s.
function formatCountdown(ms: number): string {
  const minutes = Math.max(1, Math.ceil(ms / 60_000))
  const d = Math.floor(minutes / 1440)
  const h = Math.floor((minutes % 1440) / 60)
  const m = minutes % 60
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function NextEpisodeCountdown() {
  const queryClient = useQueryClient()
  const prefsQuery = useQuery({ queryKey: ['preferences'], queryFn: api.getPreferences })
  const [now, setNow] = useState(() => Date.now())
  const nextRunAt = prefsQuery.data?.next_run_at ?? null
  const target = nextRunAt ? new Date(nextRunAt).getTime() : null
  const due = target !== null && target <= now

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(id)
  }, [])

  // Once the scheduled time passes, pick up the new episode and the next slot.
  useEffect(() => {
    if (!due) return
    void queryClient.invalidateQueries({ queryKey: ['preferences'] })
    void queryClient.invalidateQueries({ queryKey: ['episodes'] })
  }, [due, queryClient])

  if (!prefsQuery.data) return null

  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm">
      {target === null ? (
        <>
          <span className="text-slate-500">No schedule set — episodes are only made when you ask.</span>
          <Link to="/settings#schedule" className="font-medium text-accent hover:underline">
            Set a schedule
          </Link>
        </>
      ) : (
        <>
          <span className="text-slate-700">
            Next episode{' '}
            <span className="font-semibold text-slate-900">
              {due ? 'is on its way' : `in ${formatCountdown(target - now)}`}
            </span>
          </span>
          <span className="text-xs text-slate-500">
            {new Date(target).toLocaleString(undefined, {
              weekday: 'short',
              hour: 'numeric',
              minute: '2-digit',
            })}
          </span>
        </>
      )}
    </div>
  )
}

function SetUpProfileCard() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 text-center shadow-sm">
      <h2 className="text-base font-semibold text-slate-900">Set up your interests first</h2>
      <p className="mt-1 text-sm text-slate-500">
        Episodes are built from your preferences — tell us what you want to hear about.
      </p>
      <Link
        to="/settings"
        className="mt-4 inline-block rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark"
      >
        Add my interests
      </Link>
    </div>
  )
}

function NewEpisodePanel({ disabled }: { disabled: boolean }) {
  const [focus, setFocus] = useState('')
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const generate = useMutation({
    mutationFn: () => api.generateEpisode({ focus_request: focus.trim() || undefined }),
    onSuccess: () => {
      setFocus('')
      void queryClient.invalidateQueries({ queryKey: ['episodes'] })
    },
    onError: (err: unknown) => {
      setError(err instanceof ApiError ? err.message : 'Could not start generation.')
    },
  })

  return (
    <div className="mb-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <label htmlFor="focus" className="mb-1 block text-sm font-medium text-slate-700">
        Anything specific you want covered this time?
      </label>
      <textarea
        id="focus"
        rows={2}
        value={focus}
        onChange={(e) => setFocus(e.target.value)}
        placeholder="Optional — leave blank for your usual interests"
        className="mb-3 w-full resize-none rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-accent focus:outline-none"
      />
      {error && <p className="mb-2 text-sm text-red-600">{error}</p>}
      <button
        onClick={() => {
          setError(null)
          generate.mutate()
        }}
        disabled={disabled || generate.isPending}
        title={disabled && !generate.isPending ? 'An episode is already generating — wait for it to finish first.' : undefined}
        className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:cursor-not-allowed disabled:select-none disabled:opacity-60"
      >
        {generate.isPending ? 'Starting…' : 'Generate now'}
      </button>
      {disabled && <p className="mt-2 text-xs text-slate-500">An episode is already generating.</p>}
    </div>
  )
}

function EpisodeRow({ episode }: { episode: EpisodeListItem }) {
  const running = !isTerminal(episode.status)
  return (
    <Link
      to={`/episodes/${episode.id}`}
      className="block rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-accent"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-medium text-slate-900">{episode.title ?? 'Generating…'}</p>
          <p className="text-xs text-slate-500">
            {formatDate(episode.created_at)} · {formatDuration(episode.duration_s)}
            {episode.focus_request && ' · focus request'}
          </p>
        </div>
        <EpisodeListBadge episode={episode} />
      </div>
      {running && (
        <div className="mt-3">
          <StageStepper status={episode.status} />
        </div>
      )}
      {episode.status === 'failed' && episode.error && (
        <p className="mt-2 truncate text-xs text-red-600">
          {episode.failed_stage ? `${episode.failed_stage}: ` : ''}
          {episode.error}
        </p>
      )}
    </Link>
  )
}

export function EpisodesPage() {
  const { user } = useAuth()
  const needsProfile = user !== null && !user.has_profile
  const episodesQuery = useQuery({
    queryKey: ['episodes'],
    queryFn: api.listEpisodes,
    enabled: !needsProfile,
    refetchInterval: (query) => {
      const data = query.state.data
      return data?.some((e) => !isTerminal(e.status)) ? 3000 : false
    },
  })

  if (needsProfile) return <SetUpProfileCard />
  if (episodesQuery.isLoading) return <Spinner />
  if (episodesQuery.isError) return <p className="text-sm text-red-600">Could not load episodes.</p>

  const episodes = episodesQuery.data ?? []
  const hasRunning = episodes.some((e) => !isTerminal(e.status))

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold text-slate-900">Episodes</h1>
      <NextEpisodeCountdown />
      <NewEpisodePanel disabled={hasRunning} />
      {episodes.length === 0 ? (
        <p className="text-sm text-slate-500">No episodes yet — generate your first one above.</p>
      ) : (
        <div className="space-y-3">
          {episodes.map((e) => (
            <EpisodeRow key={e.id} episode={e} />
          ))}
        </div>
      )}
    </div>
  )
}
