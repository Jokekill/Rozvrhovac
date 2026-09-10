import type {
  Activity,
  AvailabilityWindow,
  ConstraintWeight,
  CycleConfig,
  Day,
  DiagnosticItem,
  ImportResult,
  IndividualLesson,
  MoveCheck,
  Period,
  Room,
  RoomFeature,
  Schedule,
  ScheduleVersion,
  ScheduleVersionDetail,
  ScheduledActivity,
  SolverRun,
  Student,
  StudentGroup,
  Subject,
  Teacher,
  VersionCompare,
  ViewScope,
} from './types'

const BASE = import.meta.env.VITE_API_BASE ?? '/api'

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown, message: string) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    let detail: unknown = null
    let message = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      detail = body.detail ?? body
      if (typeof detail === 'string') message = detail
      else if (detail && typeof detail === 'object' && 'message' in detail)
        message = String((detail as { message: unknown }).message)
    } catch {
      /* keep the status line */
    }
    throw new ApiError(response.status, detail, message)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

const get = <T,>(path: string) => request<T>(path)
const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
const put = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: 'PUT', body: JSON.stringify(body) })
const patch = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
const del = (path: string) => request<void>(path, { method: 'DELETE' })

function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const api = {
  students: {
    list: (params: { class_group_id?: number; search?: string } = {}) =>
      get<Student[]>(`/students${query(params)}`),
    create: (body: Partial<Student>) => post<Student>('/students', body),
    update: (id: number, body: Partial<Student>) => put<Student>(`/students/${id}`, body),
    remove: (id: number) => del(`/students/${id}`),
  },
  teachers: {
    list: () => get<Teacher[]>('/teachers'),
    create: (body: Partial<Teacher>) => post<Teacher>('/teachers', body),
    update: (id: number, body: Partial<Teacher>) => put<Teacher>(`/teachers/${id}`, body),
    remove: (id: number) => del(`/teachers/${id}`),
  },
  rooms: {
    list: () => get<Room[]>('/rooms'),
    create: (body: Partial<Room> & { feature_ids?: number[] }) => post<Room>('/rooms', body),
    update: (id: number, body: Partial<Room> & { feature_ids?: number[] }) =>
      put<Room>(`/rooms/${id}`, body),
    remove: (id: number) => del(`/rooms/${id}`),
  },
  roomFeatures: {
    list: () => get<RoomFeature[]>('/room-features'),
    create: (body: { name: string; description?: string }) =>
      post<RoomFeature>('/room-features', body),
    remove: (id: number) => del(`/room-features/${id}`),
  },
  subjects: {
    list: () => get<Subject[]>('/subjects'),
    create: (body: Partial<Subject>) => post<Subject>('/subjects', body),
    update: (id: number, body: Partial<Subject>) => put<Subject>(`/subjects/${id}`, body),
    remove: (id: number) => del(`/subjects/${id}`),
  },
  groups: {
    list: () => get<StudentGroup[]>('/groups'),
    create: (body: Partial<StudentGroup>) => post<StudentGroup>('/groups', body),
    update: (id: number, body: Partial<StudentGroup>) =>
      put<StudentGroup>(`/groups/${id}`, body),
    remove: (id: number) => del(`/groups/${id}`),
  },
  activities: {
    list: () => get<Activity[]>('/activities'),
    get: (id: number) => get<Activity>(`/activities/${id}`),
    create: (body: Record<string, unknown>) => post<Activity>('/activities', body),
    update: (id: number, body: Record<string, unknown>) =>
      put<Activity>(`/activities/${id}`, body),
    remove: (id: number) => del(`/activities/${id}`),
  },
  individualLessons: {
    list: () => get<IndividualLesson[]>('/individual-lessons'),
    bulk: (rows: Record<string, unknown>[], deleteIds: number[] = []) =>
      post<IndividualLesson[]>('/individual-lessons/bulk', {
        rows,
        delete_ids: deleteIds,
      }),
  },
  availability: {
    list: (params: { owner_type?: string; owner_id?: number } = {}) =>
      get<AvailabilityWindow[]>(`/availability${query(params)}`),
    create: (body: Partial<AvailabilityWindow>) =>
      post<AvailabilityWindow>('/availability', body),
    remove: (id: number) => del(`/availability/${id}`),
  },
  cycle: {
    get: () => get<CycleConfig>('/cycle'),
    update: (body: Partial<CycleConfig>) => put<CycleConfig>('/cycle', body),
    days: () => get<Day[]>('/cycle/days'),
    replaceDays: (body: Partial<Day>[]) => put<Day[]>('/cycle/days', body),
    periods: () => get<Period[]>('/cycle/periods'),
  },
  schedules: {
    list: () => get<Schedule[]>('/schedules'),
    create: (body: { name: string; description?: string }) => post<Schedule>('/schedules', body),
    versions: (scheduleId: number) =>
      get<ScheduleVersion[]>(`/schedules/${scheduleId}/versions`),
  },
  versions: {
    list: () => get<ScheduleVersion[]>('/versions'),
    get: (id: number) => get<ScheduleVersionDetail>(`/versions/${id}`),
    duplicate: (id: number, name?: string) =>
      post<ScheduleVersion>(`/versions/${id}/duplicate`, { name }),
    publish: (id: number) => post<ScheduleVersion>(`/versions/${id}/publish`),
    remove: (id: number) => del(`/versions/${id}`),
    compare: (id: number, other: number) =>
      get<VersionCompare>(`/versions/${id}/compare?other=${other}`),
    view: (id: number, scope: ViewScope, entityId?: number) =>
      get<{ title: string; items: ScheduledActivity[] }>(
        `/versions/${id}/view${query({ scope, entity_id: entityId })}`,
      ),
  },
  scheduled: {
    patch: (id: number, body: Record<string, unknown>, force = false) =>
      patch<ScheduledActivity>(`/scheduled-activities/${id}${force ? '?force=true' : ''}`, body),
    validateMove: (id: number, body: { start_minute: number; room_id: number | null }) =>
      post<MoveCheck>(`/scheduled-activities/${id}/validate-move`, body),
    roomOptions: (id: number, startMinute?: number) =>
      get<MoveCheck>(
        `/scheduled-activities/${id}/room-options${query({ start_minute: startMinute })}`,
      ),
    lock: (id: number, body: { lock_time: boolean; lock_room: boolean }) =>
      post<ScheduledActivity>(`/scheduled-activities/${id}/lock`, body),
    unlock: (id: number) => post<ScheduledActivity>(`/scheduled-activities/${id}/unlock`),
  },
  solver: {
    runs: () => get<SolverRun[]>('/solver/runs'),
    run: (id: number) => get<SolverRun>(`/solver/runs/${id}`),
    create: (body: {
      time_limit_seconds: number
      schedule_id?: number | null
      base_version_id?: number | null
      reoptimize?: boolean
      version_name?: string | null
    }) => post<SolverRun>('/solver/runs', body),
    cancel: (id: number) => post<SolverRun>(`/solver/runs/${id}/cancel`),
    validate: () => post<DiagnosticItem[]>('/solver/validate'),
  },
  constraints: {
    list: () => get<ConstraintWeight[]>('/constraint-weights'),
    update: (code: string, body: { weight?: number; enabled?: boolean }) =>
      put<ConstraintWeight>(`/constraint-weights/${code}`, body),
  },
  imports: {
    entities: () => get<string[]>('/imports'),
    run: (entity: string, action: 'preview' | 'commit', file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<ImportResult>(`/imports/${entity}/${action}`, {
        method: 'POST',
        body: form,
      })
    },
  },
  exportUrl: (
    versionId: number,
    format: 'csv' | 'xlsx' | 'pdf' | 'ics',
    scope: ViewScope = 'school',
    entityId?: number,
  ) => `${BASE}/exports/schedule/${versionId}${query({ format, scope, entity_id: entityId })}`,
}
