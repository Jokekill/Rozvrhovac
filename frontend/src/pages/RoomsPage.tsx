import { useState } from 'react'
import { api } from '../api'
import { Badge, CheckList, ConfirmButton, Loading, Message } from '../components/ui'
import { useAsync } from '../hooks'

export function RoomsPage() {
  const rooms = useAsync(() => api.rooms.list(), [])
  const features = useAsync(() => api.roomFeatures.list(), [])
  const [draft, setDraft] = useState({ name: '', code: '', building: '', capacity: '30' })
  const [draftFeatures, setDraftFeatures] = useState<number[]>([])
  const [featureName, setFeatureName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<number | null>(null)

  const save = async () => {
    setError(null)
    try {
      await api.rooms.create({
        name: draft.name.trim(),
        code: draft.code.trim() || null,
        building: draft.building.trim() || null,
        capacity: Number(draft.capacity) || 30,
        feature_ids: draftFeatures,
      })
      setDraft({ name: '', code: '', building: '', capacity: '30' })
      setDraftFeatures([])
      rooms.reload()
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem))
    }
  }

  return (
    <>
      <h1>Učebny</h1>
      <p className="lead">
        Vlastnost učebny (piano, stage, computers…) je tvrdý požadavek aktivity. Kapacita se
        porovnává s počtem konkrétních studentů.
      </p>
      {error ? <Message kind="error">{error}</Message> : null}

      <div className="workspace" style={{ gridTemplateColumns: 'minmax(0, 1fr) 300px' }}>
        <div>
          <div className="panel">
            <h2>Nová učebna</h2>
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
                <label>Budova</label>
                <input
                  type="text"
                  value={draft.building}
                  onChange={(event) => setDraft({ ...draft, building: event.target.value })}
                />
              </div>
              <div style={{ width: 110 }}>
                <label>Kapacita</label>
                <input
                  type="number"
                  value={draft.capacity}
                  onChange={(event) => setDraft({ ...draft, capacity: event.target.value })}
                />
              </div>
              <button className="primary" onClick={save} disabled={!draft.name.trim()}>
                Přidat
              </button>
            </div>
            <label>Vlastnosti</label>
            <CheckList
              items={features.data ?? []}
              selected={draftFeatures}
              onChange={setDraftFeatures}
              labelOf={(feature) => feature.name}
              emptyText="Nejprve založte vlastnost vpravo."
            />
          </div>

          <div className="panel">
            <h2>Seznam ({rooms.data?.length ?? 0})</h2>
            {rooms.loading ? (
              <Loading what="učebny" />
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Název</th>
                      <th>Budova</th>
                      <th>Kapacita</th>
                      <th>Vlastnosti</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {(rooms.data ?? []).map((room) => (
                      <tr key={room.id}>
                        <td>
                          {room.name} <span className="mono muted">{room.code}</span>
                        </td>
                        <td>{room.building ?? '—'}</td>
                        <td>{room.capacity}</td>
                        <td>
                          {editing === room.id ? (
                            <CheckList
                              items={features.data ?? []}
                              selected={room.feature_ids}
                              onChange={async (ids) => {
                                await api.rooms.update(room.id, { feature_ids: ids })
                                rooms.reload()
                              }}
                              labelOf={(feature) => feature.name}
                            />
                          ) : (
                            <span className="chips">
                              {room.feature_names.map((name) => (
                                <Badge key={name}>{name}</Badge>
                              ))}
                              {room.feature_names.length === 0 ? (
                                <span className="muted">—</span>
                              ) : null}
                            </span>
                          )}
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <span className="chips" style={{ justifyContent: 'flex-end' }}>
                            <button
                              className="small"
                              onClick={() => setEditing(editing === room.id ? null : room.id)}
                            >
                              {editing === room.id ? 'Hotovo' : 'Vlastnosti'}
                            </button>
                            <ConfirmButton
                              onConfirm={async () => {
                                await api.rooms.remove(room.id)
                                rooms.reload()
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
        </div>

        <div className="panel side-right">
          <h2>Vlastnosti učeben</h2>
          <div className="row">
            <input
              type="text"
              placeholder="např. grand_piano"
              value={featureName}
              onChange={(event) => setFeatureName(event.target.value)}
            />
            <button
              onClick={async () => {
                if (!featureName.trim()) return
                await api.roomFeatures.create({ name: featureName.trim() })
                setFeatureName('')
                features.reload()
              }}
            >
              Přidat
            </button>
          </div>
          <div className="stack" style={{ marginTop: 10 }}>
            {(features.data ?? []).map((feature) => (
              <div className="split" key={feature.id}>
                <span>{feature.name}</span>
                <ConfirmButton
                  onConfirm={async () => {
                    await api.roomFeatures.remove(feature.id)
                    features.reload()
                    rooms.reload()
                  }}
                >
                  Smazat
                </ConfirmButton>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
