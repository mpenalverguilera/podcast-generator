import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../api/client'
import { isTerminal, type EpisodeListItem } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Spinner } from '../components/Spinner'
import { StageStepper, StatusBadge } from '../components/StatusBadge'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
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
        className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-60"
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
        <StatusBadge status={episode.status} />
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
  const episodesQuery = useQuery({
    queryKey: ['episodes'],
    queryFn: api.listEpisodes,
    refetchInterval: (query) => {
      const data = query.state.data
      return data?.some((e) => !isTerminal(e.status)) ? 3000 : false
    },
  })

  if (user && !user.has_profile) return <Navigate to="/settings" replace />
  if (episodesQuery.isLoading) return <Spinner />
  if (episodesQuery.isError) return <p className="text-sm text-red-600">Could not load episodes.</p>

  const episodes = episodesQuery.data ?? []
  const hasRunning = episodes.some((e) => !isTerminal(e.status))

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold text-slate-900">Episodes</h1>
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
