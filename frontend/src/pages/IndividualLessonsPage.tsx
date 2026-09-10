import { useEffect, useState } from 'react'
import { api } from '../api'
import { ConfirmButton, Loading, Message } from '../components/ui'
import { useAsync } from '../hooks'
import type { IndividualLesson } from '../types'

interface Row {
  key: string
  id: number | null
  student_id: number | null
  subject_id: number | null
  teacher_id: number | null
  duration_minutes: number
  occurrences_per_cycle: number
  allowed_day_ordinals: number[]
  required_feature_ids: number[]
  active: boolean
}

const DURATIONS = [30, 45, 60, 90]

function toRow(lesson: IndividualLesson): Row {
  return {
    key: `saved-${lesson.id}`,
    id: lesson.id,
    student_id: lesson.student_id,
    subject_id: lesson.subject_id,
    teacher_id: lesson.teacher_id,
    duration_minutes: lesson.duration_minutes,
    occurrences_per_cycle: lesson.occurrences_per_cycle,
    allowed_day_ordinals: lesson.allowed_day_ordinals,
    required_feature_ids: lesson.required_feature_ids,
    active: lesson.active,
  }
}

let counter = 0

/**
 * Bulk editor for one-to-one tuition (§8). Underneath these are ordinary
 * activities; the school just has hundreds of them and should not fill in the
 * generic form hundreds of times.
 */
