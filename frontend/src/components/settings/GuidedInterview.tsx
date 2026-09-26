import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { InterestProfile } from '../../api/types'
import { Spinner } from '../Spinner'

// Step 1 of the settings page (docs/phases/06-frontend.md): free-text answers
// to a few guided prompts, turned into a structured profile by
// POST /profile/extract. The result isn't saved here -- it replaces the
// editable profile below, which the user still has to Save.
export function GuidedInterview({ onExtracted }: { onExtracted: (profile: InterestProfile) => void }) {
  const questionsQuery = useQuery({ queryKey: ['profile-questions'], queryFn: api.profileQuestions })
  const [answers, setAnswers] = useState<Record<string, string>>({})

  const extract = useMutation({
    mutationFn: () => api.extractProfile(answers),
    onSuccess: onExtracted,
  })

  const hasAnswer = Object.values(answers).some((v) => v.trim())

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-1 text-sm font-semibold text-slate-900">Tell us what you follow</h2>
      <p className="mb-3 text-xs text-slate-500">
        Answer as much as you like, then build your profile. You can edit the result below before saving.
      </p>
      {questionsQuery.isLoading ? (
        <Spinner />
      ) : (
        <div className="space-y-3">
          {questionsQuery.data?.map((q) => (
            <div key={q.key}>
              <label className="mb-1 block text-xs font-medium text-slate-600">{q.question}</label>
              <textarea
                rows={2}
                value={answers[q.key] ?? ''}
                onChange={(e) => setAnswers((a) => ({ ...a, [q.key]: e.target.value }))}
                className="w-full resize-none rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-accent focus:outline-none"
              />
            </div>
          ))}
        </div>
      )}
      {extract.isError && (
        <p className="mt-2 text-sm text-red-600">Could not build a profile from those answers.</p>
      )}
      <button
        onClick={() => extract.mutate()}
        disabled={extract.isPending || !hasAnswer}
        title={hasAnswer ? undefined : 'Type an answer to at least one question first'}
        className="mt-3 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-60"
      >
        {extract.isPending ? 'Building…' : 'Build my profile'}
      </button>
    </div>
  )
}
