import { useState } from 'react'
import { api } from '../api'
import { Badge, CheckList, ConfirmButton, Loading, Message, Modal } from '../components/ui'
import { duration } from '../format'
import { useAsync } from '../hooks'
import type { Activity, ActivityKind } from '../types'

const KINDS: [ActivityKind, string][] = [
  ['STANDARD', 'Běžná hodina'],
  ['SPLIT', 'Dělená skupina'],
  ['CROSS_CLASS', 'Napříč třídami'],
  ['ENSEMBLE', 'Soubor / sbor'],
  ['INDIVIDUAL', 'Individuální'],
  ['OTHER', 'Jiné'],
]

const EMPTY = {
  name: '',
  subject_id: null as number | null,
  kind: 'STANDARD' as ActivityKind,
  duration_minutes: 45,
  occurrences_per_cycle: 1,
  align_to_periods: true,
  min_capacity: null as number | null,
  teacher_ids: [] as number[],
  group_ids: [] as number[],
  student_ids: [] as number[],
  required_feature_ids: [] as number[],
  preferred_room_ids: [] as number[],
  forbidden_room_ids: [] as number[],
}

export function ActivitiesPage() {
  const activities = useAsync(() => api.activities.list(), [])
  const subjects = useAsync(() => api.subjects.list(), [])
  const teachers = useAsync(() => api.teachers.list(), [])
  const groups = useAsync(() => api.groups.list(), [])
  const students = useAsync(() => api.students.list(), [])
  const rooms = useAsync(() => api.rooms.list(), [])
  const features = useAsync(() => api.roomFeatures.list(), [])

  const [form, setForm] = useState<typeof EMPTY | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const openNew = () => {
    setEditingId(null)
    setForm({ ...EMPTY })
  }

  const openEdit = (activity: Activity) => {
    setEditingId(activity.id)
    setForm({
      name: activity.name,
      subject_id: activity.subject_id,
      kind: activity.kind,
      duration_minutes: activity.duration_minutes,
      occurrences_per_cycle: activity.occurrences_per_cycle,
      align_to_periods: activity.align_to_periods,
      min_capacity: activity.min_capacity,
      teacher_ids: activity.teacher_ids,
      group_ids: activity.group_ids,
      student_ids: activity.student_ids,
      required_feature_ids: activity.required_feature_ids,
      preferred_room_ids: activity.preferred_room_ids,
      forbidden_room_ids: activity.forbidden_room_ids,
    })
  }

  const save = async () => {
    if (!form) return
    setError(null)
    try {
      if (editingId === null) await api.activities.create(form)
      else await api.activities.update(editingId, form)
      setForm(null)
      activities.reload()
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem))
    }
  }

  const visible = (activities.data ?? []).filter((activity) =>
    activity.name.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <>
      <div className="split">
        <div>
          <h1>Aktivity</h1>
          <p className="lead">
            Jedna entita pro všechno: běžná hodina, půlená skupina, sbor i lekce 1 : 1. Liší
            se jen hodnotami.
          </p>
        </div>
        <button className="primary" onClick={openNew}>
          Nová aktivita
        </button>
      </div>
      {error ? <Message kind="error">{error}</Message> : null}

      <div className="panel">
        <div className="split">
          <h2>Seznam ({visible.length})</h2>
          <input
            type="search"
            placeholder="Hledat…"
            style={{ maxWidth: 240 }}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        {activities.loading ? (
          <Loading what="aktivity" />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Název</th>
                  <th>Typ</th>
                  <th>Délka</th>
                  <th>Týdně</th>
                  <th>Učitelé</th>
                  <th>Účastníků</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.map((activity) => (
                  <tr key={activity.id}>
                    <td>
                      {activity.name}
                      {activity.fixed_start_minute !== null ? (
                        <>
                          {' '}
                          <Badge tone="warn">pevná hodina</Badge>
                        </>
                      ) : null}
                    </td>
                    <td>
                      <Badge>{KINDS.find(([k]) => k === activity.kind)?.[1] ?? activity.kind}</Badge>
                    </td>
                    <td>{duration(activity.duration_minutes)}</td>
                    <td>{activity.occurrences_per_cycle}×</td>
                    <td>{activity.teacher_names.join(', ') || '—'}</td>
                    <td>{activity.participant_count}</td>
                    <td style={{ textAlign: 'right' }}>
                      <span className="chips" style={{ justifyContent: 'flex-end' }}>
                        <button className="small" onClick={() => openEdit(activity)}>
                          Upravit
                        </button>
                        <ConfirmButton
                          onConfirm={async () => {
                            await api.activities.remove(activity.id)
                            activities.reload()
                          }}
                        >
                          Smazat
                        </ConfirmButton>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {form ? (
        <Modal
          title={editingId === null ? 'Nová aktivita' : 'Úprava aktivity'}
          onClose={() => setForm(null)}
        >
          <div className="row">
            <div style={{ flex: 3 }}>
              <label>Název</label>
              <input
                type="text"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label>Předmět</label>
              <select
                value={form.subject_id ?? ''}
                onChange={(event) =>
                  setForm({
                    ...form,
                    subject_id: event.target.value ? Number(event.target.value) : null,
                  })
                }
              >
                <option value="">—</option>
                {(subjects.data ?? []).map((subject) => (
                  <option key={subject.id} value={subject.id}>
                    {subject.name}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label>Typ</label>
              <select
                value={form.kind}
                onChange={(event) =>
                  setForm({ ...form, kind: event.target.value as ActivityKind })
                }
              >
                {KINDS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="row">
            <div style={{ width: 130 }}>
              <label>Délka (min)</label>
              <input
                type="number"
                value={form.duration_minutes}
                onChange={(event) =>
                  setForm({ ...form, duration_minutes: Number(event.target.value) })
                }
              />
            </div>
            <div style={{ width: 130 }}>
              <label>Výskytů za cyklus</label>
              <input
                type="number"
                value={form.occurrences_per_cycle}
                onChange={(event) =>
                  setForm({ ...form, occurrences_per_cycle: Number(event.target.value) })
                }
              />
            </div>
            <div style={{ width: 150 }}>
              <label>Min. kapacita učebny</label>
              <input
                type="number"
                value={form.min_capacity ?? ''}
                onChange={(event) =>
                  setForm({
                    ...form,
                    min_capacity: event.target.value ? Number(event.target.value) : null,
                  })
                }
              />
            </div>
            <label style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 8 }}>
              <input
                type="checkbox"
                style={{ width: 'auto' }}
                checked={form.align_to_periods}
                onChange={(event) =>
                  setForm({ ...form, align_to_periods: event.target.checked })
                }
              />
              Zarovnat na mřížku hodin
            </label>
          </div>

          <div className="row" style={{ alignItems: 'flex-start' }}>
            <div style={{ flex: 1 }}>
              <label>Učitelé</label>
              <CheckList
                items={teachers.data ?? []}
                selected={form.teacher_ids}
                onChange={(ids) => setForm({ ...form, teacher_ids: ids })}
                labelOf={(teacher) => teacher.full_name}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label>Skupiny</label>
              <CheckList
                items={groups.data ?? []}
                selected={form.group_ids}
                onChange={(ids) => setForm({ ...form, group_ids: ids })}
                labelOf={(group) => `${group.name} (${group.member_count})`}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label>Jednotliví studenti</label>
              <CheckList
                items={students.data ?? []}
                selected={form.student_ids}
                onChange={(ids) => setForm({ ...form, student_ids: ids })}
                labelOf={(student) => student.full_name}
              />
            </div>
          </div>

          <div className="row" style={{ alignItems: 'flex-start' }}>
            <div style={{ flex: 1 }}>
              <label>Povinné vlastnosti učebny</label>
              <CheckList
                items={features.data ?? []}
                selected={form.required_feature_ids}
                onChange={(ids) => setForm({ ...form, required_feature_ids: ids })}
                labelOf={(feature) => feature.name}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label>Preferované učebny</label>
              <CheckList
                items={rooms.data ?? []}
                selected={form.preferred_room_ids}
                onChange={(ids) => setForm({ ...form, preferred_room_ids: ids })}
                labelOf={(room) => room.name}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label>Zakázané učebny</label>
              <CheckList
                items={rooms.data ?? []}
                selected={form.forbidden_room_ids}
                onChange={(ids) => setForm({ ...form, forbidden_room_ids: ids })}
                labelOf={(room) => room.name}
              />
            </div>
          </div>

          <div className="chips" style={{ marginTop: 10 }}>
            <button className="primary" onClick={save} disabled={!form.name.trim()}>
              Uložit
            </button>
            <button onClick={() => setForm(null)}>Zrušit</button>
          </div>
        </Modal>
      ) : null}
    </>
  )
}