export function IndividualLessonsPage() {
  const lessons = useAsync(() => api.individualLessons.list(), [])
  const students = useAsync(() => api.students.list(), [])
  const teachers = useAsync(() => api.teachers.list(), [])
  const subjects = useAsync(() => api.subjects.list(), [])
  const features = useAsync(() => api.roomFeatures.list(), [])
  const days = useAsync(() => api.cycle.days(), [])

  const [rows, setRows] = useState<Row[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (lessons.data) setRows(lessons.data.map(toRow))
  }, [lessons.data])

  const update = (key: string, patch: Partial<Row>) =>
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)))

  const addRow = () => {
    counter += 1
    setRows((current) => [
      ...current,
      {
        key: `new-${counter}`,
        id: null,
        student_id: null,
        subject_id: null,
        teacher_id: null,
        duration_minutes: 45,
        occurrences_per_cycle: 1,
        allowed_day_ordinals: [],
        required_feature_ids: [],
        active: true,
      },
    ])
  }

  const save = async () => {
    setError(null)
    setSaved(null)
    const payload = rows.filter((row) => row.student_id !== null)
    if (payload.length !== rows.length) {
      setError('Každý řádek musí mít vybraného studenta.')
      return
    }
    setBusy(true)
    try {
      await api.individualLessons.bulk(
        payload.map((row) => ({
          id: row.id,
          student_id: row.student_id,
          subject_id: row.subject_id,
          teacher_id: row.teacher_id,
          duration_minutes: row.duration_minutes,
          occurrences_per_cycle: row.occurrences_per_cycle,
          allowed_day_ordinals: row.allowed_day_ordinals,
          required_feature_ids: row.required_feature_ids,
          active: row.active,
        })),
      )
      setSaved(`Uloženo ${payload.length} lekcí.`)
      lessons.reload()
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem))
    } finally {
      setBusy(false)
    }
  }

  const toggleDay = (row: Row, ordinal: number) => {
    const next = row.allowed_day_ordinals.includes(ordinal)
      ? row.allowed_day_ordinals.filter((value) => value !== ordinal)
      : [...row.allowed_day_ordinals, ordinal].sort((a, b) => a - b)
    update(row.key, { allowed_day_ordinals: next })
  }

  if (lessons.loading) return <Loading what="individuální výuku" />

  return (
    <>
      <div className="split">
        <div>
          <h1>Individuální výuka</h1>
          <p className="lead">
            Hromadný editor lekcí 1 : 1. Prázdný výběr dnů znamená „kterýkoli den“.
          </p>
        </div>
        <div className="chips">
          <button onClick={addRow}>Přidat řádek</button>
          <button className="primary" onClick={save} disabled={busy}>
            Uložit vše
          </button>
        </div>
      </div>

      {error ? <Message kind="error">{error}</Message> : null}
      {saved ? <Message kind="ok">{saved}</Message> : null}

      <div className="panel">
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th style={{ minWidth: 180 }}>Student</th>
                <th>Třída</th>
                <th style={{ minWidth: 130 }}>Předmět</th>
                <th style={{ minWidth: 150 }}>Učitel</th>
                <th>Délka</th>
                <th>Týdně</th>
                <th style={{ minWidth: 190 }}>Povolené dny</th>
                <th style={{ minWidth: 140 }}>Učebna vyžaduje</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const student = (students.data ?? []).find((s) => s.id === row.student_id)
                return (
                  <tr key={row.key}>
                    <td>
                      <select
                        value={row.student_id ?? ''}
                        onChange={(event) =>
                          update(row.key, {
                            student_id: event.target.value ? Number(event.target.value) : null,
                          })
                        }
                      >
                        <option value="">— vyberte —</option>
                        {(students.data ?? []).map((option) => (
                          <option key={option.id} value={option.id}>
                            {option.full_name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="muted">{student?.class_group_name ?? '—'}</td>
                    <td>
                      <select
                        value={row.subject_id ?? ''}
                        onChange={(event) =>
                          update(row.key, {
                            subject_id: event.target.value ? Number(event.target.value) : null,
                          })
                        }
                      >
                        <option value="">—</option>
                        {(subjects.data ?? []).map((option) => (
                          <option key={option.id} value={option.id}>
                            {option.name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <select
                        value={row.teacher_id ?? ''}
                        onChange={(event) =>
                          update(row.key, {
                            teacher_id: event.target.value ? Number(event.target.value) : null,
                          })
                        }
                      >
                        <option value="">—</option>
                        {(teachers.data ?? []).map((option) => (
                          <option key={option.id} value={option.id}>
                            {option.full_name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td style={{ width: 90 }}>
                      <select
                        value={row.duration_minutes}
                        onChange={(event) =>
                          update(row.key, { duration_minutes: Number(event.target.value) })
                        }
                      >
                        {DURATIONS.map((value) => (
                          <option key={value} value={value}>
                            {value}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td style={{ width: 70 }}>
                      <input
                        type="number"
                        min={1}
                        value={row.occurrences_per_cycle}
                        onChange={(event) =>
                          update(row.key, {
                            occurrences_per_cycle: Math.max(1, Number(event.target.value)),
                          })
                        }
                      />
                    </td>
                    <td>
                      <div className="chips">
                        {(days.data ?? []).map((day) => (
                          <button
                            key={day.ordinal}
                            className={`small${
                              row.allowed_day_ordinals.includes(day.ordinal) ? ' primary' : ''
                            }`}
                            onClick={() => toggleDay(row, day.ordinal)}
                            type="button"
                          >
                            {day.name.slice(0, 2)}
                          </button>
                        ))}
                      </div>
                    </td>
                    <td>
                      <select
                        value={row.required_feature_ids[0] ?? ''}
                        onChange={(event) =>
                          update(row.key, {
                            required_feature_ids: event.target.value
                              ? [Number(event.target.value)]
                              : [],
                          })
                        }
                      >
                        <option value="">—</option>
                        {(features.data ?? []).map((feature) => (
                          <option key={feature.id} value={feature.id}>
                            {feature.name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {row.id === null ? (
                        <button
                          className="small"
                          onClick={() =>
                            setRows((current) => current.filter((item) => item.key !== row.key))
                          }
                        >
                          Odebrat
                        </button>
                      ) : (
                        <ConfirmButton
                          onConfirm={async () => {
                            await api.individualLessons.bulk([], [row.id as number])
                            lessons.reload()
                          }}
                        >
                          Smazat
                        </ConfirmButton>
                      )}
                    </td>
                  </tr>
                )
              })}
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={9} className="muted">
                    Zatím žádné individuální lekce. Můžete je také importovat z CSV.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
