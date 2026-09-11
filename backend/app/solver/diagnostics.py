"""Pre-solve validation (§15).

"NO SOLUTION" is useless to a school scheduler. Before the solver runs we
check the dataset and report concrete, actionable reasons such as
"teacher X needs 23 hours of teaching but only has 18 hours of availability".
"""
from __future__ import annotations

from collections import defaultdict

from app.solver.model import SolverInput

MINUTES_PER_DAY = 1440


def _free_minutes(input_data: SolverInput, unavailable: list[tuple[int, int]]) -> int:
    """Minutes inside the teaching days that are not blocked."""
    total = 0
    for day in input_data.days:
        blocked = 0
        cursor = day.abs_start
        merged = sorted(
            (max(s, day.abs_start), min(e, day.abs_end))
            for s, e in unavailable
            if s < day.abs_end and e > day.abs_start
        )
        for start, end in merged:
            if end <= cursor:
                continue
            blocked += end - max(start, cursor)
            cursor = max(cursor, end)
        total += (day.abs_end - day.abs_start) - blocked
    return total


def _fmt_hours(minutes: int) -> str:
    return f"{minutes / 60:.1f} h"


def validate_dataset(input_data: SolverInput) -> list[dict]:
    """Return a list of diagnostic dicts; ERROR entries make solving pointless."""
    issues: list[dict] = []

    def add(code, severity, message, entity_type=None, entity_id=None, details=None):
        issues.append(
            {
                "code": code,
                "severity": severity,
                "message": message,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "details": details,
            }
        )

    if not input_data.days:
        add("NO_DAYS", "ERROR", "Plánovací cyklus neobsahuje žádný aktivní den.")
        return issues
    if not input_data.rooms:
        add("NO_ROOMS", "ERROR", "V systému není žádná aktivní učebna.")

    teacher_minutes: dict[int, int] = defaultdict(int)
    student_minutes: dict[int, int] = defaultdict(int)

    for activity in input_data.activities:
        if activity.occurrences <= 0:
            continue
        required = activity.duration * activity.occurrences
        for teacher_id in activity.teacher_ids:
            teacher_minutes[teacher_id] += required
        for student_id in activity.student_ids:
            student_minutes[student_id] += required

        if not activity.teacher_ids:
            add(
                "ACTIVITY_WITHOUT_TEACHER",
                "WARNING",
                f"Aktivita '{activity.name}' nemá přiřazeného učitele.",
                "Activity",
                activity.id,
            )
        if not activity.student_ids:
            add(
                "ACTIVITY_WITHOUT_STUDENTS",
                "WARNING",
                f"Aktivita '{activity.name}' nemá žádné účastníky.",
                "Activity",
                activity.id,
            )

        # Room compatibility (HC07 / HC08 / allowed / forbidden).
        if not activity.compatible_room_ids:
            missing_features = activity.required_feature_ids
            reason = (
                "žádná učebna nemá požadované vlastnosti"
                if missing_features
                else "žádná učebna nevyhovuje kapacitě nebo seznamu povolených učeben"
            )
            add(
                "NO_COMPATIBLE_ROOM",
                "ERROR",
                f"Aktivita '{activity.name}' nemá vyhovující učebnu: {reason}.",
                "Activity",
                activity.id,
                {
                    "required_feature_ids": sorted(missing_features),
                    "needed_capacity": max(
                        len(activity.student_ids), activity.min_capacity or 0
                    ),
                    "rejections": activity.room_rejections,
                },
            )
            continue

        if not activity.candidate_starts:
            add(
                "NO_FEASIBLE_START",
                "ERROR",
                (
                    f"Aktivita '{activity.name}' nemá žádný přípustný začátek. "
                    "Dostupnost učitelů a studentů, povolená okna aktivity nebo délka "
                    f"{activity.duration} min neumožňují umístění do vyučovacího dne."
                ),
                "Activity",
                activity.id,
                {"duration_minutes": activity.duration},
            )
            continue

        # Availability of teacher/students and of a suitable room must intersect.
        usable = False
        for start in activity.candidate_starts:
            end = start + activity.duration
            for room_id in activity.compatible_room_ids:
                room = input_data.rooms.get(room_id)
                if room is None:
                    continue
                if not any(start < b_end and end > b_start for b_start, b_end in room.blocked):
                    usable = True
                    break
            if usable:
                break
        if not usable:
            room_names = ", ".join(
                input_data.rooms[r].name
                for r in activity.compatible_room_ids
                if r in input_data.rooms
            )
            add(
                "NO_ROOM_TIME_INTERSECTION",
                "ERROR",
                (
                    f"Aktivita '{activity.name}' vyžaduje současně dostupné účastníky "
                    f"a vyhovující učebnu ({room_names}), jejich dostupnosti ale nemají "
                    "průnik."
                ),
                "Activity",
                activity.id,
            )

        # Fixed lesson sanity (HC09).
        if activity.fixed_start_minute is not None:
            fixed_start = activity.fixed_start_minute
            fixed_end = fixed_start + activity.duration
            day = next(
                (d for d in input_data.days if d.ordinal == fixed_start // MINUTES_PER_DAY),
                None,
            )
            if day is None or fixed_start < day.abs_start or fixed_end > day.abs_end:
                add(
                    "FIXED_OUTSIDE_SCHOOL_DAY",
                    "ERROR",
                    (
                        f"Pevně zadaná aktivita '{activity.name}' leží mimo vyučovací den."
                    ),
                    "Activity",
                    activity.id,
                )
            else:
                for teacher_id in activity.teacher_ids:
                    person = input_data.teachers.get(teacher_id)
                    if person and any(
                        fixed_start < end and fixed_end > start
                        for start, end in person.unavailable
                    ):
                        add(
                            "FIXED_AGAINST_AVAILABILITY",
                            "ERROR",
                            (
                                f"Pevně zadaná aktivita '{activity.name}' je v době, kdy "
                                f"učitel {person.name} není dostupný."
                            ),
                            "Activity",
                            activity.id,
                        )

    # Fixed lessons colliding with each other.
    fixed = [
        a
        for a in input_data.activities
        if a.fixed_start_minute is not None and a.occurrences > 0
    ]
    for index, left in enumerate(fixed):
        for right in fixed[index + 1 :]:
            l_start, l_end = left.fixed_start_minute, left.fixed_start_minute + left.duration
            r_start, r_end = right.fixed_start_minute, right.fixed_start_minute + right.duration
            if not (l_start < r_end and l_end > r_start):
                continue
            shared_students = set(left.student_ids) & set(right.student_ids)
            shared_teachers = set(left.teacher_ids) & set(right.teacher_ids)
            same_room = (
                left.fixed_room_id is not None and left.fixed_room_id == right.fixed_room_id
            )
            if shared_students or shared_teachers or same_room:
                add(
                    "FIXED_LESSONS_COLLIDE",
                    "ERROR",
                    (
                        f"Pevně zadané aktivity '{left.name}' a '{right.name}' se překrývají "
                        "a sdílejí studenty, učitele nebo učebnu."
                    ),
                    "Activity",
                    left.id,
                    {"other_activity_id": right.id},
                )

    # Teacher workload versus availability.
    for teacher_id, needed in teacher_minutes.items():
        person = input_data.teachers.get(teacher_id)
        if person is None:
            continue
        available = _free_minutes(input_data, person.unavailable)
        if needed > available:
            add(
                "TEACHER_CAPACITY",
                "ERROR",
                (
                    f"Učitel {person.name} potřebuje {_fmt_hours(needed)} výuky, ale podle "
                    f"dostupnosti má pouze {_fmt_hours(available)} prostoru."
                ),
                "Teacher",
                teacher_id,
                {"required_minutes": needed, "available_minutes": available},
            )
        elif needed > available * 0.9:
            add(
                "TEACHER_CAPACITY_TIGHT",
                "WARNING",
                (
                    f"Učitel {person.name} má naplněno {needed / max(available, 1):.0%} "
                    "své dostupnosti, rozvrh bude obtížně řešitelný."
                ),
                "Teacher",
                teacher_id,
            )

    # Student workload versus availability.
    for student_id, needed in student_minutes.items():
        person = input_data.students.get(student_id)
        if person is None:
            continue
        available = _free_minutes(input_data, person.unavailable)
        if needed > available:
            add(
                "STUDENT_CAPACITY",
                "ERROR",
                (
                    f"Student {person.name} má {_fmt_hours(needed)} povinné výuky, ale jeho "
                    f"dostupnost umožňuje pouze {_fmt_hours(available)}."
                ),
                "Student",
                student_id,
                {"required_minutes": needed, "available_minutes": available},
            )

    # Can the compulsory morning block (SC17) be filled at all?
    core = input_data.core_periods()
    if core and input_data.weight("SC17") > 0:
        slots_needed = len(core) * len(input_data.days)
        core_windows = [
            (day.offset + period.start_minute, day.offset + period.end_minute)
            for day in input_data.days
            for period in core
        ]
        core_supply: dict[int, int] = defaultdict(int)
        for activity in input_data.activities:
            if activity.occurrences <= 0:
                continue
            fits_core = any(
                start < window_end and start + activity.duration > window_start
                for start in activity.candidate_starts
                for window_start, window_end in core_windows
            )
            if not fits_core:
                continue
            for student_id in activity.student_ids:
                core_supply[student_id] += activity.occurrences
        short = [
            (input_data.students[student_id].name, core_supply.get(student_id, 0))
            for student_id in input_data.students
            if core_supply.get(student_id, 0) < slots_needed
        ]
        if short:
            worst = sorted(short, key=lambda item: item[1])[:3]
            listed = ", ".join(f"{name} ({count})" for name, count in worst)
            add(
                "CORE_BLOCK_UNDERSUPPLIED",
                "WARNING",
                (
                    f"{len(short)} studentů nemá dost hodin na zaplnění prvních "
                    f"{len(core)} hodin každý den: potřeba {slots_needed} hodin za cyklus, "
                    f"nejméně jich má {listed}. Rozvrh vznikne, ale jádro dne "
                    "(SC17) zůstane místy děravé."
                ),
                details={
                    "slots_needed": slots_needed,
                    "students_short": len(short),
                },
            )

    # Room feature demand versus supply.
    supply: dict[int, int] = defaultdict(int)
    for room in input_data.rooms.values():
        for feature_id in room.feature_ids:
            supply[feature_id] += 1
    for activity in input_data.activities:
        for feature_id in activity.required_feature_ids:
            if supply.get(feature_id, 0) == 0:
                add(
                    "FEATURE_NOT_AVAILABLE",
                    "ERROR",
                    (
                        f"Aktivita '{activity.name}' vyžaduje vlastnost učebny, kterou "
                        "nemá žádná učebna v systému."
                    ),
                    "Activity",
                    activity.id,
                    {"feature_id": feature_id},
                )

    # Parallel activities must be able to start at the same time.
    by_id = {a.id: a for a in input_data.activities}
    for link in input_data.links:
        if link.kind != "SAME_START":
            continue
        left, right = by_id.get(link.activity_a_id), by_id.get(link.activity_b_id)
        if not left or not right:
            continue
        if not set(left.candidate_starts) & set(right.candidate_starts):
            add(
                "PARALLEL_NO_COMMON_START",
                "ERROR",
                (
                    f"Aktivity '{left.name}' a '{right.name}' mají být paralelní, ale nemají "
                    "žádný společný přípustný začátek."
                ),
                "Activity",
                left.id,
                {"other_activity_id": right.id},
            )
        if set(left.student_ids) & set(right.student_ids):
            add(
                "PARALLEL_SHARED_STUDENT",
                "ERROR",
                (
                    f"Aktivity '{left.name}' a '{right.name}' mají začínat současně, ale "
                    "sdílejí studenty."
                ),
                "Activity",
                left.id,
                {"other_activity_id": right.id},
            )
        shared_teachers = set(left.teacher_ids) & set(right.teacher_ids)
        if shared_teachers:
            names = ", ".join(
                input_data.teachers[teacher_id].name
                for teacher_id in sorted(shared_teachers)
                if teacher_id in input_data.teachers
            )
            add(
                "PARALLEL_SHARED_TEACHER",
                "ERROR",
                (
                    f"Aktivity '{left.name}' a '{right.name}' mají začínat současně, ale "
                    f"obě má učit {names}. Jedna z půlených skupin potřebuje jiného učitele."
                ),
                "Activity",
                left.id,
                {"other_activity_id": right.id, "teacher_ids": sorted(shared_teachers)},
            )
        shared_rooms = (
            set(left.compatible_room_ids) & set(right.compatible_room_ids)
            if len(set(left.compatible_room_ids) | set(right.compatible_room_ids)) == 1
            else set()
        )
        if shared_rooms:
            room = input_data.rooms.get(next(iter(shared_rooms)))
            add(
                "PARALLEL_SINGLE_ROOM",
                "ERROR",
                (
                    f"Aktivity '{left.name}' a '{right.name}' mají běžet současně, ale obě "
                    f"se vejdou jen do jediné učebny "
                    f"({room.name if room else next(iter(shared_rooms))})."
                ),
                "Activity",
                left.id,
                {"other_activity_id": right.id},
            )

    return issues


def has_errors(issues: list[dict]) -> bool:
    return any(issue["severity"] == "ERROR" for issue in issues)


def staged_infeasibility_probe(input_data: SolverInput, time_limit: int = 5) -> list[dict]:
    """Find which constraint layer removes the last solution.

    Solved as a sequence of relaxations: only students, then teachers, then
    rooms, then fixed lessons, then links. The first layer that turns the
    model infeasible is the one to report.
    """
    from ortools.sat.python import cp_model

    layers = [
        ("students", {"teachers": False, "rooms": False, "fixed": False, "links": False}),
        ("teachers", {"teachers": True, "rooms": False, "fixed": False, "links": False}),
        ("rooms", {"teachers": True, "rooms": True, "fixed": False, "links": False}),
        ("fixed lessons", {"teachers": True, "rooms": True, "fixed": True, "links": False}),
        ("links", {"teachers": True, "rooms": True, "fixed": True, "links": True}),
    ]
    messages = {
        "students": "Konflikt vzniká už mezi studenty a jejich dostupností.",
        "teachers": "Konflikt vzniká po přidání rozvrhu učitelů.",
        "rooms": "Konflikt vzniká po přidání učeben (kapacita, vlastnosti, obsazenost).",
        "fixed lessons": "Konflikt vzniká po přidání pevně zadaných hodin.",
        "links": "Konflikt vzniká po přidání vazeb mezi aktivitami (paralelní výuka apod.).",
    }

    for name, flags in layers:
        builder = _RelaxedModel(input_data, **flags)
        try:
            builder.build()
        except Exception:  # pragma: no cover - defensive
            continue
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit)
        solver.parameters.num_search_workers = 4
        status = solver.Solve(builder.model)
        if status == cp_model.INFEASIBLE:
            return [
                {
                    "code": "INFEASIBLE_LAYER",
                    "severity": "ERROR",
                    "message": messages[name],
                    "entity_type": None,
                    "entity_id": None,
                    "details": {"layer": name},
                }
            ]
        if status == cp_model.UNKNOWN:
            break
    return []


