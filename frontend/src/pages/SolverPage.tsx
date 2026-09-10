import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Badge, Loading, Message } from '../components/ui'
import { PENALTY_LABELS } from '../format'
import { useAsync } from '../hooks'
import type { DiagnosticItem, SolverRun } from '../types'

const PRESETS: [number, string][] = [
  [10, '10 s – rychlý návrh'],
  [60, '60 s – běžný'],
  [300, '5 min – kvalitnější optimalizace'],
]

function statusTone(status: string): 'ok' | 'warn' | 'error' | 'default' {
  if (status === 'OPTIMAL' || status === 'FEASIBLE') return 'ok'
  if (status === 'RUNNING' || status === 'QUEUED') return 'warn'
  if (status === 'INFEASIBLE' || status === 'FAILED') return 'error'
  return 'default'
}

export function SolverPage() {
  const navigate = useNavigate()
  const runs = useAsync(() => api.solver.runs(), [])
  const versions = useAsync(() => api.versions.list(), [])
  const [timeLimit, setTimeLimit] = useState(60)
  const [baseVersionId, setBaseVersionId] = useState<number | null>(null)
  const [reoptimize, setReoptimize] = useState(true)
  const [diagnostics, setDiagnostics] = useState<DiagnosticItem[] | null>(null)
  const [current, setCurrent] = useState<SolverRun | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!current || !['QUEUED', 'RUNNING'].includes(current.status)) return
    const timer = window.setInterval(async () => {
      try {
        const fresh = await api.solver.run(current.id)
        setCurrent(fresh)
        if (!['QUEUED', 'RUNNING'].includes(fresh.status)) {
          runs.reload()
          versions.reload()
        }
      } catch {
        /* keep polling */
      }
    }, 2000)
    return () => window.clearInterval(timer)
  }, [current?.id, current?.status])

  const validate = async () => {
    setError(null)
    setBusy(true)
    try {
      setDiagnostics(await api.solver.validate())
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem))
    } finally {
      setBusy(false)
    }
  }

  const start = async () => {
    setError(null)
    setBusy(true)
    try {
      const run = await api.solver.create({
        time_limit_seconds: timeLimit,
        base_version_id: baseVersionId,
        reoptimize: baseVersionId !== null && reoptimize,
      })
      setCurrent(run)
      setDiagnostics(run.diagnostics ?? null)
      runs.reload()
      versions.reload()
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem))
    } finally {
      setBusy(false)
    }
  }

  const errors = (diagnostics ?? []).filter((item) => item.severity === 'ERROR')
  const warnings = (diagnostics ?? []).filter((item) => item.severity === 'WARNING')

  return (
    <>
      <h1>Solver</h1>
      <p className="lead">
        Optimalizace běží jako úloha na pozadí. Po vypršení limitu se uloží nejlepší nalezené
        proveditelné řešení.
      </p>
      {error ? <Message kind="error">{error}</Message> : null}

      <div className="workspace" style={{ gridTemplateColumns: '320px minmax(0, 1fr)' }}>
        <div>
          <div className="panel">
            <h2>Nový běh</h2>
            <div className="field">
              <label>Časový limit</label>
              <select
                value={timeLimit}
                onChange={(event) => setTimeLimit(Number(event.target.value))}
              >
                {PRESETS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Výchozí verze (reoptimalizace)</label>
              <select
                value={baseVersionId ?? ''}
                onChange={(event) =>
                  setBaseVersionId(event.target.value ? Number(event.target.value) : null)
                }
              >
                <option value="">— rozvrh od nuly —</option>
                {(versions.data ?? []).map((version) => (
                  <option key={version.id} value={version.id}>
                    {version.name} ({version.item_count} hodin)
                  </option>
                ))}
              </select>
            </div>
            {baseVersionId !== null ? (
              <label style={{ display: 'flex', gap: 6, alignItems: 'center', color: 'inherit' }}>
                <input
                  type="checkbox"
                  style={{ width: 'auto' }}
                  checked={reoptimize}
                  onChange={(event) => setReoptimize(event.target.checked)}
                />
                Minimalizovat změny proti výchozímu rozvrhu
              </label>
            ) : null}
            <div className="chips" style={{ marginTop: 12 }}>
              <button className="primary" onClick={start} disabled={busy}>
                {baseVersionId === null ? 'Spustit solver' : 'Optimize remaining schedule'}
              </button>
              <button onClick={validate} disabled={busy}>
                Jen zkontrolovat data
              </button>
            </div>
            <p className="muted" style={{ marginTop: 8 }}>
              Uzamčené hodiny se při reoptimalizaci nepřesouvají.
            </p>
          </div>

          {current ? (
            <div className="panel">
              <h2>Běh #{current.id}</h2>
              <div className="chips">
                <Badge tone={statusTone(current.status)}>{current.status}</Badge>
                {current.best_score !== null ? (
                  <Badge>skóre {current.best_score}</Badge>
                ) : null}
              </div>
              {current.log ? <p className="mono muted">{current.log}</p> : null}
              {current.schedule_version_id ? (
                <button
                  className="primary"
                  onClick={() => {
                    window.localStorage.setItem(
                      'timetable.version',
                      String(current.schedule_version_id),
                    )
                    navigate('/')
                  }}
                >
                  Zobrazit výsledný rozvrh
                </button>
              ) : null}
            </div>
          ) : null}
        </div>

        <div>
          {diagnostics !== null ? (
            <div className="panel">
              <h2>Diagnostika dat</h2>
              {errors.length === 0 && warnings.length === 0 ? (
                <Message kind="ok">Žádné problémy nenalezeny, dataset je řešitelný.</Message>
              ) : null}
              {errors.length > 0 ? (
                <>
                  <h3>Chyby ({errors.length})</h3>
                  <ul>
                    {errors.map((item, index) => (
                      <li key={index}>
                        <span className="mono">{item.code}</span> {item.message}
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
              {warnings.length > 0 ? (
                <>
                  <h3>Varování ({warnings.length})</h3>
                  <ul>
                    {warnings.map((item, index) => (
                      <li key={index}>
                        <span className="mono">{item.code}</span> {item.message}
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </div>
          ) : null}

          {current?.penalties && Object.keys(current.penalties).length > 0 ? (
            <div className="panel">
              <h2>Rozpad penalizace</h2>
              <table>
                <thead>
                  <tr>
                    <th>Pravidlo</th>
                    <th style={{ textAlign: 'right' }}>Penalizace</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(current.penalties)
                    .sort((a, b) => b[1] - a[1])
                    .map(([key, value]) => (
                      <tr key={key}>
                        <td>{PENALTY_LABELS[key] ?? key}</td>
                        <td style={{ textAlign: 'right' }}>{value}</td>
                      </tr>
                    ))}
                  <tr>
                    <th>Celkem</th>
                    <th style={{ textAlign: 'right' }}>{current.best_score}</th>
                  </tr>
                </tbody>
              </table>
            </div>
          ) : null}

          <div className="panel">
            <h2>Historie běhů</h2>
            {runs.loading ? (
              <Loading what="běhy" />
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Stav</th>
                    <th>Limit</th>
                    <th>Skóre</th>
                    <th>Verze</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {(runs.data ?? []).map((run) => (
                    <tr key={run.id}>
                      <td>{run.id}</td>
                      <td>
                        <Badge tone={statusTone(run.status)}>{run.status}</Badge>
                      </td>
                      <td>{run.time_limit_seconds} s</td>
                      <td>{run.best_score ?? '—'}</td>
                      <td>{run.schedule_version_id ?? '—'}</td>
                      <td style={{ textAlign: 'right' }}>
                        <span className="chips" style={{ justifyContent: 'flex-end' }}>
                          <button className="small" onClick={() => setCurrent(run)}>
                            Detail
                          </button>
                          {['QUEUED', 'RUNNING'].includes(run.status) ? (
                            <button
                              className="small danger"
                              onClick={async () => {
                                await api.solver.cancel(run.id)
                                runs.reload()
                              }}
                            >
                              Zrušit
                            </button>
                          ) : null}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
