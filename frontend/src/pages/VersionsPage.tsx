import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Badge, ConfirmButton, Loading, Message } from '../components/ui'
import { hhmm, PENALTY_LABELS } from '../format'
import { useAsync } from '../hooks'
import type { VersionCompare } from '../types'

const CHANGE_LABELS: Record<string, string> = {
  ADDED: 'přidáno',
  REMOVED: 'odebráno',
  MOVED: 'přesunuto',
  ROOM_CHANGED: 'jiná učebna',
  UNCHANGED: 'beze změny',
}

export function VersionsPage() {
  const navigate = useNavigate()
  const versions = useAsync(() => api.versions.list(), [])
  const [left, setLeft] = useState<number | null>(null)
  const [right, setRight] = useState<number | null>(null)
  const [comparison, setComparison] = useState<VersionCompare | null>(null)
  const [error, setError] = useState<string | null>(null)

  const compare = async () => {
    if (left === null || right === null) return
    setError(null)
    try {
      setComparison(await api.versions.compare(left, right))
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem))
    }
  }

  return (
    <>
      <h1>Verze rozvrhu</h1>
      <p className="lead">
        Rozvrh se nikdy nepřepisuje destruktivně. Každý běh solveru i každá kopie vytvoří
        novou verzi, kterou lze porovnat a publikovat.
      </p>
      {error ? <Message kind="error">{error}</Message> : null}

      <div className="panel">
        <h2>Seznam</h2>
        {versions.loading ? (
          <Loading what="verze" />
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Název</th>
                <th>Stav</th>
                <th>Hodin</th>
                <th>Skóre</th>
                <th>Vznikla z</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(versions.data ?? []).map((version) => (
                <tr key={version.id}>
                  <td>{version.id}</td>
                  <td>{version.name}</td>
                  <td>
                    <Badge tone={version.status === 'PUBLISHED' ? 'ok' : 'default'}>
                      {version.status}
                    </Badge>
                  </td>
                  <td>{version.item_count}</td>
                  <td>{version.total_penalty ?? '—'}</td>
                  <td className="muted">{version.parent_version_id ?? '—'}</td>
                  <td style={{ textAlign: 'right' }}>
                    <span className="chips" style={{ justifyContent: 'flex-end' }}>
                      <button
                        className="small"
                        onClick={() => {
                          window.localStorage.setItem('timetable.version', String(version.id))
                          navigate('/')
                        }}
                      >
                        Otevřít
                      </button>
                      <button
                        className="small"
                        onClick={async () => {
                          await api.versions.duplicate(version.id)
                          versions.reload()
                        }}
                      >
                        Duplikovat
                      </button>
                      <button
                        className="small"
                        onClick={async () => {
                          await api.versions.publish(version.id)
                          versions.reload()
                        }}
                        disabled={version.status === 'PUBLISHED'}
                      >
                        Publikovat
                      </button>
                      <ConfirmButton
                        onConfirm={async () => {
                          await api.versions.remove(version.id)
                          versions.reload()
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
        )}
      </div>

      <div className="panel">
        <h2>Porovnání verzí</h2>
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>Verze A</label>
            <select
              value={left ?? ''}
              onChange={(event) => setLeft(event.target.value ? Number(event.target.value) : null)}
            >
              <option value="">—</option>
              {(versions.data ?? []).map((version) => (
                <option key={version.id} value={version.id}>
                  {version.name}
                </option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label>Verze B</label>
            <select
              value={right ?? ''}
              onChange={(event) =>
                setRight(event.target.value ? Number(event.target.value) : null)
              }
            >
              <option value="">—</option>
              {(versions.data ?? []).map((version) => (
                <option key={version.id} value={version.id}>
                  {version.name}
                </option>
              ))}
            </select>
          </div>
          <button onClick={compare} disabled={left === null || right === null}>
            Porovnat
          </button>
        </div>

        {comparison ? (
          <>
            <p>
              Změněno <b>{comparison.changed}</b>, beze změny <b>{comparison.unchanged}</b>.
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Aktivita</th>
                    <th>Změna</th>
                    <th>A</th>
                    <th>B</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.items
                    .filter((item) => item.change !== 'UNCHANGED')
                    .map((item, index) => (
                      <tr key={index}>
                        <td>
                          {item.activity_name} #{item.occurrence_index + 1}
                        </td>
                        <td>
                          <Badge tone={item.change === 'MOVED' ? 'warn' : 'default'}>
                            {CHANGE_LABELS[item.change] ?? item.change}
                          </Badge>
                        </td>
                        <td>
                          {item.left_start === null ? '—' : hhmm(item.left_start)}{' '}
                          <span className="muted">{item.left_room ?? ''}</span>
                        </td>
                        <td>
                          {item.right_start === null ? '—' : hhmm(item.right_start)}{' '}
                          <span className="muted">{item.right_room ?? ''}</span>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </div>

      <div className="panel">
        <h2>Skóre publikovaných verzí</h2>
        <div className="stack">
          {(versions.data ?? [])
            .filter((version) => version.penalties)
            .map((version) => (
              <div key={version.id}>
                <b>{version.name}</b>{' '}
                <span className="chips">
                  {Object.entries(version.penalties ?? {}).map(([key, value]) => (
                    <Badge key={key}>
                      {PENALTY_LABELS[key] ?? key}: {value}
                    </Badge>
                  ))}
                </span>
              </div>
            ))}
        </div>
      </div>
    </>
  )
}
