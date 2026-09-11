import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAsync } from '../hooks'
import type { DatasetRequest, DatasetResult } from '../types'
import { Badge, Message } from './ui'

const DEFAULTS: DatasetRequest = {
  preset: 'school',
  reset: false,
  seed: 7,
  gymnasium_classes: 8,
  lyceum_classes: 4,
  gymnasium_class_min: 25,
  gymnasium_class_max: 30,
  lyceum_class_size: 25,
  solo_share: 0.27,
  rooms_ordinary: 10,
  solve: true,
  time_limit_seconds: 60,
}

const STAT_LABELS: Record<string, string> = {
  students: 'studentů',
  teachers: 'učitelů',
  rooms: 'učeben',
  groups: 'skupin',
  activities: 'aktivit',
  occurrences: 'hodin k naplánování',
  solo_lessons: 'sólových lekcí',
  ensembles: 'souborů',
}

/**
 * One-click test data (§28). Generating replaces the whole database, so the
 * wipe is opt-in, confirmed, and reported back row by row.
 */
export function DatasetGenerator() {
  const info = useAsync(() => api.datasets.info(), [])
  const navigate = useNavigate()
  const [form, setForm] = useState<DatasetRequest>(DEFAULTS)
  const [result, setResult] = useState<DatasetResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [armed, setArmed] = useState(false)

  const set = <K extends keyof DatasetRequest>(key: K, value: DatasetRequest[K]) =>
    setForm((current) => ({ ...current, [key]: value }))

  const notEmpty = info.data ? !info.data.database_empty : false
  const needsReset = notEmpty && !form.reset

  const run = async () => {
    setBusy(true)
    setError(null)
    setResult(null)
    setArmed(false)
    try {
      const outcome = await api.datasets.generate(form)
      setResult(outcome)
      info.reload()
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem))
    } finally {
      setBusy(false)
    }
  }

  if (info.data && !info.data.enabled) {
    return (
      <div className="panel">
        <h2>Testovací data</h2>
        <p className="muted">
          Generování testovacích dat je na tomto prostředí vypnuté nastavením
          <span className="mono"> ALLOW_DATASET_GENERATION=false</span>.
        </p>
      </div>
    )
  }

  const school = form.preset === 'school'
  const estimate = school
    ? form.gymnasium_classes *
        Math.round((form.gymnasium_class_min + form.gymnasium_class_max) / 2) +
      form.lyceum_classes * form.lyceum_class_size
    : 60

  return (
    <div className="panel">
      <div className="split">
        <h2>Testovací data</h2>
        {info.data ? (
          <Badge tone={info.data.database_empty ? 'ok' : 'warn'}>
            {info.data.database_empty
              ? 'databáze je prázdná'
              : `v databázi je ${info.data.students} studentů`}
          </Badge>
        ) : null}
      </div>
      <p className="muted">
        Vygeneruje kompletní školu přímo do databáze: třídy, učitele, učebny,
        skupiny napříč ročníky, sólové lekce i dostupnosti. Nic se neimportuje ze
        souboru.
      </p>

      {error ? <Message kind="error">{error}</Message> : null}

      <div className="row">
        <div style={{ flex: 1 }}>
          <label>Velikost školy</label>
          <select
            value={form.preset}
            onChange={(event) => set('preset', event.target.value as 'demo' | 'school')}
          >
            <option value="school">Gymnázium a lyceum (plná škola)</option>
            <option value="demo">Malá ukázka (3 třídy, 60 studentů)</option>
          </select>
        </div>
        <div style={{ width: 110 }}>
          <label>Seed</label>
          <input
            type="number"
            value={form.seed}
            onChange={(event) => set('seed', Number(event.target.value))}
          />
        </div>
      </div>

      {school ? (
        <>
          <div className="row">
            <div style={{ width: 150 }}>
              <label>Tříd gymnázia</label>
              <input
                type="number"
                min={0}
                max={info.data?.max_gymnasium_classes ?? 8}
                value={form.gymnasium_classes}
                onChange={(event) => set('gymnasium_classes', Number(event.target.value))}
              />
            </div>
            <div style={{ width: 150 }}>
              <label>Studentů ve třídě od</label>
              <input
                type="number"
                min={1}
                value={form.gymnasium_class_min}
                onChange={(event) => set('gymnasium_class_min', Number(event.target.value))}
              />
            </div>
            <div style={{ width: 150 }}>
              <label>… do</label>
              <input
                type="number"
                min={1}
                value={form.gymnasium_class_max}
                onChange={(event) => set('gymnasium_class_max', Number(event.target.value))}
              />
            </div>
          </div>
          <div className="row">
            <div style={{ width: 150 }}>
              <label>Tříd lycea</label>
              <input
                type="number"
                min={0}
                max={info.data?.max_lyceum_classes ?? 4}
                value={form.lyceum_classes}
                onChange={(event) => set('lyceum_classes', Number(event.target.value))}
              />
            </div>
            <div style={{ width: 150 }}>
              <label>Studentů ve třídě lycea</label>
              <input
                type="number"
                min={1}
                value={form.lyceum_class_size}
                onChange={(event) => set('lyceum_class_size', Number(event.target.value))}
              />
            </div>
            <div style={{ width: 170 }}>
              <label>Běžných učeben</label>
              <input
                type="number"
                min={1}
                value={form.rooms_ordinary}
                onChange={(event) => set('rooms_ordinary', Number(event.target.value))}
              />
            </div>
            <div style={{ width: 200 }}>
              <label>Podíl studentů se sólovou výukou</label>
              <input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={form.solo_share}
                onChange={(event) => set('solo_share', Number(event.target.value))}
              />
            </div>
          </div>
          <p className="muted">
            Odhadem {estimate} studentů. Ke každé třídě se přidá půlená informatika,
            k celé škole sbor, orchestr, dva dramatické soubory a jazzový band.
            Specializované učebny se přidávají nad rámec běžných.
          </p>
        </>
      ) : null}

      <div className="row" style={{ alignItems: 'center' }}>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', color: 'inherit' }}>
          <input
            type="checkbox"
            style={{ width: 'auto' }}
            checked={form.solve}
            onChange={(event) => set('solve', event.target.checked)}
          />
          Po vygenerování rovnou spustit solver
        </label>
        {form.solve ? (
          <div style={{ width: 150 }}>
            <label>Limit solveru (s)</label>
            <input
              type="number"
              min={1}
              value={form.time_limit_seconds}
              onChange={(event) => set('time_limit_seconds', Number(event.target.value))}
            />
          </div>
        ) : null}
      </div>

      {notEmpty ? (
        <label
          style={{ display: 'flex', gap: 6, alignItems: 'center', color: 'var(--danger)' }}
        >
          <input
            type="checkbox"
            style={{ width: 'auto' }}
            checked={form.reset}
            onChange={(event) => {
              set('reset', event.target.checked)
              setArmed(false)
            }}
          />
          Smazat všechna současná data včetně rozvrhů a verzí
        </label>
      ) : null}

      <div className="chips" style={{ marginTop: 12 }}>
        {armed ? (
          <>
            <button className="danger" onClick={run} disabled={busy}>
              Opravdu smazat a vygenerovat znovu
            </button>
            <button onClick={() => setArmed(false)} disabled={busy}>
              Zrušit
            </button>
          </>
        ) : (
          <button
            className="primary"
            disabled={busy || needsReset}
            onClick={() => (form.reset ? setArmed(true) : run())}
          >
            {busy ? 'Generuji…' : 'Vygenerovat testovací data'}
          </button>
        )}
        {needsReset ? (
          <span className="muted">
            Databáze není prázdná. Zaškrtněte smazání současných dat.
          </span>
        ) : null}
      </div>

      {result ? (
        <>
          <Message kind="ok">{result.message}</Message>
          <div className="chips">
            {Object.entries(result.stats).map(([key, value]) => (
              <Badge key={key}>
                {value} {STAT_LABELS[key] ?? key}
              </Badge>
            ))}
          </div>
          {Object.keys(result.removed).length > 0 ? (
            <p className="muted">
              Smazáno {Object.values(result.removed).reduce((a, b) => a + b, 0)} řádků ve{' '}
              {Object.keys(result.removed).length} tabulkách.
            </p>
          ) : null}
          <div className="chips" style={{ marginTop: 8 }}>
            {result.solver_run_id ? (
              <button onClick={() => navigate('/solver')}>Sledovat běh solveru</button>
            ) : null}
            <button onClick={() => navigate('/')}>Otevřít rozvrh</button>
          </div>
        </>
      ) : null}
    </div>
  )
}
