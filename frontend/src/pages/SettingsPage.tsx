import { useState } from 'react'
import { api } from '../api'
import { Badge, ConfirmButton, Loading, Message } from '../components/ui'
import { hhmm, parseHhmm } from '../format'
import { useAsync } from '../hooks'

const SCALE = [
  [1, 'VERY_LOW'],
  [10, 'LOW'],
  [100, 'MEDIUM'],
  [1000, 'HIGH'],
] as const

export function SettingsPage() {
  const weights = useAsync(() => api.constraints.list(), [])
  const cycle = useAsync(() => api.cycle.get(), [])
  const days = useAsync(() => api.cycle.days(), [])
  const periods = useAsync(() => api.cycle.periods(), [])
  const subjects = useAsync(() => api.subjects.list(), [])
  const [subjectDraft, setSubjectDraft] = useState({ name: '', code: '', color: '#3b6ea5' })
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)

  const updateWeight = async (code: string, body: { weight?: number; enabled?: boolean }) => {
    setError(null)
    try {
      await api.constraints.update(code, body)
      setSaved(`Uloženo: ${code}`)
      weights.reload()
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem))
    }
  }

  return (
    <>
      <h1>Nastavení</h1>
      <p className="lead">
        Váhy soft constraintů jsou data, ne kód. Váha 0 nebo vypnuté pravidlo se do modelu
        vůbec nepromítne.
      </p>
      {error ? <Message kind="error">{error}</Message> : null}
      {saved ? <Message kind="ok">{saved}</Message> : null}

      <div className="panel">
        <h2>Váhy soft constraintů</h2>
        {weights.loading ? (
          <Loading what="váhy" />
        ) : (
          <table>
            <thead>
              <tr>
                <th style={{ width: 60 }}>Kód</th>
                <th>Pravidlo</th>
                <th style={{ width: 120 }}>Váha</th>
                <th style={{ width: 140 }}>Škála</th>
                <th style={{ width: 90 }}>Zapnuto</th>
              </tr>
            </thead>
            <tbody>
              {(weights.data ?? []).map((constraint) => (
                <tr key={constraint.code}>
                  <td className="mono">{constraint.code}</td>
                  <td>
                    {constraint.name}
                    <div className="muted">{constraint.description}</div>
                  </td>
                  <td>
                    <input
                      type="number"
                      min={0}
                      defaultValue={constraint.weight}
                      onBlur={(event) =>
                        updateWeight(constraint.code, { weight: Number(event.target.value) })
                      }
                    />
                  </td>
                  <td>
                    <div className="chips">
                      {SCALE.map(([value, label]) => (
                        <button
                          key={label}
                          className={`small${constraint.weight === value ? ' primary' : ''}`}
                          onClick={() => updateWeight(constraint.code, { weight: value })}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      checked={constraint.enabled}
                      onChange={(event) =>
                        updateWeight(constraint.code, { enabled: event.target.checked })
                      }
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <h2>Plánovací cyklus</h2>
        {cycle.data ? (
          <div className="row">
            <div style={{ width: 140 }}>
              <label>Krok (min)</label>
              <input
                type="number"
                defaultValue={cycle.data.granularity_minutes}
                onBlur={async (event) => {
                  await api.cycle.update({ granularity_minutes: Number(event.target.value) })
                  cycle.reload()
                }}
              />
            </div>
            <div style={{ width: 140 }}>
              <label>Oběd od</label>
              <input
                type="text"
                defaultValue={hhmm(cycle.data.lunch_start_minute)}
                onBlur={async (event) => {
                  const value = parseHhmm(event.target.value)
                  if (value !== null) {
                    await api.cycle.update({ lunch_start_minute: value })
                    cycle.reload()
                  }
                }}
              />
            </div>
            <div style={{ width: 140 }}>
              <label>Oběd do</label>
              <input
                type="text"
                defaultValue={hhmm(cycle.data.lunch_end_minute)}
                onBlur={async (event) => {
                  const value = parseHhmm(event.target.value)
                  if (value !== null) {
                    await api.cycle.update({ lunch_end_minute: value })
                    cycle.reload()
                  }
                }}
              />
            </div>
            <div style={{ width: 160 }}>
              <label>Délka pauzy (min)</label>
              <input
                type="number"
                defaultValue={cycle.data.lunch_break_minutes}
                onBlur={async (event) => {
                  await api.cycle.update({ lunch_break_minutes: Number(event.target.value) })
                  cycle.reload()
                }}
              />
            </div>
            <div style={{ width: 200 }}>
              <label>Max. minut studentovi/den</label>
              <input
                type="number"
                defaultValue={cycle.data.max_student_minutes_per_day}
                onBlur={async (event) => {
                  await api.cycle.update({
                    max_student_minutes_per_day: Number(event.target.value),
                  })
                  cycle.reload()
                }}
              />
            </div>
          </div>
        ) : null}

        <h3>Dny cyklu</h3>
        <table>
          <thead>
            <tr>
              <th>Pořadí</th>
              <th>Týden</th>
              <th>Název</th>
              <th>Začátek</th>
              <th>Konec</th>
            </tr>
          </thead>
          <tbody>
            {(days.data ?? []).map((day) => (
              <tr key={day.id}>
                <td>{day.ordinal}</td>
                <td>{day.week_index === 0 ? 'A' : 'B'}</td>
                <td>{day.name}</td>
                <td>{hhmm(day.start_minute)}</td>
                <td>{hhmm(day.end_minute)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h3>Mřížka hodin</h3>
        <div className="chips">
          {(periods.data ?? []).map((period) => (
            <Badge key={period.id}>
              {period.name} {hhmm(period.start_minute)}–{hhmm(period.end_minute)}
            </Badge>
          ))}
        </div>
      </div>

      <div className="panel">
        <h2>Předměty</h2>
        <div className="row">
          <div style={{ flex: 2 }}>
            <label>Název</label>
            <input
              type="text"
              value={subjectDraft.name}
              onChange={(event) =>
                setSubjectDraft({ ...subjectDraft, name: event.target.value })
              }
            />
          </div>
          <div style={{ flex: 1 }}>
            <label>Kód</label>
            <input
              type="text"
              value={subjectDraft.code}
              onChange={(event) =>
                setSubjectDraft({ ...subjectDraft, code: event.target.value })
              }
            />
          </div>
          <div style={{ width: 90 }}>
            <label>Barva</label>
            <input
              type="color"
              value={subjectDraft.color}
              onChange={(event) =>
                setSubjectDraft({ ...subjectDraft, color: event.target.value })
              }
            />
          </div>
          <button
            className="primary"
            disabled={!subjectDraft.name.trim()}
            onClick={async () => {
              await api.subjects.create({
                name: subjectDraft.name.trim(),
                code: subjectDraft.code.trim() || null,
                color: subjectDraft.color,
              })
              setSubjectDraft({ name: '', code: '', color: '#3b6ea5' })
              subjects.reload()
            }}
          >
            Přidat
          </button>
        </div>
        <table>
          <tbody>
            {(subjects.data ?? []).map((subject) => (
              <tr key={subject.id}>
                <td style={{ width: 30 }}>
                  <span
                    className="swatch"
                    style={{
                      background: subject.color ?? '#999',
                      display: 'inline-block',
                      width: 12,
                      height: 12,
                      borderRadius: 2,
                    }}
                  />
                </td>
                <td>{subject.name}</td>
                <td className="mono">{subject.code ?? '—'}</td>
                <td style={{ textAlign: 'right' }}>
                  <ConfirmButton
                    onConfirm={async () => {
                      await api.subjects.remove(subject.id)
                      subjects.reload()
                    }}
                  >
                    Smazat
                  </ConfirmButton>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