class _RelaxedModel:
    """Builds the hard part of the model with selected layers switched off.

    The input is deep-copied so that relaxing one layer cannot leak into the
    next probe.
    """

    def __init__(
        self, data: SolverInput, *, teachers: bool, rooms: bool, fixed: bool, links: bool
    ):
        import copy

        from app.solver.engine import TimetableModel

        self._flags = {"teachers": teachers, "rooms": rooms, "fixed": fixed, "links": links}
        local = copy.deepcopy(data)
        if not fixed:
            for activity in local.activities:
                activity.fixed_start_minute = None
                activity.fixed_room_id = None
        if not rooms:
            # Rooms are ignored in this layer; keep one dummy candidate so that
            # variable creation does not bail out.
            for activity in local.activities:
                if not activity.compatible_room_ids:
                    activity.compatible_room_ids = [-1]
        self._inner = TimetableModel(local)

    @property
    def model(self):
        return self._inner.model

    def build(self) -> None:
        inner = self._inner
        inner._create_variables()
        if self._flags["rooms"]:
            inner._create_room_variables()
        by_teacher: dict[int, list] = {}
        by_student: dict[int, list] = {}
        for occurrence in inner.occurrences:
            for student_id in occurrence.activity.student_ids:
                by_student.setdefault(student_id, []).append(occurrence.interval)
            if self._flags["teachers"]:
                for teacher_id in occurrence.activity.teacher_ids:
                    by_teacher.setdefault(teacher_id, []).append(occurrence.interval)
        for intervals in list(by_student.values()) + list(by_teacher.values()):
            if len(intervals) > 1:
                inner.model.AddNoOverlap(intervals)
        if self._flags["links"]:
            inner._links()
