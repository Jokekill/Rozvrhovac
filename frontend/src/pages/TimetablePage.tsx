import { useMemo, useState } from 'react'
import { api, ApiError } from '../api'
import { DetailPanel } from '../components/DetailPanel'
import { TimetableGrid, colorOf } from '../components/TimetableGrid'
import type { ColorMode } from '../components/TimetableGrid'
import { Badge, Loading, Message } from '../components/ui'
import { hhmm } from '../format'
import { useAsync, useStored } from '../hooks'
import type { Conflict, ScheduledActivity, ViewScope } from '../types'

const SCOPES: [ViewScope, string][] = [
  ['school', 'Celá škola'],
  ['class', 'Třída'],
  ['group', 'Skupina'],
  ['teacher', 'Učitel'],
  ['room', 'Učebna'],
  ['student', 'Student'],
]

export function TimetablePage() {
  const versions = useAsync(() => api.versions.list(), [])
  const days = useAsync(() => api.cycle.days(), [])
  const cycle = useAsync(() => api.cycle.get(), [])
  const teachers = useAsync(() => api.teachers.list(), [])
  const rooms = useAsync(() => api.rooms.list(), [])
  const groups = useAsync(() => api.groups.list(), [])
  const students = useAsync(() => api.students.list(), [])

  const [versionId, setVersionId] = useStored<number | null>('timetable.version', null)
  const [scope, setScope] = useStored<ViewScope>('timetable.scope', 'school')
  const [entityId, setEntityId] = useStored<number | null>('timetable.entity', null)
  const [colorMode, setColorMode] = useStored<ColorMode>('timetable.color', 'subject')
  const [selected, setSelected] = useState<ScheduledActivity | null>(null)
  const [conflicts, setConflicts] = useState<Conflict[] | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const effectiveVersion =
    versionId ?? (versions.data && versions.data.length > 0 ? versions.data[0].id : null)

  const detail = useAsync(
    async () => (effectiveVersion ? api.versions.get(effectiveVersion) : null),
    [effectiveVersion],
  )

  const entityOptions = useMemo(() => {
    if (scope === 'teacher') return (teachers.data ?? []).map((t) => ({ id: t.id, label: t.full_name }))
    if (scope === 'room') return (rooms.data ?? []).map((r) => ({ id: r.id, label: r.name }))
    if (scope === 'class')
      return (groups.data ?? [])
        .filter((g) => g.type === 'CLASS')
        .map((g) => ({ id: g.id, label: g.name }))
    if (scope === 'group')
      return (groups.data ?? [])
        .filter((g) => g.type !== 'CLASS')
        .map((g) => ({ id: g.id, label: `${g.name} (${g.member_count})` }))
    if (scope === 'student')
      return (students.data ?? []).map((s) => ({
        id: s.id,
        label: `${s.full_name}${s.class_group_name ? ` – ${s.class_group_name}` : ''}`,
      }))
    return []
  }, [scope, teachers.data, rooms.data, groups.data, students.data])

  const items = useMemo(() => {
    const all = detail.data?.items ?? []
    if (scope === 'school' || entityId === null) return all
    if (scope === 'student') return all.filter((i) => i.student_ids.includes(entityId))
    if (scope === 'teacher') return all.filter((i) => i.teacher_ids.includes(entityId))
    if (scope === 'room') return all.filter((i) => i.room_id === entityId)
    return all.filter((i) => i.group_ids.includes(entityId))
  }, [detail.data, scope, entityId])

  const legend = useMemo(() => {
    const seen = new Map<string, string>()
    for (const item of items) {
      const key =
        colorMode === 'subject'
          ? item.subject_name ?? item.activity_name
          : colorMode === 'teacher'
            ? item.teacher_names.join(', ') || 'bez učitele'
            : item.kind
      if (!seen.has(key)) seen.set(key, colorOf(item, colorMode))
    }
    return [...seen.entries()].sort((a, b) => a[0].localeCompare(b[0], 'cs'))
  }, [items, colorMode])

  const move = async (item: ScheduledActivity, startMinute: number) => {
    setNotice(null)
    setConflicts(null)
    try {
      await api.scheduled.patch(item.id, { start_minute: startMinute })
      setNotice(`Přesunuto na ${hhmm(startMinute)}.`)
      detail.reload()
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 409) {
        const payload = problem.detail as { conflicts?: Conflict[] } | null
        setConflicts(payload?.conflicts ?? [])
        setSelected(item)
      } else {
        setNotice(problem instanceof Error ? problem.message : String(problem))
      }
    }
  }

  const forceMove = async (item: ScheduledActivity, startMinute: number) => {
    await api.scheduled.patch(item.id, { start_minute: startMinute }, true)
    setConflicts(null)
    detail.reload()
  }

  if (versions.loading || days.loading) return <Loading what="rozvrh" />

  if ((versions.data ?? []).length === 0) {
    return (
      <>
        <h1>Rozvrh</h1>
        <p className="lead">
          Zatím neexistuje žádná verze rozvrhu. Spusťte solver na stránce <b>Solver</b>.
        </p>
      </>
    )
  }

  return (
    <>
      <div className="split">
        <div>
          <h1>Rozvrh</h1>
          <p className="lead">
            Táhnutím přesunete hodinu. Konflikty se kontrolují okamžitě proti studentům,
            učitelům i učebnám.
          </p>
        </div>
        {effectiveVersion ? (
          <div className="chips">
            {(['csv', 'xlsx', 'pdf', 'ics'] as const).map((format) => (
              <a
                key={format}
                className="badge"
                href={api.exportUrl(effectiveVersion, format, scope, entityId ?? undefined)}
              >
                Export {format.toUpperCase()}
              </a>
            ))}
          </div>
        ) : null}
      </div>

      {notice ? <Message kind="ok">{notice}</Message> : null}
      {detail.error ? <Message kind="error">{detail.error}</Message> : null}

      {conflicts ? (
        <div className="message error">
          <b>CONFLICT</b>
          <ul style={{ margin: '6px 0 0 18px' }}>
            {conflicts.map((conflict, index) => (
              <li key={index}>
                <span className="mono">{conflict.code}</span> {conflict.message}
              </li>
            ))}
          </ul>
          <div className="chips" style={{ marginTop: 8 }}>
            <button className="small" onClick={() => setConflicts(null)}>
              Zrušit přesun
            </button>
          </div>
        </div>
      ) : null}

      <div className="workspace">
        <div>
          <div className="panel">
            <h2>Filtry</h2>
            <div className="field">
              <label>Verze rozvrhu</label>
              <select
                value={effectiveVersion ?? ''}
                onChange={(event) => {
                  setVersionId(Number(event.target.value))
                  setSelected(null)
                }}
              >
                {(versions.data ?? []).map((version) => (
                  <option key={version.id} value={version.id}>
                    {version.name} · {version.status} · {version.item_count} hodin
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Pohled</label>
              <select
                value={scope}
                onChange={(event) => {
                  setScope(event.target.value as ViewScope)
                  setEntityId(null)
                }}
              >
                {SCOPES.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            {scope !== 'school' ? (
              <div className="field">
                <label>Vyberte</label>
                <select
                  value={entityId ?? ''}
                  onChange={(event) =>
                    setEntityId(event.target.value ? Number(event.target.value) : null)
                  }
                >
                  <option value="">— vše —</option>
                  {entityOptions.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            <div className="field">
              <label>Barvy podle</label>
              <select
                value={colorMode}
                onChange={(event) => setColorMode(event.target.value as ColorMode)}
              >
                <option value="subject">Předmětu</option>
                <option value="teacher">Učitele</option>
                <option value="kind">Typu aktivity</option>
              </select>
            </div>
            <p className="muted">
              Zobrazeno {items.length} z {detail.data?.items.length ?? 0} hodin.
            </p>
          </div>

          <div className="panel">
            <h2>Legenda</h2>
            <div className="legend">
              {legend.map(([label, color]) => (
                <span key={label}>
                  <span className="swatch" style={{ background: color }} />
                  {label}
                </span>
              ))}
            </div>
            <p className="muted" style={{ marginTop: 8 }}>
              Barva je jen doplněk, každá hodina nese i textový popis.
            </p>
          </div>
        </div>

        <div>
          {detail.loading ? (
            <Loading what="hodiny" />
          ) : (
            <TimetableGrid
              days={days.data ?? []}
              items={items}
              granularity={cycle.data?.granularity_minutes ?? 5}
              selectedId={selected?.id ?? null}
              onSelect={(item) => {
                setSelected(item)
                setConflicts(null)
              }}
              onMove={move}
              colorMode={colorMode}
              lunch={
                cycle.data
                  ? { start: cycle.data.lunch_start_minute, end: cycle.data.lunch_end_minute }
                  : null
              }
            />
          )}
          {selected && conflicts ? (
            <div className="panel" style={{ marginTop: 12 }}>
              <h2>Vynutit přesun</h2>
              <p className="muted">
                Přesun poruší hard constraint. Rozvrhář jej může přesto provést, například
                při ručním dolaďování.
              </p>
              <button
                className="danger"
                onClick={() => {
                  const target = conflicts[0]?.conflicting_item_id
                  const item = detail.data?.items.find((i) => i.id === target)
                  if (selected && item) forceMove(selected, item.start_minute)
                }}
                disabled={!conflicts[0]?.conflicting_item_id}
              >
                Přesunout i tak
              </button>
            </div>
          ) : null}
        </div>

        <DetailPanel
          item={selected}
          onChanged={() => {
            detail.reload()
            setSelected(null)
          }}
        />
      </div>

      {detail.data?.penalties ? (
        <div className="panel" style={{ marginTop: 12 }}>
          <h2>Skóre verze</h2>
          <div className="chips">
            <Badge>Celkem {detail.data.total_penalty ?? 0}</Badge>
            {Object.entries(detail.data.penalties).map(([key, value]) => (
              <Badge key={key}>
                {key}: {value}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}
    </>
  )
}
