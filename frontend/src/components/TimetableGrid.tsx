import { useMemo, useRef, useState } from 'react'
import type { Day, ScheduledActivity } from '../types'
import { absoluteMinute, colorFor, hhmm, minuteOfDay } from '../format'

export type ColorMode = 'subject' | 'teacher' | 'kind'

const KIND_COLORS: Record<string, string> = {
  STANDARD: '#3b6ea5',
  SPLIT: '#5c3ba5',
  CROSS_CLASS: '#a52e6b',
  ENSEMBLE: '#2ea55c',
  INDIVIDUAL: '#b0562e',
  OTHER: '#6b7280',
}

export function colorOf(item: ScheduledActivity, mode: ColorMode): string {
  if (mode === 'kind') return KIND_COLORS[item.kind] ?? KIND_COLORS.OTHER
  if (mode === 'teacher') return colorFor(item.teacher_names.join('|') || 'bez učitele')
  return item.subject_color ?? colorFor(item.subject_name ?? item.activity_name)
}

interface DropTarget {
  dayOrdinal: number
  startMinute: number
  durationMinutes: number
}

interface Props {
  days: Day[]
  items: ScheduledActivity[]
  granularity: number
  selectedId: number | null
  onSelect: (item: ScheduledActivity) => void
  onMove?: (item: ScheduledActivity, startMinute: number) => void
  colorMode?: ColorMode
  lunch?: { start: number; end: number } | null
  pixelsPerMinute?: number
  readOnly?: boolean
}

/**
 * Week grid drawn from absolute cycle minutes, not from lesson numbers, so a
 * 30 minute individual lesson and a 90 minute drama block coexist naturally.
 */
