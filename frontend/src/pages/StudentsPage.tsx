import { useState } from 'react'
import { api } from '../api'
import { ConfirmButton, Loading, Message } from '../components/ui'
import { useAsync } from '../hooks'

export function StudentsPage() {
  const students = useAsync(() => api.students.list(), [])
  const groups = useAsync(() => api.groups.list(), [])
  const [draft, setDraft] = useState({ first_name: '', last_name: '', external_id: '', class_group_id: '' })
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const save = async () => {
    setError(null)
    try {
      await api.students.create({
        first_name: draft.first_name.trim(),
        last_name: draft.last_name.trim(),
        external_id: draft.external_id.trim() || null,
        class_group_id: draft.class_group_id ? Number(draft.class_group_id) : null,
      })
      setDraft({ first_name: '', last_name: '', external_id: '', class_group_id: '' })
      students.reload()
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem))
    }
  }

  const visible = (students.data ?? []).filter((student) =>
    student.full_name.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <>
      <h1>Studenti</h1>
      <p className="lead">
        Student je nejnižší úroveň plánování. Konflikty se vyhodnocují nad konkrétními
        studenty, ne nad třídami.
      </p>
      {error ? <Message kind="error">{error}</Message> : null}

      <div className="panel">
        <h2>Nový student</h2>
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>Jméno</label>
            <input
              type="text"
              value={draft.first_name}
              onChange={(event) => setDraft({ ...draft, first_name: event.target.value })}
            />
          </div>
          <div style={{ flex: 1 }}>
            <label>Příjmení</label>
            <input
              type="text"
              value={draft.last_name}
              onChange={(event) => setDraft({ ...draft, last_name: event.target.value })}
            />
          </div>
          <div style={{ flex: 1 }}>
            <label>Externí ID</label>
            <input
              type="text"
              value={draft.external_id}
              onChange={(event) => setDraft({ ...draft, external_id: event.target.value })}
            />
          </div>
          <div style={{ flex: 1 }}>
            <label>Třída</label>
            <select
              value={draft.class_group_id}
              onChange={(event) => setDraft({ ...draft, class_group_id: event.target.value })}
            >
              <option value="">—</option>
              {(groups.data ?? [])
                .filter((group) => group.type === 'CLASS')
                .map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name}
                  </option>
                ))}
            </select>
          </div>
          <button
            className="primary"
            onClick={save}
            disabled={!draft.first_name.trim() || !draft.last_name.trim()}
          >
            Přidat
          </button>
        </div>
        <p className="muted">
          Systém ukládá jen jméno, ID, třídu a členství ve skupinách. Datum narození ani
          kontakty do rozvrhového systému nepatří.
        </p>
      </div>

      <div className="panel">
        <div className="split">
          <h2>Seznam ({visible.length})</h2>
          <input
            type="search"
            placeholder="Hledat…"
            style={{ maxWidth: 220 }}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        {students.loading ? (
          <Loading what="studenty" />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Jméno</th>
                  <th>Externí ID</th>
                  <th>Třída</th>
                  <th>Aktivní</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.map((student) => (
                  <tr key={student.id}>
                    <td>{student.full_name}</td>
                    <td className="mono">{student.external_id ?? '—'}</td>
                    <td>
                      <select
                        value={student.class_group_id ?? ''}
                        onChange={async (event) => {
                          await api.students.update(student.id, {
                            class_group_id: event.target.value
                              ? Number(event.target.value)
                              : null,
                          })
                          students.reload()
                        }}
                      >
                        <option value="">—</option>
                        {(groups.data ?? [])
                          .filter((group) => group.type === 'CLASS')
                          .map((group) => (
                            <option key={group.id} value={group.id}>
                              {group.name}
                            </option>
                          ))}
                      </select>
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={student.active}
                        onChange={async (event) => {
                          await api.students.update(student.id, {
                            active: event.target.checked,
                          })
                          students.reload()
                        }}
                      />
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <ConfirmButton
                        onConfirm={async () => {
                          await api.students.remove(student.id)
                          students.reload()
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
        )}
      </div>
    </>
  )
}
