"""CP-SAT timetable model.

Design notes
------------
* One :class:`Occurrence` per (activity, occurrence index) with ``start``,
  constant ``duration``, ``end`` and an ``IntervalVar``.
* Students, teachers and rooms are resources: ``AddNoOverlap`` over their
  intervals. Rooms use optional intervals selected by
  ``activity_X_occurrence_Y_in_room_Z`` booleans with ``AddExactlyOne``.
* There is deliberately **no** ``student x minute x activity`` boolean.
* Availability is folded into the domain of ``start`` by the loader, so the
  hard availability constraints cost no variables at all.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from app.models.enums import LinkKind
from app.solver.model import (
    ActivityData,
    Assignment,
    SolveResult,
    SolverInput,
)

MINUTES_PER_DAY = 1440
PENALTY_UNIT = 5  # gaps and overloads are counted in 5 minute units


# Objective groups, reported separately for explainability (§13).
PENALTY_GROUPS = {
    "SC01": "teacher_gaps",
    "SC02": "student_gaps",
    "SC03": "teacher_time_preferences",
    "SC04": "student_time_preferences",
    "SC05": "room_preferences",
    "SC06": "teacher_room_changes",
    "SC07": "subject_spread",
    "SC08": "same_day_repeats",
    "SC09": "student_daily_load",
    "SC10": "teacher_daily_load",
    "SC11": "lunch_break",
    "SC12": "individual_lesson_blocks",
    "SC13": "early_late_lessons",
    "SC14": "building_transitions",
    "SC15": "schedule_changes",
    "SC16": "student_min_lessons",
    "SC17": "core_block",
    "SC18": "zeroth_hour",
}


@dataclass
class Occurrence:
    activity: ActivityData
    index: int
    start: cp_model.IntVar
    end: cp_model.IntVar
    interval: cp_model.IntervalVar
    room_bools: dict[int, cp_model.IntVar] = field(default_factory=dict)

    @property
    def key(self) -> tuple[int, int]:
        return (self.activity.id, self.index)

    @property
    def duration(self) -> int:
        return self.activity.duration


class InfeasibleModelError(Exception):
    """Raised while building when the model is provably empty."""

    def __init__(self, diagnostics: list[dict]):
        super().__init__("Model is infeasible before solving")
        self.diagnostics = diagnostics


class TimetableModel:
    def __init__(self, data: SolverInput):
        self.data = data
        self.model = cp_model.CpModel()
        self.occurrences: list[Occurrence] = []
        self.by_activity: dict[int, list[Occurrence]] = {}
        self._penalty_terms: dict[str, list[tuple[int, cp_model.IntVar]]] = {}
        self._in_day_cache: dict[tuple[int, int, int], cp_model.IntVar] = {}
        self._domain_cache: dict[tuple[int, int, tuple], cp_model.IntVar] = {}
        self._student_groups: list[tuple[object, list[Occurrence], int]] | None = None
        self.build_diagnostics: list[dict] = []
        self._has_hints = False

    # -- helpers ---------------------------------------------------------
    def _add_penalty(self, code: str, var, coefficient: int = 1) -> None:
        weight = self.data.weight(code)
        if weight <= 0:
            return
        self._penalty_terms.setdefault(code, []).append((coefficient, var))

    def _enabled(self, code: str) -> bool:
        return self.data.weight(code) > 0

    def _reify_start_in(self, occurrence: Occurrence, values: set[int], tag: str):
        """Bool that is true exactly when ``start`` takes one of ``values``.

        Table constraints do not accept enforcement literals, linear ones do,
        so membership is expressed with ``AddLinearExpressionInDomain``.
        """
        key = (occurrence.activity.id, occurrence.index, tuple(sorted(values)))
        cached = self._domain_cache.get(key)
        if cached is not None:
            return cached
        candidates = set(occurrence.activity.candidate_starts)
        inside = values & candidates
        literal = self.model.NewBoolVar(
            f"a{occurrence.activity.id}_o{occurrence.index}_{tag}"
        )
        if not inside:
            self.model.Add(literal == 0)
        elif inside == candidates:
            self.model.Add(literal == 1)
        else:
            domain = cp_model.Domain.FromValues(sorted(inside))
            self.model.AddLinearExpressionInDomain(
                occurrence.start, domain
            ).OnlyEnforceIf(literal)
            self.model.AddLinearExpressionInDomain(
                occurrence.start, domain.complement()
            ).OnlyEnforceIf(literal.Not())
        self._domain_cache[key] = literal
        return literal

    def _in_day(self, occurrence: Occurrence, day_ordinal: int):
        key = (occurrence.activity.id, occurrence.index, day_ordinal)
        cached = self._in_day_cache.get(key)
        if cached is not None:
            return cached
        values = {
            s
            for s in occurrence.activity.candidate_starts
            if s // MINUTES_PER_DAY == day_ordinal
        }
        literal = self._reify_start_in(occurrence, values, f"day{day_ordinal}")
        self._in_day_cache[key] = literal
        return literal

    # -- variables -------------------------------------------------------
    def _create_variables(self) -> None:
        problems: list[dict] = []
        for activity in self.data.activities:
            if activity.occurrences <= 0:
                continue
            if not activity.candidate_starts:
                problems.append(
                    {
                        "code": "NO_FEASIBLE_START",
                        "severity": "ERROR",
                        "entity_type": "Activity",
                        "entity_id": activity.id,
                        "message": (
                            f"Aktivita '{activity.name}' nemá žádný přípustný začátek "
                            f"(dostupnost učitelů/studentů, povolená okna nebo délka "
                            f"{activity.duration} min se nevejde do vyučovacího dne)."
                        ),
                    }
                )
                continue
            if not activity.compatible_room_ids:
                problems.append(
                    {
                        "code": "NO_COMPATIBLE_ROOM",
                        "severity": "ERROR",
                        "entity_type": "Activity",
                        "entity_id": activity.id,
                        "message": (
                            f"Aktivita '{activity.name}' nemá žádnou vyhovující učebnu "
                            f"(vlastnosti, kapacita nebo allowed/forbidden seznam)."
                        ),
                    }
                )
                continue

            occurrences: list[Occurrence] = []
            for index in range(activity.occurrences):
                domain_values = sorted(activity.candidate_starts)
                key = (activity.id, index)
                if index == 0 and activity.fixed_start_minute is not None:
                    domain_values = [activity.fixed_start_minute]  # HC09
                if key in self.data.locked_time:  # HC15
                    base = self.data.base_assignments.get(key)
                    if base is not None:
                        domain_values = [base.start_minute]
                start = self.model.NewIntVarFromDomain(
                    cp_model.Domain.FromValues(domain_values),
                    f"start_a{activity.id}_o{index}",
                )
                end = self.model.NewIntVar(
                    min(domain_values) + activity.duration,
                    max(domain_values) + activity.duration,
                    f"end_a{activity.id}_o{index}",
                )
                interval = self.model.NewIntervalVar(
                    start, activity.duration, end, f"iv_a{activity.id}_o{index}"
                )
                occurrence = Occurrence(activity, index, start, end, interval)
                occurrences.append(occurrence)
                self.occurrences.append(occurrence)
            self.by_activity[activity.id] = occurrences

        if problems:
            raise InfeasibleModelError(problems)

    def _create_room_variables(self) -> None:
        """Optional intervals per room + ExactlyOne per occurrence."""
        room_intervals: dict[int, list] = {room_id: [] for room_id in self.data.rooms}

        for occurrence in self.occurrences:
            activity = occurrence.activity
            candidates = list(activity.compatible_room_ids)
            key = occurrence.key
            if key in self.data.locked_room:
                base = self.data.base_assignments.get(key)
                if base is not None and base.room_id in candidates:
                    candidates = [base.room_id]
            if occurrence.index == 0 and activity.fixed_room_id:
                candidates = [
                    r for r in candidates if r == activity.fixed_room_id
                ] or [activity.fixed_room_id]

            for room_id in candidates:
                literal = self.model.NewBoolVar(
                    f"activity_{activity.id}_{occurrence.index}_in_room_{room_id}"
                )
                occurrence.room_bools[room_id] = literal
                room_intervals.setdefault(room_id, []).append(
                    self.model.NewOptionalIntervalVar(
                        occurrence.start,
                        activity.duration,
                        occurrence.end,
                        literal,
                        f"iv_a{activity.id}_o{occurrence.index}_r{room_id}",
                    )
                )
            self.model.AddExactlyOne(occurrence.room_bools.values())  # HC03 selection

        # HC06 – room unavailability becomes a fixed blocking interval.
        for room_id, room in self.data.rooms.items():
            for block_start, block_end in room.blocked:
                room_intervals.setdefault(room_id, []).append(
                    self.model.NewIntervalVar(
                        block_start,
                        block_end - block_start,
                        block_end,
                        f"blocked_r{room_id}_{block_start}",
                    )
                )
        for room_id, intervals in room_intervals.items():
            if len(intervals) > 1:
                self.model.AddNoOverlap(intervals)  # HC03

    # -- hard constraints ------------------------------------------------
    def _resource_no_overlap(self) -> None:
        by_teacher: dict[int, list] = {}
        by_student: dict[int, list] = {}
        for occurrence in self.occurrences:
            for teacher_id in occurrence.activity.teacher_ids:
                by_teacher.setdefault(teacher_id, []).append(occurrence.interval)
            for student_id in occurrence.activity.student_ids:
                by_student.setdefault(student_id, []).append(occurrence.interval)
        for intervals in by_teacher.values():  # HC02
            if len(intervals) > 1:
                self.model.AddNoOverlap(intervals)
        for intervals in by_student.values():  # HC01
            if len(intervals) > 1:
                self.model.AddNoOverlap(intervals)
        self._teacher_intervals = by_teacher
        self._student_intervals = by_student

    def _symmetry_breaking(self) -> None:
        """Occurrences of one activity are interchangeable, so order them.

        Skipped whenever an occurrence is pinned (fixed lesson, lock or a base
        schedule we try to stay close to), where the order carries meaning.
        """
        for activity_id, occurrences in self.by_activity.items():
            if len(occurrences) < 2:
                continue
            activity = occurrences[0].activity
            pinned = (
                activity.fixed_start_minute is not None
                or any(o.key in self.data.locked_time for o in occurrences)
                or any(o.key in self.data.base_assignments for o in occurrences)
            )
            if pinned:
                continue
            for previous, current in zip(occurrences, occurrences[1:], strict=False):
                self.model.Add(current.start >= previous.start + activity.duration)

    def _links(self) -> None:
        for link in self.data.links:
            left = self.by_activity.get(link.activity_a_id, [])
            right = self.by_activity.get(link.activity_b_id, [])
            if not left or not right:
                continue
            pairs = list(zip(left, right, strict=False))
            if link.kind == LinkKind.SAME_START:  # HC12
                for a, b in pairs:
                    self.model.Add(a.start == b.start)
            elif link.kind == LinkKind.NOT_SIMULTANEOUS:  # HC13
                for a in left:
                    for b in right:
                        self.model.AddNoOverlap([a.interval, b.interval])
            elif link.kind == LinkKind.BEFORE:  # HC14
                for a, b in pairs:
                    self.model.Add(a.end <= b.start)

    # -- soft constraints ------------------------------------------------
    def _student_signature_groups(self):
        """(student, occurrences, multiplier) for students with identical days.

        Students that attend exactly the same set of occurrences produce
        identical per-day expressions, so they collapse into one group whose
        penalty is multiplied by the group size. In a real school most of a
        class shares the same signature, which keeps the model small. Cached,
        because SC02/SC09, SC16 and SC17 all want the same grouping.
        """
        if self._student_groups is not None:
            return self._student_groups
        by_signature: dict[tuple, list[int]] = {}
        for student_id in self.data.students:
            signature = tuple(
                sorted(
                    o.key
                    for o in self.occurrences
                    if student_id in o.activity.student_ids
                )
            )
            if signature:
                by_signature.setdefault(signature, []).append(student_id)
        index = {o.key: o for o in self.occurrences}
        self._student_groups = [
            (
                self.data.students[student_ids[0]],
                [index[key] for key in signature],
                len(student_ids),
            )
            for signature, student_ids in by_signature.items()
        ]
        return self._student_groups

    def _resource_day_groups(self):
        """(role, person, occurrences, multiplier) tuples for day based rules.

        Student groups come from :meth:`_student_signature_groups`.
        """
        groups: list[tuple[str, object, list[Occurrence], int]] = []
        if self._enabled("SC01") or self._enabled("SC10"):
            for teacher_id, person in self.data.teachers.items():
                occurrences = [
                    o for o in self.occurrences if teacher_id in o.activity.teacher_ids
                ]
                if occurrences:
                    groups.append(("teacher", person, occurrences, 1))
        if self._enabled("SC02") or self._enabled("SC09"):
            for person, occurrences, multiplier in self._student_signature_groups():
                groups.append(("student", person, occurrences, multiplier))
        return groups

    def _day_span_penalties(self) -> None:
        """SC01/SC02 gaps and SC09/SC10 daily load, per person and day.

        ``first_start`` and ``last_end`` are min/max over *linear expressions*
        rather than over freshly created variables: an absent occurrence is
        pushed a whole day length out of the way instead of needing two extra
        integer variables and four enforced equalities.
        """
        for role, person, occurrences, multiplier in self._resource_day_groups():
            gap_code = "SC01" if role == "teacher" else "SC02"
            load_code = "SC10" if role == "teacher" else "SC09"
            if role == "teacher":
                minute_limit = person.max_minutes_per_day
                span_limit = person.max_consecutive_minutes
            else:
                minute_limit = self.data.config.max_student_minutes_per_day
                span_limit = None

            for day in self.data.days:
                relevant = [
                    o
                    for o in occurrences
                    if any(
                        s // MINUTES_PER_DAY == day.ordinal
                        for s in o.activity.candidate_starts
                    )
                ]
                if not relevant:
                    continue
                presence = [(o, self._in_day(o, day.ordinal)) for o in relevant]
                busy = sum(o.duration * literal for o, literal in presence)
                day_length = day.end_minute - day.start_minute
                span_units = math.ceil(day_length / PENALTY_UNIT)

                need_span = self._enabled(gap_code) or (
                    span_limit is not None and self._enabled(load_code)
                )
                if need_span and len(relevant) > 1:
                    # An occurrence scheduled on another day must not drag the
                    # span of this day, so it is clamped to the day boundary.
                    effective_starts = []
                    effective_ends = []
                    for occurrence, literal in presence:
                        tag = f"{role}{person.id}_d{day.ordinal}_a{occurrence.activity.id}_{occurrence.index}"
                        s_eff = self.model.NewIntVar(day.abs_start, day.abs_end, f"s_eff_{tag}")
                        e_eff = self.model.NewIntVar(day.abs_start, day.abs_end, f"e_eff_{tag}")
                        self.model.Add(s_eff == occurrence.start).OnlyEnforceIf(literal)
                        self.model.Add(s_eff == day.abs_end).OnlyEnforceIf(literal.Not())
                        self.model.Add(e_eff == occurrence.end).OnlyEnforceIf(literal)
                        self.model.Add(e_eff == day.abs_start).OnlyEnforceIf(literal.Not())
                        effective_starts.append(s_eff)
                        effective_ends.append(e_eff)
                    first_start = self.model.NewIntVar(
                        day.abs_start, day.abs_end, f"first_{role}{person.id}_d{day.ordinal}"
                    )
                    last_end = self.model.NewIntVar(
                        day.abs_start, day.abs_end, f"last_{role}{person.id}_d{day.ordinal}"
                    )
                    self.model.AddMinEquality(first_start, effective_starts)
                    self.model.AddMaxEquality(last_end, effective_ends)

                    if self._enabled(gap_code):
                        gap_units = self.model.NewIntVar(
                            0, span_units, f"gap_{role}{person.id}_d{day.ordinal}"
                        )
                        self.model.Add(
                            PENALTY_UNIT * gap_units >= last_end - first_start - busy
                        )
                        self._add_penalty(gap_code, gap_units, multiplier)

                    if span_limit is not None and self._enabled(load_code):
                        over_span = self.model.NewIntVar(
                            0, span_units, f"span_over_{role}{person.id}_d{day.ordinal}"
                        )
                        self.model.Add(
                            PENALTY_UNIT * over_span >= last_end - first_start - span_limit
                        )
                        self._add_penalty(load_code, over_span, multiplier)

                if minute_limit is not None and self._enabled(load_code):
                    total = sum(o.duration for o in relevant)
                    if total > minute_limit:
                        over = self.model.NewIntVar(
                            0,
                            math.ceil(total / PENALTY_UNIT),
                            f"load_{role}{person.id}_d{day.ordinal}",
                        )
                        self.model.Add(PENALTY_UNIT * over >= busy - minute_limit)
                        self._add_penalty(load_code, over, multiplier)

    def _preferred_time_penalties(self) -> None:
        """SC03 / SC04 – occurrence outside a PREFERRED window."""
        for code, people, attribute in (
            ("SC03", self.data.teachers, "teacher_ids"),
            ("SC04", self.data.students, "student_ids"),
        ):
            if not self._enabled(code):
                continue
            for person_id, person in people.items():
                if not person.preferred:
                    continue
                for occurrence in self.occurrences:
                    if person_id not in getattr(occurrence.activity, attribute):
                        continue
                    duration = occurrence.duration
                    good = {
                        s
                        for s in occurrence.activity.candidate_starts
                        if any(
                            s >= window_start and s + duration <= window_end
                            for window_start, window_end in person.preferred
                        )
                    }
                    literal = self._reify_start_in(occurrence, good, f"pref{person_id}")
                    outside = self.model.NewBoolVar(f"outside_{person_id}_{id(occurrence)}")
                    self.model.Add(outside == 1 - literal)
                    self._add_penalty(code, outside)

    def _room_preference_penalties(self) -> None:
        if not self._enabled("SC05"):
            return
        for occurrence in self.occurrences:
            preferred = occurrence.activity.preferred_room_ids
            if not preferred:
                continue
            for room_id, literal in occurrence.room_bools.items():
                if room_id not in preferred:
                    self._add_penalty("SC05", literal)

    def _room_and_building_changes(self) -> None:
        """SC06 (rooms) and SC14 (buildings), per teacher and day.

        One marker per distinct room / building, so the penalty really is
        "number of different rooms used that day minus one".
        """
        want_rooms = self._enabled("SC06")
        want_buildings = self._enabled("SC14")
        if not (want_rooms or want_buildings):
            return
        for teacher_id in self.data.teachers:
            occurrences = [
                o for o in self.occurrences if teacher_id in o.activity.teacher_ids
            ]
            if len(occurrences) < 2:
                continue
            for day in self.data.days:
                used_rooms: dict[int, cp_model.IntVar] = {}
                used_buildings: dict[str, cp_model.IntVar] = {}
                for occurrence in occurrences:
                    in_day = self._in_day(occurrence, day.ordinal)
                    for room_id, room_literal in occurrence.room_bools.items():
                        if want_rooms:
                            marker = used_rooms.get(room_id)
                            if marker is None:
                                marker = self.model.NewBoolVar(
                                    f"used_t{teacher_id}_d{day.ordinal}_r{room_id}"
                                )
                                used_rooms[room_id] = marker
                            self.model.Add(marker >= room_literal + in_day - 1)
                        if want_buildings:
                            building = self.data.rooms[room_id].building or "?"
                            marker = used_buildings.get(building)
                            if marker is None:
                                marker = self.model.NewBoolVar(
                                    f"used_t{teacher_id}_d{day.ordinal}_b{building}"
                                )
                                used_buildings[building] = marker
                            self.model.Add(marker >= room_literal + in_day - 1)
                if want_rooms and len(used_rooms) > 1:
                    changes = self.model.NewIntVar(
                        0, len(used_rooms), f"room_changes_t{teacher_id}_d{day.ordinal}"
                    )
                    self.model.Add(changes >= sum(used_rooms.values()) - 1)
                    self._add_penalty("SC06", changes)
                if want_buildings and len(used_buildings) > 1:
                    transitions = self.model.NewIntVar(
                        0,
                        len(used_buildings),
                        f"building_changes_t{teacher_id}_d{day.ordinal}",
                    )
                    self.model.Add(transitions >= sum(used_buildings.values()) - 1)
                    self._add_penalty("SC14", transitions)

    def _distribution_penalties(self) -> None:
        """SC07 spread over the week and SC08 not twice on the same day."""
        want_spread = self._enabled("SC07")
        want_same_day = self._enabled("SC08")
        if not (want_spread or want_same_day):
            return
        for activity_id, occurrences in self.by_activity.items():
            if len(occurrences) < 2:
                continue
            day_used: dict[int, cp_model.IntVar] = {}
            for day in self.data.days:
                literals = [self._in_day(o, day.ordinal) for o in occurrences]
                if want_same_day:
                    excess = self.model.NewIntVar(
                        0, len(literals), f"same_day_a{activity_id}_d{day.ordinal}"
                    )
                    self.model.Add(excess >= sum(literals) - 1)
                    self._add_penalty("SC08", excess)
                if want_spread:
                    marker = self.model.NewBoolVar(f"day_used_a{activity_id}_d{day.ordinal}")
                    for literal in literals:
                        self.model.Add(marker >= literal)
                    day_used[day.ordinal] = marker
            if want_spread:
                ordinals = sorted(day_used)
                for left, right in zip(ordinals, ordinals[1:], strict=False):
                    if right != left + 1:
                        continue
                    adjacent = self.model.NewBoolVar(f"adjacent_a{activity_id}_{left}")
                    self.model.Add(adjacent >= day_used[left] + day_used[right] - 1)
                    self._add_penalty("SC07", adjacent)

    def _lunch_penalties(self) -> None:
        """SC11 – every student should keep one free block in the lunch window."""
        if not self._enabled("SC11"):
            return
        config = self.data.config
        break_length = max(5, config.lunch_break_minutes)
        for student_id in self.data.students:
            occurrences = [
                o for o in self.occurrences if student_id in o.activity.student_ids
            ]
            if not occurrences:
                continue
            for day in self.data.days:
                slots: list[tuple[int, int]] = []
                cursor = day.offset + config.lunch_start_minute
                limit = day.offset + config.lunch_end_minute
                while cursor + break_length <= limit:
                    slots.append((cursor, cursor + break_length))
                    cursor += break_length
                if not slots:
                    continue
                relevant = [
                    o
                    for o in occurrences
                    if any(
                        s < limit and s + o.duration > day.offset + config.lunch_start_minute
                        for s in o.activity.candidate_starts
                        if s // MINUTES_PER_DAY == day.ordinal
                    )
                ]
                if not relevant:
                    continue
                free_slots = []
                for slot_start, slot_end in slots:
                    free = self.model.NewBoolVar(f"lunch_free_s{student_id}_{slot_start}")
                    for occurrence in relevant:
                        overlapping = {
                            s
                            for s in occurrence.activity.candidate_starts
                            if s < slot_end and s + occurrence.duration > slot_start
                        }
                        busy = self._reify_start_in(
                            occurrence, overlapping, f"lunch{slot_start}"
                        )
                        self.model.Add(free + busy <= 1)
                    free_slots.append(free)
                has_break = self.model.NewBoolVar(f"lunch_ok_s{student_id}_d{day.ordinal}")
                self.model.Add(has_break <= sum(free_slots))
                missed = self.model.NewBoolVar(f"lunch_miss_s{student_id}_d{day.ordinal}")
                self.model.Add(missed == 1 - has_break)
                self._add_penalty("SC11", missed)

    def _individual_block_penalties(self) -> None:
        """SC12 – keep one-to-one tuition inside the preferred block."""
        if not self._enabled("SC12"):
            return
        config = self.data.config
        for occurrence in self.occurrences:
            if occurrence.activity.kind != "INDIVIDUAL":
                continue
            good = {
                s
                for s in occurrence.activity.candidate_starts
                if (s % MINUTES_PER_DAY) >= config.individual_preferred_start
                and (s % MINUTES_PER_DAY) + occurrence.duration
                <= config.individual_preferred_end
            }
            literal = self._reify_start_in(occurrence, good, "indiv_block")
            outside = self.model.NewBoolVar(f"indiv_out_{id(occurrence)}")
            self.model.Add(outside == 1 - literal)
            self._add_penalty("SC12", outside)

    def _early_late_penalties(self) -> None:
        """SC13 – avoid very early and very late lessons."""
        if not self._enabled("SC13"):
            return
        config = self.data.config
        for occurrence in self.occurrences:
            bad = {
                s
                for s in occurrence.activity.candidate_starts
                if (s % MINUTES_PER_DAY) < config.early_threshold_minute
                or (s % MINUTES_PER_DAY) + occurrence.duration > config.late_threshold_minute
            }
            if not bad:
                continue
            literal = self._reify_start_in(occurrence, bad, "early_late")
            self._add_penalty("SC13", literal)

    def _min_lessons_penalties(self) -> None:
        """SC16 - a day a student comes in for is worth at least N lessons.

        A day with no teaching at all is free: the rule forbids the pointless
        trip to school for a single lesson, not the day off. ``attends`` is
        pushed up by every lesson placed on the day, so the solver can only
        escape the shortfall by emptying the day completely.
        """
        if not self._enabled("SC16"):
            return
        minimum = self.data.config.min_student_lessons_per_day
        if minimum <= 1:
            return
        for person, occurrences, multiplier in self._student_signature_groups():
            for day in self.data.days:
                relevant = [
                    o
                    for o in occurrences
                    if any(
                        s // MINUTES_PER_DAY == day.ordinal
                        for s in o.activity.candidate_starts
                    )
                ]
                if not relevant:
                    continue
                presence = [self._in_day(o, day.ordinal) for o in relevant]
                attends = self.model.NewBoolVar(
                    f"attends_s{person.id}_d{day.ordinal}"
                )
                for literal in presence:
                    self.model.Add(attends >= literal)
                shortfall = self.model.NewIntVar(
                    0, minimum, f"short_s{person.id}_d{day.ordinal}"
                )
                self.model.Add(shortfall >= minimum * attends - sum(presence))
                self._add_penalty("SC16", shortfall, multiplier)

    def _core_signature_groups(self, core):
        """Like :meth:`_student_signature_groups`, but only core-capable lessons.

        Core coverage depends solely on the occurrences that can land in a core
        slot at all. Afternoon-only tuition is what makes a student's full
        signature unique, so ignoring it collapses a whole class back into one
        group and takes SC17 from thousands of variables down to dozens.
        """
        windows = [
            (day.offset + period.start_minute, day.offset + period.end_minute)
            for day in self.data.days
            for period in core
        ]

        def reaches_core(occurrence: Occurrence) -> bool:
            return any(
                start < window_end and start + occurrence.duration > window_start
                for start in occurrence.activity.candidate_starts
                for window_start, window_end in windows
            )

        core_capable = {o.key for o in self.occurrences if reaches_core(o)}
        merged: dict[tuple, tuple[object, int]] = {}
        for person, occurrences, multiplier in self._student_signature_groups():
            signature = tuple(sorted(o.key for o in occurrences if o.key in core_capable))
            representative, headcount = merged.get(signature, (person, 0))
            merged[signature] = (representative, headcount + multiplier)
        index = {o.key: o for o in self.occurrences}
        return [
            (representative, [index[key] for key in signature], headcount)
            for signature, (representative, headcount) in merged.items()
        ]

    def _core_block_penalties(self) -> None:
        """SC17 - everybody is in school for the first periods, every day.

        "Covers the period" is overlap, not an equal start, so a double lesson
        or an activity that ignores the period grid still counts.
        """
        if not self._enabled("SC17"):
            return
        core = self.data.core_periods()
        if not core:
            return
        for person, occurrences, multiplier in self._core_signature_groups(core):
            for day in self.data.days:
                for period in core:
                    slot_start = day.offset + period.start_minute
                    slot_end = day.offset + period.end_minute
                    if slot_start < day.abs_start or slot_end > day.abs_end:
                        continue
                    covering = []
                    for occurrence in occurrences:
                        values = {
                            s
                            for s in occurrence.activity.candidate_starts
                            if s < slot_end and s + occurrence.duration > slot_start
                        }
                        if not values:
                            continue
                        covering.append(
                            self._reify_start_in(
                                occurrence, values, f"core_p{period.index}"
                            )
                        )
                    missing = self.model.NewBoolVar(
                        f"core_miss_s{person.id}_d{day.ordinal}_p{period.index}"
                    )
                    if covering:
                        self.model.Add(sum(covering) + missing >= 1)
                    else:
                        self.model.Add(missing == 1)
                    self._add_penalty("SC17", missing, multiplier)

    def _zeroth_hour_penalties(self) -> None:
        """SC18 - the zeroth hour is legal, but stays the exception.

        Everything starting before ``core_day_start_minute`` counts, so the
        rule follows the configured boundary rather than a period index.
        """
        if not self._enabled("SC18"):
            return
        boundary = self.data.config.core_day_start_minute
        for occurrence in self.occurrences:
            early = {
                s
                for s in occurrence.activity.candidate_starts
                if (s % MINUTES_PER_DAY) < boundary
            }
            if not early:
                continue
            literal = self._reify_start_in(occurrence, early, "zeroth")
            self._add_penalty("SC18", literal)

    def _change_penalties(self) -> None:
        """SC15 – MINIMIZE_CHANGES_FROM_CURRENT_SCHEDULE."""
        if not self._enabled("SC15") or not self.data.base_assignments:
            return
        for occurrence in self.occurrences:
            base = self.data.base_assignments.get(occurrence.key)
            if base is None:
                continue
            same_start = self._reify_start_in(occurrence, {base.start_minute}, "same_start")
            moved = self.model.NewBoolVar(f"moved_{id(occurrence)}")
            self.model.Add(moved == 1 - same_start)
            self._add_penalty("SC15", moved)
            if base.room_id is not None and base.room_id in occurrence.room_bools:
                room_changed = self.model.NewBoolVar(f"room_moved_{id(occurrence)}")
                self.model.Add(room_changed == 1 - occurrence.room_bools[base.room_id])
                self._add_penalty("SC15", room_changed)

    def _hints(self) -> None:
        """Warm start from the base schedule or from the feasibility pass."""
        for occurrence in self.occurrences:
            base = self.data.base_assignments.get(
                occurrence.key
            ) or self.data.hints.get(occurrence.key)
            if base is None:
                continue
            if base.start_minute in occurrence.activity.candidate_starts:
                self.model.AddHint(occurrence.start, base.start_minute)
                self._has_hints = True
            literal = occurrence.room_bools.get(base.room_id or -1)
            if literal is not None:
                self.model.AddHint(literal, 1)

    # -- assembly --------------------------------------------------------
    def build(self) -> None:
        self._create_variables()
        self._create_room_variables()
        self._resource_no_overlap()
        self._symmetry_breaking()
        self._links()

        self._day_span_penalties()
        self._preferred_time_penalties()
        self._room_preference_penalties()
        self._room_and_building_changes()
        self._distribution_penalties()
        self._lunch_penalties()
        self._individual_block_penalties()
        self._early_late_penalties()
        self._min_lessons_penalties()
        self._core_block_penalties()
        self._zeroth_hour_penalties()
        self._change_penalties()
        self._hints()

        objective = []
        for code, terms in self._penalty_terms.items():
            weight = self.data.weight(code)
            for coefficient, var in terms:
                objective.append(weight * coefficient * var)
        if objective:
            self.model.Minimize(sum(objective))

    def freeze_to(self, assignments: dict[tuple[int, int], "Assignment"]) -> None:
        """Pin every occurrence to a known solution.

        Used to score a schedule that was produced by the feasibility pass, so
        that a short time limit still yields a stored result *with* its penalty
        breakdown rather than an empty run.
        """
        for occurrence in self.occurrences:
            assignment = assignments.get(occurrence.key)
            if assignment is None:
                continue
            self.model.Add(occurrence.start == assignment.start_minute)
            literal = occurrence.room_bools.get(assignment.room_id or -1)
            if literal is not None:
                self.model.Add(literal == 1)

    def apply_hints(self, hints: dict[tuple[int, int], "Assignment"]) -> None:
        """Attach a warm start after the model has already been built."""
        for occurrence in self.occurrences:
            hint = hints.get(occurrence.key)
            if hint is None:
                continue
            if hint.start_minute in occurrence.activity.candidate_starts:
                self.model.AddHint(occurrence.start, hint.start_minute)
                self._has_hints = True
            literal = occurrence.room_bools.get(hint.room_id or -1)
            if literal is not None:
                self.model.AddHint(literal, 1)

    def solve(
        self,
        *,
        time_limit_seconds: int = 60,
        workers: int = 8,
        should_stop=None,
    ) -> SolveResult:
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit_seconds)
        solver.parameters.num_search_workers = workers
        solver.parameters.log_search_progress = False

        callback = _StopCallback(should_stop) if should_stop else None
        status = solver.Solve(self.model, callback) if callback else solver.Solve(self.model)

        status_name = {
            cp_model.OPTIMAL: "OPTIMAL",
            cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.MODEL_INVALID: "FAILED",
            cp_model.UNKNOWN: "FAILED",
        }[status]

        result = SolveResult(status=status_name, wall_time=solver.WallTime())
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for occurrence in self.occurrences:
                room_id = None
                for candidate, literal in occurrence.room_bools.items():
                    if solver.Value(literal):
                        room_id = candidate
                        break
                result.assignments.append(
                    Assignment(
                        activity_id=occurrence.activity.id,
                        occurrence_index=occurrence.index,
                        start_minute=solver.Value(occurrence.start),
                        room_id=room_id,
                    )
                )
            penalties: dict[str, int] = {}
            total = 0
            for code, terms in self._penalty_terms.items():
                weight = self.data.weight(code)
                value = sum(
                    weight * coefficient * solver.Value(var) for coefficient, var in terms
                )
                if value:
                    penalties[PENALTY_GROUPS.get(code, code)] = int(value)
                total += int(value)
            result.penalties = penalties
            result.total_penalty = total
        result.log = (
            f"status={status_name} wall_time={solver.WallTime():.2f}s "
            f"branches={solver.NumBranches()} conflicts={solver.NumConflicts()} "
            f"occurrences={len(self.occurrences)}"
        )
        return result


class _StopCallback(cp_model.CpSolverSolutionCallback):
    """Stops the search when the run is cancelled from the API."""

    def __init__(self, should_stop):
        super().__init__()
        self._should_stop = should_stop

    def on_solution_callback(self) -> None:  # pragma: no cover - timing dependent
        if self._should_stop():
            self.StopSearch()
