import type { InterestProfile, Topic } from '../../api/types'
import { TagInput } from './TagInput'

const DEPTHS: Topic['depth'][] = ['headlines', 'deep']

function emptyTopic(): Topic {
  return { name: '', description: '', include: [], exclude: [], depth: 'headlines' }
}

function TopicCard({
  topic,
  onChange,
  onRemove,
}: {
  topic: Topic
  onChange: (topic: Topic) => void
  onRemove: () => void
}) {
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <input
          value={topic.name}
          onChange={(e) => onChange({ ...topic, name: e.target.value })}
          placeholder="Topic name"
          className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-sm font-medium focus:border-accent focus:outline-none"
        />
        <button type="button" onClick={onRemove} className="text-xs text-slate-400 hover:text-red-600">
          Remove
        </button>
      </div>
      <textarea
        rows={2}
        value={topic.description}
        onChange={(e) => onChange({ ...topic, description: e.target.value })}
        placeholder="What this topic covers"
        className="mb-2 w-full resize-none rounded-md border border-slate-300 px-2 py-1 text-sm focus:border-accent focus:outline-none"
      />
      <div className="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <TagInput
          label="Include"
          values={topic.include}
          onChange={(v) => onChange({ ...topic, include: v })}
          placeholder="add a term…"
        />
        <TagInput
          label="Exclude"
          values={topic.exclude}
          onChange={(v) => onChange({ ...topic, exclude: v })}
          placeholder="add a term…"
        />
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span className="font-medium text-slate-600">Depth:</span>
        {DEPTHS.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => onChange({ ...topic, depth: d })}
            className={`rounded-full px-2 py-0.5 ${
              topic.depth === d ? 'bg-accent text-white' : 'bg-slate-100 hover:bg-slate-200'
            }`}
          >
            {d}
          </button>
        ))}
      </div>
    </div>
  )
}

export function ProfileEditor({
  profile,
  onChange,
}: {
  profile: InterestProfile
  onChange: (profile: InterestProfile) => void
}) {
  function updateTopic(index: number, topic: Topic) {
    const topics = [...profile.topics]
    topics[index] = topic
    onChange({ ...profile, topics })
  }

  function removeTopic(index: number) {
    onChange({ ...profile, topics: profile.topics.filter((_, i) => i !== index) })
  }

  function addTopic() {
    if (profile.topics.length >= 8) return
    onChange({ ...profile, topics: [...profile.topics, emptyTopic()] })
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-slate-900">Your profile</h2>
      {profile.topics.length === 0 && (
        <p className="mb-3 text-sm text-slate-500">
          No topics yet — build one from the interview above, or add one directly.
        </p>
      )}
      <div className="space-y-3">
        {profile.topics.map((topic, i) => (
          <TopicCard key={i} topic={topic} onChange={(t) => updateTopic(i, t)} onRemove={() => removeTopic(i)} />
        ))}
      </div>
      <button
        type="button"
        onClick={addTopic}
        disabled={profile.topics.length >= 8}
        className="mt-3 rounded-md border border-dashed border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:border-accent hover:text-accent disabled:opacity-50"
      >
        + Add topic
      </button>
      <div className="mt-4 border-t border-slate-100 pt-3">
        <TagInput
          label="Always avoid"
          values={profile.avoid}
          onChange={(v) => onChange({ ...profile, avoid: v })}
          placeholder="e.g. celebrity gossip"
        />
      </div>
    </div>
  )
}