export function TimetableGrid({
  days,
  items,
  granularity,
  selectedId,
  onSelect,
  onMove,
  colorMode = 'subject',
  lunch = null,
  pixelsPerMinute = 1.1,
  readOnly = false,
}: Props) {
  const [dropTarget, setDropTarget] = useState<DropTarget | null>(null)
  const dragOffset = useRef(0)
  const draggedId = useRef<number | null>(null)

  const visibleDays = days.filter((day) => day.active)
  const bounds = useMemo(() => {
    if (visibleDays.length === 0) return { start: 8 * 60, end: 17 * 60 }
    let start = Math.min(...visibleDays.map((day) => day.start_minute))
    let end = Math.max(...visibleDays.map((day) => day.end_minute))
    for (const item of items) {
      start = Math.min(start, minuteOfDay(item.start_minute))
      end = Math.max(end, minuteOfDay(item.start_minute) + item.duration_minutes)
    }
    // A little air at both ends so the first hour label is not clipped.
    return { start: start - 10, end: end + 10 }
  }, [visibleDays, items])

  const height = (bounds.end - bounds.start) * pixelsPerMinute
  const top = (minute: number) => (minute - bounds.start) * pixelsPerMinute

  const hourMarks: number[] = []
  for (let minute = Math.ceil(bounds.start / 60) * 60; minute <= bounds.end; minute += 60) {
    hourMarks.push(minute)
  }

  const minuteFromEvent = (event: React.DragEvent<HTMLDivElement>): number => {
    const rect = event.currentTarget.getBoundingClientRect()
    const raw = bounds.start + (event.clientY - rect.top) / pixelsPerMinute - dragOffset.current
    const snapped = Math.round(raw / granularity) * granularity
    return Math.max(bounds.start, Math.min(snapped, bounds.end))
  }

  const byDay = useMemo(() => {
    const map = new Map<number, ScheduledActivity[]>()
    for (const item of items) {
      const list = map.get(item.day_ordinal) ?? []
      list.push(item)
      map.set(item.day_ordinal, list)
    }
    return map
  }, [items])

  /** Lessons that overlap in time share the column width. */
  const laneOf = (dayItems: ScheduledActivity[]) => {
    const sorted = [...dayItems].sort((a, b) => a.start_minute - b.start_minute)
    const lanes: number[] = []
    const assignment = new Map<number, { lane: number; lanes: number }>()
    const clusters: ScheduledActivity[][] = []
    let current: ScheduledActivity[] = []
    let clusterEnd = -1
    for (const item of sorted) {
      if (current.length > 0 && item.start_minute >= clusterEnd) {
        clusters.push(current)
        current = []
        lanes.length = 0
      }
      current.push(item)
      clusterEnd = Math.max(clusterEnd, item.start_minute + item.duration_minutes)
    }
    if (current.length > 0) clusters.push(current)

    for (const cluster of clusters) {
      const ends: number[] = []
      for (const item of cluster) {
        let lane = ends.findIndex((end) => end <= item.start_minute)
        if (lane === -1) {
          lane = ends.length
          ends.push(0)
        }
        ends[lane] = item.start_minute + item.duration_minutes
        assignment.set(item.id, { lane, lanes: 0 })
      }
      for (const item of cluster) {
        const entry = assignment.get(item.id)
        if (entry) entry.lanes = ends.length
      }
    }
    return assignment
  }

  return (
    <div className="grid-wrap">
      <div
        className="grid"
        style={{ gridTemplateColumns: `56px repeat(${visibleDays.length}, minmax(140px, 1fr))` }}
      >
        <div className="grid-head" />
        {visibleDays.map((day) => (
          <div className="grid-head" key={day.ordinal}>
            {day.name}
            <span className="muted" style={{ fontWeight: 400 }}>
              {' '}
              {hhmm(day.start_minute)}–{hhmm(day.end_minute)}
            </span>
          </div>
        ))}

        <div className="grid-time" style={{ height }}>
          {hourMarks.map((minute) => (
            <span key={minute} style={{ top: top(minute) }}>
              {hhmm(minute)}
            </span>
          ))}
        </div>

        {visibleDays.map((day) => {
          const dayItems = byDay.get(day.ordinal) ?? []
          const lanes = laneOf(dayItems)
          return (
            <div
              key={day.ordinal}
              className="grid-day"
              style={{ height }}
              onDragOver={(event) => {
                if (readOnly || !onMove) return
                event.preventDefault()
                const startMinute = minuteFromEvent(event)
                const dragged = items.find((candidate) => candidate.id === draggedId.current)
                setDropTarget({
                  dayOrdinal: day.ordinal,
                  startMinute,
                  durationMinutes: dragged?.duration_minutes ?? 45,
                })
              }}
              onDragLeave={() => setDropTarget(null)}
              onDrop={(event) => {
                if (readOnly || !onMove) return
                event.preventDefault()
                const id = Number(event.dataTransfer.getData('text/plain'))
                const item = items.find((candidate) => candidate.id === id)
                setDropTarget(null)
                if (!item) return
                onMove(item, absoluteMinute(day.ordinal, minuteFromEvent(event)))
              }}
            >
              {hourMarks.map((minute) => (
                <div key={minute} className="grid-line hour" style={{ top: top(minute) }} />
              ))}
              {lunch ? (
                <div
                  className="grid-lunch"
                  style={{ top: top(lunch.start), height: (lunch.end - lunch.start) * pixelsPerMinute }}
                />
              ) : null}

              {dayItems.map((item) => {
                const lane = lanes.get(item.id) ?? { lane: 0, lanes: 1 }
                const width = 100 / Math.max(1, lane.lanes)
                const background = colorOf(item, colorMode)
                return (
                  <div
                    key={item.id}
                    className={`lesson${selectedId === item.id ? ' selected' : ''}`}
                    style={{
                      top: top(minuteOfDay(item.start_minute)),
                      height: Math.max(18, item.duration_minutes * pixelsPerMinute - 2),
                      background,
                      left: `calc(${lane.lane * width}% + 2px)`,
                      width: `calc(${width}% - 4px)`,
                    }}
                    draggable={!readOnly && Boolean(onMove) && !item.lock_time}
                    onDragStart={(event) => {
                      draggedId.current = item.id
                      event.dataTransfer.setData('text/plain', String(item.id))
                      const rect = event.currentTarget.getBoundingClientRect()
                      dragOffset.current = (event.clientY - rect.top) / pixelsPerMinute
                    }}
                    onDragEnd={() => {
                      draggedId.current = null
                      setDropTarget(null)
                    }}
                    onClick={() => onSelect(item)}
                    title={`${item.activity_name} • ${hhmm(item.start_minute)}–${hhmm(
                      item.start_minute + item.duration_minutes,
                    )} • ${item.room_name ?? 'bez učebny'}`}
                  >
                    <span className="flags">
                      {item.lock_time ? '🔒' : ''}
                      {item.lock_room && !item.lock_time ? '⌂' : ''}
                    </span>
                    <span className="title">{item.activity_name}</span>
                    <span className="meta">
                      {hhmm(item.start_minute)}–{hhmm(item.start_minute + item.duration_minutes)}
                      {item.room_name ? ` · ${item.room_name}` : ''}
                    </span>
                    {item.duration_minutes >= 45 ? (
                      <span className="meta">
                        {item.teacher_names.join(', ') || 'bez učitele'} · {item.student_count} st.
                      </span>
                    ) : null}
                  </div>
                )
              })}

              {dropTarget && dropTarget.dayOrdinal === day.ordinal ? (
                <div
                  className="drop-hint"
                  style={{
                    top: top(dropTarget.startMinute),
                    height: dropTarget.durationMinutes * pixelsPerMinute,
                  }}
                />
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}
