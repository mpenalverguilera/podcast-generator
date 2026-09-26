import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { absoluteUrl, api, ApiError } from '../api/client'
import { isTerminal, type TranscriptSection } from '../api/types'
import { Spinner } from '../components/Spinner'
import { StageStepper, StatusBadge } from '../components/StatusBadge'
import { AudioPlayer } from '../components/AudioPlayer'

function TranscriptSectionView({ section }: { section: TranscriptSection }) {
  return (
    <div className="border-t border-slate-100 pt-4 first:border-t-0 first:pt-0">
      {section.heading && (
        <h3 className="text-sm font-semibold text-slate-900">
          {section.heading}
          {section.topic && <span className="ml-2 text-xs font-normal text-slate-400">{section.topic}</span>}
        </h3>
      )}
      <div className="mt-2 space-y-1.5">
        {section.turns.map((turn, i) => (
          <p key={i} className="text-sm text-slate-700">
            <span className="font-medium text-slate-900">{turn.speaker}: </span>
            {turn.text}
          </p>
        ))}
      </div>
      {section.sources.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-slate-500">
          {section.sources.map((s) => (
            <li key={s.url}>
              <a href={s.url} target="_blank" rel="noreferrer" className="hover:text-accent hover:underline">
                {s.title ?? s.url} {s.outlet && `— ${s.outlet}`}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function RatingButtons({ episodeId, myRating }: { episodeId: number; myRating: 1 | -1 | null }) {
  const queryClient = useQueryClient()
  const rate = useMutation({
    mutationFn: (value: 1 | -1 | 0) =>
      api.sendEvent({ type: 'episode_rated', episode_id: episodeId, payload: { value } }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['episode', episodeId] }),
  })

  function toggle(value: 1 | -1) {
    rate.mutate(myRating === value ? 0 : value)
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => toggle(1)}
        aria-label="Thumbs up"
        className={`rounded-md px-2 py-1 text-lg ${myRating === 1 ? 'bg-emerald-100' : 'hover:bg-slate-100'}`}
      >
        👍
      </button>
      <button
        onClick={() => toggle(-1)}
        aria-label="Thumbs down"
        className={`rounded-md px-2 py-1 text-lg ${myRating === -1 ? 'bg-red-100' : 'hover:bg-slate-100'}`}
      >
        👎
      </button>
    </div>
  )
}

export function EpisodeDetailPage() {
  const { id } = useParams<{ id: string }>()
  const episodeId = Number(id)
  const navigate = useNavigate()

  const episodeQuery = useQuery({
    queryKey: ['episode', episodeId],
    queryFn: () => api.getEpisode(episodeId),
    refetchInterval: (query) => (query.state.data && !isTerminal(query.state.data.status) ? 3000 : false),
  })

  const retry = useMutation({
    mutationFn: () => api.retryEpisode(episodeId),
    onSuccess: () => void episodeQuery.refetch(),
  })

  if (episodeQuery.isLoading) return <Spinner />
  if (episodeQuery.isError || !episodeQuery.data) {
    return <p className="text-sm text-red-600">Could not load this episode.</p>
  }

  const episode = episodeQuery.data

  return (
    <div>
      <button onClick={() => navigate('/')} className="mb-3 text-sm text-slate-500 hover:text-accent">
        ← Back to episodes
      </button>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">{episode.title ?? 'Generating…'}</h1>
          {episode.summary && <p className="mt-1 text-sm text-slate-600">{episode.summary}</p>}
        </div>
        <StatusBadge status={episode.status} />
      </div>

      {!isTerminal(episode.status) && (
        <div className="mb-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <StageStepper status={episode.status} />
        </div>
      )}

      {episode.status === 'failed' && (
        <div className="mb-6 rounded-xl border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-700">
            Failed{episode.failed_stage && ` at ${episode.failed_stage}`}
            {episode.error && `: ${episode.error}`}
          </p>
          <button
            onClick={() => retry.mutate()}
            disabled={retry.isPending}
            className="mt-3 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-60"
          >
            {retry.isPending ? 'Retrying…' : 'Retry'}
          </button>
          {retry.isError && (
            <p className="mt-2 text-xs text-red-600">
              {retry.error instanceof ApiError ? retry.error.message : 'Retry failed.'}
            </p>
          )}
        </div>
      )}

      {episode.audio_url && (
        <div className="mb-6 space-y-3">
          <AudioPlayer episodeId={episode.id} src={absoluteUrl(episode.audio_url)} />
          <RatingButtons episodeId={episode.id} myRating={episode.my_rating} />
        </div>
      )}

      {episode.sections.length > 0 && (
        <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          {episode.sections.map((section, i) => (
            <TranscriptSectionView key={i} section={section} />
          ))}
        </div>
      )}
    </div>
  )
}
