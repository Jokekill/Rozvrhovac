import { useState } from 'react'
import { api } from '../api'
import { ConfirmButton, Loading, Message } from '../components/ui'
import { useAsync } from '../hooks'

export function TeachersPage() {
  const teachers = useAsync(() => api.teachers.list(), [])
  const [draft, setDraft] = useState({ first_name: '', last_name: '', external_id: '' })
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    setError(null)
    try {
      await api.teachers.create({
        first_name: draft.first_name.trim(),
        last_name: draft.last_name.trim(),
        external_id: draft.external_id.trim() || null,
        max_minutes_per_day: 270,
        max_consecutive_minutes: 135,
      })
      setDraft({ first_name: '', last_name: '', external_id: '' })
      teachers.reload()
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem))
    }
  }

  return (
    <>
      <h1>Učitelé</h1>
      <p className="lead">
        Denní limity vstupují do soft constraintů SC10 (příliš mnoho hodin, příliš dlouhý
        blok). Nedostupnost se zadává na stránce Dostupnost.
      </p>
      {error ? <Message kind="error">{error}</Message> : null}

      <div className="panel">
        <h2>Nový učitel</h2>
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
          <button
            className="primary"
            onClick={save}
            disabled={!draft.first_name.trim() || !draft.last_name.trim()}
          >
            Přidat
          </button>
        </div>
      </div>

      <div className="panel">
        <h2>Seznam ({teachers.data?.length ?? 0})</h2>
        {teachers.loading ? (
          <Loading what="učitele" />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Jméno</th>
                  <th>Externí ID</th>
                  <th>Max. minut/den</th>
                  <th>Max. v kuse</th>
                  <th>Aktivní</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(teachers.data ?? []).map((teacher) => (
                  <tr key={teacher.id}>
                    <td>{teacher.full_name}</td>
                    <td className="mono">{teacher.external_id ?? '—'}</td>
                    <td style={{ width: 120 }}>
                      <input
                        type="number"
                        defaultValue={teacher.max_minutes_per_day ?? ''}
                        onBlur={async (event) => {
                          await api.teachers.update(teacher.id, {
                            max_minutes_per_day: event.target.value
                              ? Number(event.target.value)
                              : null,
                          })
                          teachers.reload()
                        }}
                      />
                    </td>
                    <td style={{ width: 120 }}>
                      <input
                        type="number"
                        defaultValue={teacher.max_consecutive_minutes ?? ''}
                        onBlur={async (event) => {
                          await api.teachers.update(teacher.id, {
                            max_consecutive_minutes: event.target.value
                              ? Number(event.target.value)
                              : null,
                          })
                          teachers.reload()
                        }}
                      />
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={teacher.active}
                        onChange={async (event) => {
                          await api.teachers.update(teacher.id, {
                            active: event.target.checked,
                          })
                          teachers.reload()
                        }}
                      />
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <ConfirmButton
                        onConfirm={async () => {
                          await api.teachers.remove(teacher.id)
                          teachers.reload()
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
