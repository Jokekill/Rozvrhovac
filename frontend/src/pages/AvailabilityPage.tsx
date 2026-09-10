import { useState } from 'react'
import { api } from '../api'
import { Badge, ConfirmButton, Loading, Message } from '../components/ui'
import { hhmm, parseHhmm } from '../format'
import { useAsync } from '../hooks'
import type { AvailabilityKind, OwnerType } from '../types'

export function AvailabilityPage() {
  const teachers = useAsync(() => api.teachers.list(), [])
  const students = useAsync(() => api.students.list(), [])
  const rooms = useAsync(() => api.rooms.list(), [])
  const days = useAsync(() => api.cycle.days(), [])
  const [ownerType, setOwnerType] = useState<OwnerType>('TEACHER')
  const [ownerId, setOwnerId] = useState<number | null>(null)
  const windows = useAsync(
    async () =>
      ownerId === null ? [] : api.availability.list({ owner_type: ownerType, owner_id: ownerId }),
    [ownerType, ownerId],
  )

  const [draft, setDraft] = useState({
    kind: 'UNAVAILABLE' as AvailabilityKind,
    day_ordinal: '' as string,
    start: '08:00',
    end: '12:00',
    note: '',
  })
  const [error, setError] = useState<string | null>(null)

  const owners =
    ownerType === 'TEACHER'
      ? (teachers.data ?? []).map((t) => ({ id: t.id, label: t.full_name }))
      : ownerType === 'STUDENT'
        ? (students.data ?? []).map((s) => ({ id: s.id, label: s.full_name }))
        : (rooms.data ?? []).map((r) => ({ id: r.id, label: r.name }))

  const add = async () => {
    setError(null)
    const start = parseHhmm(draft.start)
    const end = parseHhmm(draft.end)
    if (start === null || end === null || end <= start) {
      setError('Zadejte platný časový interval ve tvaru HH:MM.')
      return
    }
    if (ownerId === null) return
    try {
      await api.availability.create({
        owner_type: ownerType,
        owner_id: ownerId,
        kind: draft.kind,
        day_ordinal: draft.day_ordinal === '' ? null : Number(draft.day_ordinal),
        start_minute: start,
        end_minute: end,
        note: draft.note.trim() || null,
      })
      windows.reload()
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem))
    }
  }

  return (
    <>
      <h1>Dostupnost</h1>
      <p className="lead">
        Výchozí stav je „dostupný“. Omezení se zadává jako nedostupnost (hard constraint),
        preference jako PREFERRED (soft constraint).
      </p>
      {error ? <Message kind="error">{error}</Message> : null}

      <div className="panel">
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>Typ</label>
            <select
              value={ownerType}
              onChange={(event) => {
                setOwnerType(event.target.value as OwnerType)
                setOwnerId(null)
              }}
            >
              <option value="TEACHER">Učitel</option>
              <option value="STUDENT">Student</option>
              <option value="ROOM">Učebna</option>
            </select>
          </div>
          <div style={{ flex: 2 }}>
            <label>Koho se týká</label>
            <select
              value={ownerId ?? ''}
              onChange={(event) =>
                setOwnerId(event.target.value ? Number(event.target.value) : null)
              }
            >
              <option value="">— vyberte —</option>
              {owners.map((owner) => (
                <option key={owner.id} value={owner.id}>
                  {owner.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {ownerId !== null ? (
        <>
          <div className="panel">
            <h2>Nové okno</h2>
            <div className="row">
              <div style={{ flex: 1 }}>
                <label>Druh</label>
                <select
                  value={draft.kind}
                  onChange={(event) =>
                    setDraft({ ...draft, kind: event.target.value as AvailabilityKind })
                  }
                >
                  <option value="UNAVAILABLE">Nedostupný</option>
                  <option value="PREFERRED">Preferovaný čas</option>
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label>Den</label>
                <select
                  value={draft.day_ordinal}
                  onChange={(event) => setDraft({ ...draft, day_ordinal: event.target.value })}
                >
                  <option value="">Každý den</option>
                  {(days.data ?? []).map((day) => (
                    <option key={day.ordinal} value={day.ordinal}>
                      {day.name}
                    </option>
                  ))}
                </select>
              </div>
              <div style={{ width: 110 }}>
                <label>Od</label>
                <input
                  type="text"
                  value={draft.start}
                  onChange={(event) => setDraft({ ...draft, start: event.target.value })}
                />
              </div>
              <div style={{ width: 110 }}>
                <label>Do</label>
                <input
                  type="text"
                  value={draft.end}
                  onChange={(event) => setDraft({ ...draft, end: event.target.value })}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label>Poznámka</label>
                <input
                  type="text"
                  value={draft.note}
                  onChange={(event) => setDraft({ ...draft, note: event.target.value })}
                />
              </div>
              <button className="primary" onClick={add}>
                Přidat
              </button>
            </div>
          </div>

          <div className="panel">
            <h2>Zadaná okna</h2>
            {windows.loading ? (
              <Loading what="dostupnost" />
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Druh</th>
                    <th>Den</th>
                    <th>Od</th>
                    <th>Do</th>
                    <th>Poznámka</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {(windows.data ?? []).map((window) => (
                    <tr key={window.id}>
                      <td>
                        <Badge tone={window.kind === 'UNAVAILABLE' ? 'error' : 'ok'}>
                          {window.kind === 'UNAVAILABLE' ? 'Nedostupný' : 'Preferuje'}
                        </Badge>
                      </td>
                      <td>
                        {window.day_ordinal === null
                          ? 'každý den'
                          : ((days.data ?? []).find((d) => d.ordinal === window.day_ordinal)
                              ?.name ?? window.day_ordinal)}
                      </td>
                      <td>{hhmm(window.start_minute)}</td>
                      <td>{hhmm(window.end_minute)}</td>
                      <td className="muted">{window.note ?? '—'}</td>
                      <td style={{ textAlign: 'right' }}>
                        <ConfirmButton
                          onConfirm={async () => {
                            await api.availability.remove(window.id)
                            windows.reload()
                          }}
                        >
                          Smazat
                        </ConfirmButton>
                      </td>
                    </tr>
                  ))}
                  {(windows.data ?? []).length === 0 ? (
                    <tr>
                      <td colSpan={6} className="muted">
                        Bez omezení – dostupný po celý cyklus.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            )}
          </div>
        </>
      ) : null}
    </>
  )
}
