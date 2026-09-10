import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { hhmm, duration } from '../format'
import type { Conflict, MoveCheck, ScheduledActivity } from '../types'
import { Badge, Message } from './ui'

interface Props {
  item: ScheduledActivity | null
  onChanged: () => void
  readOnly?: boolean
}

/**
 * Right hand panel: what the occupancy is, which constraints apply, what is
 * locked and, after a failed move, exactly why it failed (§35).
 */
export function DetailPanel({ item, onChanged, readOnly = false }: Props) {
  const [options, setOptions] = useState<MoveCheck | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setError(null)
    setOptions(null)
    if (!item) return
    api.scheduled
      .roomOptions(item.id, item.start_minute)
      .then(setOptions)
      .catch((problem: Error) => setError(problem.message))
  }, [item?.id, item?.start_minute])

  if (!item) {
    return (
      <div className="panel side-right">
        <h2>Detail aktivity</h2>
        <p className="muted">Vyberte hodinu v rozvrhu.</p>
      </div>
    )
  }

  const act = async (work: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await work()
      onChanged()
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem))
    } finally {
      setBusy(false)
    }
  }

  const moveToRoom = (roomId: number) =>
    act(async () => {
      try {
        await api.scheduled.patch(item.id, { room_id: roomId })
      } catch (problem) {
        if (problem instanceof ApiError && problem.status === 409) {
          const detail = problem.detail as { conflicts?: Conflict[] } | null
          throw new Error(
            (detail?.conflicts ?? []).map((c) => c.message).join(' ') || problem.message,
          )
        }
        throw problem
      }
    })

  return (
    <div className="panel side-right">
      <h2>Detail aktivity</h2>
      {error ? <Message kind="error">{error}</Message> : null}

      <h3 style={{ margin: '0 0 4px' }}>{item.activity_name}</h3>
      <p className="muted" style={{ marginTop: 0 }}>
        {hhmm(item.start_minute)}–{hhmm(item.start_minute + item.duration_minutes)} ·{' '}
        {duration(item.duration_minutes)} · výskyt {item.occurrence_index + 1}
      </p>

      <table>
        <tbody>
          <tr>
            <th>Předmět</th>
            <td>{item.subject_name ?? '—'}</td>
          </tr>
          <tr>
            <th>Učitel</th>
            <td>{item.teacher_names.join(', ') || '—'}</td>
          </tr>
          <tr>
            <th>Učebna</th>
            <td>
              {item.room_name ?? '—'}
              {item.building ? ` (budova ${item.building})` : ''}
            </td>
          </tr>
          <tr>
            <th>Skupiny</th>
            <td>{item.group_names.join(', ') || '—'}</td>
          </tr>
          <tr>
            <th>Studentů</th>
            <td>{item.student_count}</td>
          </tr>
          <tr>
            <th>Typ</th>
            <td>
              <Badge>{item.kind}</Badge>
            </td>
          </tr>
        </tbody>
      </table>

      {!readOnly ? (
        <>
          <h2 style={{ marginTop: 14 }}>Zámky</h2>
          <div className="chips">
            <button
              className="small"
              disabled={busy}
              onClick={() =>
                act(() =>
                  api.scheduled.lock(item.id, {
                    lock_time: !item.lock_time,
                    lock_room: item.lock_room,
                  }),
                )
              }
            >
              {item.lock_time ? '🔒 Čas uzamčen' : 'Uzamknout čas'}
            </button>
            <button
              className="small"
              disabled={busy}
              onClick={() =>
                act(() =>
                  api.scheduled.lock(item.id, {
                    lock_time: item.lock_time,
                    lock_room: !item.lock_room,
                  }),
                )
              }
            >
              {item.lock_room ? '🔒 Učebna uzamčena' : 'Uzamknout učebnu'}
            </button>
            {item.lock_time || item.lock_room ? (
              <button
                className="small"
                disabled={busy}
                onClick={() => act(() => api.scheduled.unlock(item.id))}
              >
                Odemknout vše
              </button>
            ) : null}
          </div>
          <p className="muted" style={{ marginTop: 6 }}>
            Uzamčený čas i učebna se při reoptimalizaci chovají jako hard constraint.
          </p>

          <h2 style={{ marginTop: 14 }}>Učebny v tomto čase</h2>
          {options === null ? (
            <p className="muted">Zjišťuji…</p>
          ) : (
            <div className="stack">
              {options.room_suggestions.map((suggestion) => (
                <div className="split" key={suggestion.room_id}>
                  <span>
                    {suggestion.room_name}{' '}
                    {suggestion.free ? (
                      <Badge tone="ok">volná</Badge>
                    ) : (
                      <Badge tone="warn">{suggestion.reason ?? 'obsazená'}</Badge>
                    )}
                  </span>
                  <button
                    className="small"
                    disabled={busy || suggestion.room_id === item.room_id || !suggestion.free}
                    onClick={() => moveToRoom(suggestion.room_id)}
                  >
                    Přesunout sem
                  </button>
                </div>
              ))}
              {options.room_suggestions.length === 0 ? (
                <p className="muted">Žádná učebna nevyhovuje požadavkům aktivity.</p>
              ) : null}
            </div>
          )}
        </>
      ) : null}
    </div>
  )
}
