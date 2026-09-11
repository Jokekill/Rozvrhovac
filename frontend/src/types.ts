export type GroupType = 'CLASS' | 'SUBGROUP' | 'CROSS_CLASS' | 'ENSEMBLE' | 'OTHER'
export type ActivityKind =
  | 'STANDARD'
  | 'SPLIT'
  | 'CROSS_CLASS'
  | 'ENSEMBLE'
  | 'INDIVIDUAL'
  | 'OTHER'
export type OwnerType = 'TEACHER' | 'STUDENT' | 'ROOM'
export type AvailabilityKind = 'UNAVAILABLE' | 'PREFERRED'
export type Severity = 'ERROR' | 'WARNING' | 'INFO'
export type SolverStatus =
  | 'QUEUED'
  | 'RUNNING'
  | 'FEASIBLE'
  | 'OPTIMAL'
  | 'INFEASIBLE'
  | 'FAILED'
  | 'CANCELLED'

export interface Student {
  id: number
  first_name: string
  last_name: string
  full_name: string
  external_id: string | null
  active: boolean
  class_group_id: number | null
  class_group_name: string | null
  notes: string | null
}

export interface Teacher {
  id: number
  first_name: string
  last_name: string
  full_name: string
  external_id: string | null
  active: boolean
  max_minutes_per_day: number | null
  max_consecutive_minutes: number | null
  notes: string | null
}

export interface Room {
  id: number
  name: string
  code: string | null
  building: string | null
  floor: string | null
  capacity: number
  active: boolean
  feature_ids: number[]
  feature_names: string[]
}

export interface RoomFeature {
  id: number
  name: string
  description: string | null
}

export interface Subject {
  id: number
  name: string
  code: string | null
  color: string | null
}

export interface StudentGroup {
  id: number
  name: string
  code: string | null
  type: GroupType
  student_ids: number[]
  member_count: number
}

export interface ActivityTimeWindow {
  id?: number
  kind: 'ALLOWED' | 'FORBIDDEN' | 'PREFERRED'
  day_ordinal: number | null
  start_minute: number | null
  end_minute: number | null
}

export interface Activity {
  id: number
  name: string
  subject_id: number | null
  subject_name: string | null
  kind: ActivityKind
  duration_minutes: number
  occurrences_per_cycle: number
  priority: number
  active: boolean
  notes: string | null
  fixed_start_minute: number | null
  fixed_room_id: number | null
  align_to_periods: boolean
  start_step_minutes: number | null
  min_capacity: number | null
  teacher_ids: number[]
  teacher_names: string[]
  student_ids: number[]
  group_ids: number[]
  required_feature_ids: number[]
  allowed_room_ids: number[]
  preferred_room_ids: number[]
  forbidden_room_ids: number[]
  time_windows: ActivityTimeWindow[]
  participant_count: number
}

export interface IndividualLesson {
  id: number
  student_id: number
  student_name: string
  class_name: string | null
  subject_id: number | null
  subject_name: string | null
  teacher_id: number | null
  teacher_name: string | null
  duration_minutes: number
  occurrences_per_cycle: number
  allowed_day_ordinals: number[]
  required_feature_ids: number[]
  name: string | null
  active: boolean
}

export interface Day {
  id: number
  ordinal: number
  week_index: number
  weekday: number
  name: string
  start_minute: number
  end_minute: number
  active: boolean
}

export interface Period {
  id: number
  index: number
  name: string
  start_minute: number
  end_minute: number
}

export interface CycleConfig {
  id: number
  name: string
  weeks_in_cycle: number
  granularity_minutes: number
  lunch_start_minute: number
  lunch_end_minute: number
  lunch_break_minutes: number
  early_threshold_minute: number
  late_threshold_minute: number
  max_student_minutes_per_day: number
  individual_preferred_start: number
  individual_preferred_end: number
}

export interface AvailabilityWindow {
  id: number
  owner_type: OwnerType
  owner_id: number
  kind: AvailabilityKind
  day_ordinal: number | null
  start_minute: number
  end_minute: number
  note: string | null
}

