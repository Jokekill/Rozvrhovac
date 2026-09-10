export const MINUTES_PER_DAY = 1440

export function hhmm(minute: number): string {
  const value = ((minute % MINUTES_PER_DAY) + MINUTES_PER_DAY) % MINUTES_PER_DAY
  const hours = Math.floor(value / 60)
  const minutes = value % 60
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
}

export function parseHhmm(text: string): number | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(text.trim())
  if (!match) return null
  const hours = Number(match[1])
  const minutes = Number(match[2])
  if (hours > 23 || minutes > 59) return null
  return hours * 60 + minutes
}

export function minuteOfDay(absolute: number): number {
  return ((absolute % MINUTES_PER_DAY) + MINUTES_PER_DAY) % MINUTES_PER_DAY
}

export function dayOrdinalOf(absolute: number): number {
  return Math.floor(absolute / MINUTES_PER_DAY)
}

export function absoluteMinute(dayOrdinal: number, minute: number): number {
  return dayOrdinal * MINUTES_PER_DAY + minute
}

export function duration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`
}

/** Deterministic fallback colour when a subject has none configured. */
export function colorFor(key: string): string {
  let hash = 0
  for (let index = 0; index < key.length; index += 1) {
    hash = (hash * 31 + key.charCodeAt(index)) % 360
  }
  return `hsl(${hash}, 45%, 42%)`
}

export const PENALTY_LABELS: Record<string, string> = {
  teacher_gaps: 'Okna učitelů',
  student_gaps: 'Okna studentů',
  teacher_time_preferences: 'Preferované časy učitelů',
  student_time_preferences: 'Preferované časy studentů',
  room_preferences: 'Preferované učebny',
  teacher_room_changes: 'Změny učeben učitele',
  subject_spread: 'Rozložení předmětu',
  same_day_repeats: 'Opakování ve stejný den',
  student_daily_load: 'Denní zátěž studentů',
  teacher_daily_load: 'Denní zátěž učitelů',
  lunch_break: 'Přestávka na oběd',
  individual_lesson_blocks: 'Bloky individuální výuky',
  early_late_lessons: 'Brzké a pozdní hodiny',
  building_transitions: 'Přesuny mezi budovami',
  schedule_changes: 'Změny proti výchozímu rozvrhu',
}
