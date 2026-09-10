import { useRef, useState } from 'react'
import { api } from '../api'
import { Badge, Message } from '../components/ui'
import { useAsync } from '../hooks'
import type { ImportResult } from '../types'

const LABELS: Record<string, string> = {
  students: 'Studenti',
  teachers: 'Učitelé',
  rooms: 'Učebny',
  groups: 'Skupiny',
  'group-members': 'Členství ve skupinách',
  activities: 'Aktivity',
  'individual-lessons': 'Individuální výuka',
  availability: 'Dostupnost',
}

const COLUMNS: Record<string, string> = {
  students: 'external_id, first_name, last_name, class_code, active, notes',
  teachers:
    'external_id, first_name, last_name, max_minutes_per_day, max_consecutive_minutes, active',
  rooms: 'code, name, building, floor, capacity, features, active',
  groups: 'code, name, type',
  'group-members': 'group_code, student_external_id',
  activities:
    'name, subject_code, kind, duration_minutes, occurrences_per_cycle, teacher_external_ids, ' +
    'group_codes, student_external_ids, required_features, align_to_periods',
  'individual-lessons':
    'student_external_id, subject_code, teacher_external_id, duration_minutes, ' +
    'occurrences_per_cycle, allowed_days, required_features',
  availability: 'owner_type, owner_external_id, kind, day, start, end, note',
}

export function ImportPage() {
  const entities = useAsync(() => api.imports.entities(), [])
  const [entity, setEntity] = useState('students')
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const run = async (action: 'preview' | 'commit') => {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      setResult(await api.imports.run(entity, action, file))
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem))
    } finally {
      setBusy(false)
    }
  }

  const previewColumns =
    result && result.preview.length > 0 ? Object.keys(result.preview[0]) : []

  return (
    <>
      <h1>Import dat</h1>
      <p className="lead">
        Nahrajte CSV nebo XLSX. Náhled nic nezapisuje; potvrzení je vše-nebo-nic, takže
        chybný řádek zastaví celý soubor.
      </p>
      {error ? <Message kind="error">{error}</Message> : null}

      <div className="panel">
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>Co importujeme</label>
            <select
              value={entity}
              onChange={(event) => {
                setEntity(event.target.value)
                setResult(null)
              }}
            >
              {(entities.data ?? Object.keys(LABELS)).map((name) => (
                <option key={name} value={name}>
                  {LABELS[name] ?? name}
                </option>
              ))}
            </select>
          </div>
          <div style={{ flex: 2 }}>
            <label>Soubor</label>
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xlsx,.xlsm,text/csv"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null)
                setResult(null)
              }}
            />
          </div>
          <button onClick={() => run('preview')} disabled={!file || busy}>
            Náhled
          </button>
          <button
            className="primary"
            onClick={() => run('commit')}
            disabled={!file || busy || !result || result.errors.length > 0}
          >
            Importovat
          </button>
        </div>
        <p className="muted mono">Očekávané sloupce: {COLUMNS[entity]}</p>
      </div>

      {result ? (
        <div className="panel">
          <h2>Výsledek</h2>
          <div className="chips">
            <Badge>Rows detected: {result.rows_detected}</Badge>
            <Badge tone="ok">New: {result.new}</Badge>
            <Badge tone="warn">Updated: {result.updated}</Badge>
            <Badge tone={result.errors.length > 0 ? 'error' : 'default'}>
              Errors: {result.errors.length}
            </Badge>
            {result.committed ? <Badge tone="ok">zapsáno do databáze</Badge> : null}
          </div>

          {result.errors.length > 0 ? (
            <>
              <h3>Chyby podle řádků</h3>
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 80 }}>Řádek</th>
                    <th>Problém</th>
                  </tr>
                </thead>
                <tbody>
                  {result.errors.map((item, index) => (
                    <tr key={index}>
                      <td>{item.row}</td>
                      <td>{item.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : null}

          {previewColumns.length > 0 ? (
            <>
              <h3>Náhled ({result.preview.length} řádků)</h3>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      {previewColumns.map((column) => (
                        <th key={column}>{column}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.preview.map((row, index) => (
                      <tr key={index}>
                        {previewColumns.map((column) => (
                          <td key={column}>
                            {row[column] === null || row[column] === undefined
                              ? '—'
                              : String(row[column])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </div>
      ) : null}
    </>
  )
}
