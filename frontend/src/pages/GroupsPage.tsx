import { useState } from 'react'
import { api } from '../api'
import { Badge, CheckList, ConfirmButton, Loading, Message, Modal } from '../components/ui'
import { useAsync } from '../hooks'
import type { GroupType } from '../types'

const TYPES: [GroupType, string][] = [
  ['CLASS', 'Třída'],
  ['SUBGROUP', 'Dělená skupina'],
  ['CROSS_CLASS', 'Skupina napříč třídami'],
  ['ENSEMBLE', 'Soubor / sbor'],
  ['OTHER', 'Jiné'],
]

export function GroupsPage() {
  const groups = useAsync(() => api.groups.list(), [])
  const students = useAsync(() => api.students.list(), [])
  const [draft, setDraft] = useState<{ name: string; code: string; type: GroupType }>({
    name: '',
    code: '',
    type: 'CROSS_CLASS',
  })
  const [editing, setEditing] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('')

  const editingGroup = (groups.data ?? []).find((group) => group.id === editing) ?? null

  const save = async () => {
    setError(null)
    try {
      await api.groups.create({
        name: draft.name.trim(),
        code: draft.code.trim() || null,
        type: draft.type,
      })
      setDraft({ name: '', code: '', type: 'CROSS_CLASS' })
      groups.reload()
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem))
    }
  }

  const candidates = (students.data ?? []).filter((student) =>
    `${student.full_name} ${student.class_group_name ?? ''}`
      .toLowerCase()
      .includes(filter.toLowerCase()),
  )

  return (
    <>
      <h1>Skupiny</h1>
      <p className="lead">
        Třída, dělená informatika, Drama A i sbor jsou tatáž entita: množina konkrétních
        studentů. Solver mezi nimi nedělá rozdíl.
      </p>
      {error ? <Message kind="error">{error}</Message> : null}

      <div className="panel">
        <h2>Nová skupina</h2>
        <div className="row">
          <div style={{ flex: 2 }}>
            <label>Název</label>
            <input
              type="text"
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
            />
          </div>
          <div style={{ flex: 1 }}>
            <label>Kód</label>
            <input
              type="text"
              value={draft.code}
              onChange={(event) => setDraft({ ...draft, code: event.target.value })}
            />
          </div>
          <div style={{ flex: 1 }}>
            <label>Typ</label>
            <select
              value={draft.type}
              onChange={(event) => setDraft({ ...draft, type: event.target.value as GroupType })}
            >
              {TYPES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <button className="primary" onClick={save} disabled={!draft.name.trim()}>
            Přidat
          </button>
        </div>
      </div>

      <div className="panel">
        <h2>Seznam ({groups.data?.length ?? 0})</h2>
        {groups.loading ? (
          <Loading what="skupiny" />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Název</th>
                  <th>Kód</th>
                  <th>Typ</th>
                  <th>Členů</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(groups.data ?? []).map((group) => (
                  <tr key={group.id}>
                    <td>{group.name}</td>
                    <td className="mono">{group.code ?? '—'}</td>
                    <td>
                      <Badge>{TYPES.find(([t]) => t === group.type)?.[1] ?? group.type}</Badge>
                    </td>
                    <td>{group.member_count}</td>
                    <td style={{ textAlign: 'right' }}>
                      <span className="chips" style={{ justifyContent: 'flex-end' }}>
                        <button className="small" onClick={() => setEditing(group.id)}>
                          Členové
                        </button>
                        <ConfirmButton
                          onConfirm={async () => {
                            await api.groups.remove(group.id)
                            groups.reload()
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

      {editingGroup ? (
        <Modal title={`Členové – ${editingGroup.name}`} onClose={() => setEditing(null)}>
          <input
            type="search"
            placeholder="Filtrovat studenty…"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          />
          <div style={{ marginTop: 10 }}>
            <CheckList
              items={candidates}
              selected={editingGroup.student_ids}
              onChange={async (ids) => {
                await api.groups.update(editingGroup.id, { student_ids: ids })
                groups.reload()
              }}
              labelOf={(student) =>
                `${student.full_name}${student.class_group_name ? ` – ${student.class_group_name}` : ''}`
              }
            />
          </div>
          <p className="muted">
            Vybráno {editingGroup.member_count} studentů. Student může být současně v libovolném
            počtu skupin.
          </p>
        </Modal>
      ) : null}
    </>
  )
}
