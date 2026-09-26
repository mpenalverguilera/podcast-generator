import { useState, type KeyboardEvent } from 'react'

export function TagInput({
  label,
  values,
  onChange,
  placeholder,
}: {
  label?: string
  values: string[]
  onChange: (values: string[]) => void
  placeholder?: string
}) {
  const [draft, setDraft] = useState('')

  function commit() {
    const value = draft.trim()
    if (value && !values.includes(value)) onChange([...values, value])
    setDraft('')
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      commit()
    } else if (e.key === 'Backspace' && draft === '' && values.length > 0) {
      onChange(values.slice(0, -1))
    }
  }

  return (
    <div>
      {label && <label className="mb-1 block text-xs font-medium text-slate-600">{label}</label>}
      <div className="flex flex-wrap gap-1 rounded-md border border-slate-300 p-1.5 focus-within:border-accent">
        {values.map((v) => (
          <span
            key={v}
            className="flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700"
          >
            {v}
            <button
              type="button"
              onClick={() => onChange(values.filter((x) => x !== v))}
              className="text-slate-400 hover:text-slate-700"
            >
              ×
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={commit}
          placeholder={values.length === 0 ? placeholder : undefined}
          className="min-w-24 flex-1 border-none text-xs outline-none"
        />
      </div>
    </div>
  )
}
