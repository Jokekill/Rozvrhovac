import type { ReactNode } from 'react'
import { useState } from 'react'

export function Message({ kind, children }: { kind: 'error' | 'ok'; children: ReactNode }) {
  return <div className={`message ${kind}`}>{children}</div>
}

export function Loading({ what = 'data' }: { what?: string }) {
  return <p className="muted">Načítám {what}…</p>
}

export function Badge({
  tone = 'default',
  children,
}: {
  tone?: 'default' | 'ok' | 'warn' | 'error'
  children: ReactNode
}) {
  return <span className={`badge ${tone === 'default' ? '' : tone}`}>{children}</span>
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string
  children: ReactNode
  hint?: string
}) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {hint ? <div className="muted mono">{hint}</div> : null}
    </div>
  )
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal" onClick={(event) => event.stopPropagation()} role="dialog">
        <div className="split">
          <h2>{title}</h2>
          <button onClick={onClose}>Zavřít</button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function ConfirmButton({
  onConfirm,
  children,
  question = 'Opravdu smazat?',
}: {
  onConfirm: () => void
  children: ReactNode
  question?: string
}) {
  const [armed, setArmed] = useState(false)
  if (!armed) {
    return (
      <button className="small danger" onClick={() => setArmed(true)}>
        {children}
      </button>
    )
  }
  return (
    <span className="chips">
      <button
        className="small danger"
        onClick={() => {
          setArmed(false)
          onConfirm()
        }}
      >
        {question}
      </button>
      <button className="small" onClick={() => setArmed(false)}>
        Ne
      </button>
    </span>
  )
}

export function CheckList<T extends { id: number }>({
  items,
  selected,
  onChange,
  labelOf,
  emptyText = 'Žádné položky',
}: {
  items: T[]
  selected: number[]
  onChange: (ids: number[]) => void
  labelOf: (item: T) => string
  emptyText?: string
}) {
  if (items.length === 0) return <p className="muted">{emptyText}</p>
  const toggle = (id: number) => {
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id])
  }
  return (
    <div className="checklist">
      {items.map((item) => (
        <label key={item.id}>
          <input
            type="checkbox"
            checked={selected.includes(item.id)}
            onChange={() => toggle(item.id)}
          />
          {labelOf(item)}
        </label>
      ))}
    </div>
  )
}