export interface ScheduledActivity {
  id: number
  version_id: number
  activity_id: number
  occurrence_index: number
  start_minute: number
  duration_minutes: number
  day_ordinal: number
  room_id: number | null
  lock_time: boolean
  lock_room: boolean
  activity_name: string
  subject_name: string | null
  subject_color: string | null
  room_name: string | null
  building: string | null
  teacher_ids: number[]
  teacher_names: string[]
  student_ids: number[]
  group_ids: number[]
  group_names: string[]
  student_count: number
  kind: ActivityKind
}

export interface ScheduleVersion {
  id: number
  schedule_id: number
  name: string
  status: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'
  created_at: string | null
  parent_version_id: number | null
  solver_run_id: number | null
  total_penalty: number | null
  penalties: Record<string, number> | null
  note: string | null
  item_count: number
}

export interface ScheduleVersionDetail extends ScheduleVersion {
  items: ScheduledActivity[]
}

export interface Schedule {
  id: number
  name: string
  description: string | null
  created_at: string | null
  version_count: number
}

export interface Conflict {
  code: string
  severity: Severity
  message: string
  entity_type: string | null
  entity_id: number | null
  conflicting_item_id: number | null
}

export interface RoomSuggestion {
  room_id: number
  room_name: string
  free: boolean
  reason: string | null
}

export interface MoveCheck {
  ok: boolean
  conflicts: Conflict[]
  room_suggestions: RoomSuggestion[]
}

export interface DiagnosticItem {
  code: string
  severity: Severity
  message: string
  entity_type: string | null
  entity_id: number | null
  details: Record<string, unknown> | null
}

export interface SolverRun {
  id: number
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  status: SolverStatus
  time_limit_seconds: number
  best_score: number | null
  schedule_version_id: number | null
  schedule_id: number | null
  base_version_id: number | null
  params: Record<string, unknown> | null
  penalties: Record<string, number> | null
  diagnostics: DiagnosticItem[] | null
  log: string | null
}

export interface ConstraintWeight {
  id: number
  code: string
  name: string
  type: string
  weight: number
  enabled: boolean
  description: string | null
}

export interface ImportResult {
  entity: string
  rows_detected: number
  new: number
  updated: number
  unchanged: number
  committed: boolean
  errors: { row: number; message: string; data: Record<string, unknown> }[]
  preview: Record<string, unknown>[]
}

export interface VersionCompare {
  left_version_id: number
  right_version_id: number
  changed: number
  unchanged: number
  items: {
    activity_id: number
    activity_name: string
    occurrence_index: number
    change: string
    left_start: number | null
    right_start: number | null
    left_room: string | null
    right_room: string | null
  }[]
}

export interface DatasetInfo {
  enabled: boolean
  database_empty: boolean
  students: number
  max_gymnasium_classes: number
  max_lyceum_classes: number
  gymnasium_class_names: string[]
  lyceum_class_names: string[]
}

export interface DatasetRequest {
  preset: 'demo' | 'school'
  reset: boolean
  seed: number
  gymnasium_classes: number
  lyceum_classes: number
  gymnasium_class_min: number
  gymnasium_class_max: number
  lyceum_class_size: number
  solo_share: number
  rooms_ordinary: number
  solve: boolean
  time_limit_seconds: number
}

export interface DatasetResult {
  preset: string
  reset: boolean
  stats: Record<string, number>
  removed: Record<string, number>
  solver_run_id: number | null
  message: string
}

export type LinkKind = 'SAME_START' | 'NOT_SIMULTANEOUS' | 'BEFORE'

export interface ActivityLink {
  id: number
  kind: LinkKind
  activity_a_id: number
  activity_b_id: number
  note: string | null
  activity_a_name: string | null
  activity_b_name: string | null
}

export type ViewScope = 'school' | 'student' | 'class' | 'group' | 'teacher' | 'room'
