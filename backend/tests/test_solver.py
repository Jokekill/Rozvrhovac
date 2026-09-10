"""Mandatory solver tests (§29 of the specification).

Each test builds the smallest dataset that makes the constraint bite: the day
has just enough slots that a violation would be the only alternative.
"""
from __future__ import annotations

from app.models import ScheduledActivity
from app.models.enums import ActivityKind, GroupType, LinkKind, OwnerType, SolverStatus
from tests.factory import (
    SLOT,
    abs_minute,
    block,
    items_of,
    make_activity,
    make_group,
    make_link,
    make_room,
    make_student,
    make_subject,
    make_teacher,
    overlaps,
    set_calendar,
    solve,
)


def _by_activity(items, activity):
    return [i for i in items if i.activity_id == activity.id]


def test_student_conflict(db):
    """A student must never have mathematics and piano at the same time."""
    set_calendar(db, days=1, slots=2)
    anna = make_student(db, "Anna Nováková")
    make_room(db, "A1")
    make_room(db, "K1", capacity=4, features=["piano"])
    math_teacher = make_teacher(db, "Jan Novák")
    piano_teacher = make_teacher(db, "Jan Dvořák")
    math = make_activity(db, "Matematika", teachers=[math_teacher], students=[anna])
    piano = make_activity(
        db, "Klavír – Anna", teachers=[piano_teacher], students=[anna],
        features=["piano"], kind=ActivityKind.INDIVIDUAL,
    )

    run = solve(db)
    assert run.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
    items = items_of(db, run)
    assert len(items) == 2
    assert not overlaps(_by_activity(items, math)[0], _by_activity(items, piano)[0])


def test_teacher_conflict(db):
    """One teacher cannot teach two students at once."""
    set_calendar(db, days=1, slots=2)
    make_room(db, "K1", capacity=4, features=["piano"])
    make_room(db, "K2", capacity=4, features=["piano"])
    teacher = make_teacher(db, "Jan Dvořák")
    anna = make_student(db, "Anna Nováková")
    petr = make_student(db, "Petr Malý")
    first = make_activity(
        db, "Klavír – Anna", teachers=[teacher], students=[anna], features=["piano"]
    )
    second = make_activity(
        db, "Klavír – Petr", teachers=[teacher], students=[petr], features=["piano"]
    )

    run = solve(db)
    items = items_of(db, run)
    assert not overlaps(_by_activity(items, first)[0], _by_activity(items, second)[0])


def test_room_conflict(db):
    """Two lessons must not occupy the same room at the same time."""
    set_calendar(db, days=1, slots=2)
    only_room = make_room(db, "A1", capacity=30)
    teacher_a = make_teacher(db, "A Učitel")
    teacher_b = make_teacher(db, "B Učitel")
    class_a = make_group(db, "Kvinta", students=[make_student(db, "S1")])
    class_b = make_group(db, "Kvarta", students=[make_student(db, "S2")])
    first = make_activity(db, "Matematika Kvinta", teachers=[teacher_a], groups=[class_a])
    second = make_activity(db, "Matematika Kvarta", teachers=[teacher_b], groups=[class_b])

    run = solve(db)
    items = items_of(db, run)
    left, right = _by_activity(items, first)[0], _by_activity(items, second)[0]
    assert left.room_id == only_room.id and right.room_id == only_room.id
    assert not overlaps(left, right)


def test_mixed_group_conflict(db):
    """A Drama A member cannot attend their own class lesson at the same time."""
    set_calendar(db, days=1, slots=2)
    make_room(db, "A1")
    make_room(db, "D1", features=["stage"])
    kvinta = make_group(db, "Kvinta", GroupType.CLASS)
    kvarta = make_group(db, "Kvarta", GroupType.CLASS)
    anna = make_student(db, "Anna Nováková", kvinta)
    petr = make_student(db, "Petr Malý", kvarta)
    drama = make_group(db, "Drama A", GroupType.CROSS_CLASS, students=[anna, petr])

    class_lesson = make_activity(
        db, "Matematika Kvinta", teachers=[make_teacher(db, "Jan Novák")], groups=[kvinta]
    )
    drama_lesson = make_activity(
        db, "Drama A", teachers=[make_teacher(db, "M Němcová")], groups=[drama],
        features=["stage"], kind=ActivityKind.CROSS_CLASS,
    )

    run = solve(db)
    items = items_of(db, run)
    left = _by_activity(items, class_lesson)[0]
    right = _by_activity(items, drama_lesson)[0]
    assert not overlaps(left, right), "Anna is in both groups, they cannot be parallel"


def test_room_feature(db):
    """A piano lesson must not be put into a room without a piano."""
    set_calendar(db, days=1, slots=3)
    plain = make_room(db, "A1", capacity=30)
    studio = make_room(db, "K1", capacity=4, features=["piano"])
    anna = make_student(db, "Anna Nováková")
    piano = make_activity(
        db, "Klavír – Anna", teachers=[make_teacher(db, "Jan Dvořák")],
        students=[anna], features=["piano"], kind=ActivityKind.INDIVIDUAL,
    )

    run = solve(db)
    item = _by_activity(items_of(db, run), piano)[0]
    assert item.room_id == studio.id
    assert item.room_id != plain.id


def test_room_capacity(db):
    """HC07 – the room must hold every participant."""
    set_calendar(db, days=1, slots=2)
    small = make_room(db, "K1", capacity=4)
    big = make_room(db, "A1", capacity=30)
    choir_students = [make_student(db, f"S{i}") for i in range(10)]
    choir = make_group(db, "Sbor", GroupType.ENSEMBLE, students=choir_students)
    activity = make_activity(
        db, "Sbor", teachers=[make_teacher(db, "P Marek")], groups=[choir]
    )

    run = solve(db)
    item = _by_activity(items_of(db, run), activity)[0]
    assert item.room_id == big.id and item.room_id != small.id


def test_teacher_availability(db):
    """A lesson must not land outside the teacher's availability."""
    set_calendar(db, days=1, slots=2)
    make_room(db, "A1")
    teacher = make_teacher(db, "Jan Dvořák")
    student = make_student(db, "Anna Nováková")
    activity = make_activity(db, "Klavír", teachers=[teacher], students=[student])
    # Teacher is away during the first slot.
    block(db, OwnerType.TEACHER, teacher.id, 0, 8 * 60, 8 * 60 + SLOT)

    run = solve(db)
    item = _by_activity(items_of(db, run), activity)[0]
    assert item.start_minute >= abs_minute(0, 8 * 60 + SLOT)


def test_student_availability(db):
    """HC05 – the same holds for a student."""
    set_calendar(db, days=1, slots=2)
    make_room(db, "A1")
    student = make_student(db, "Jan Malý")
    activity = make_activity(
        db, "Housle", teachers=[make_teacher(db, "L Veselá")], students=[student]
    )
    block(db, OwnerType.STUDENT, student.id, 0, 8 * 60, 8 * 60 + SLOT)

    run = solve(db)
    item = _by_activity(items_of(db, run), activity)[0]
    assert item.start_minute >= abs_minute(0, 8 * 60 + SLOT)


def test_room_availability(db):
    """HC06 – a room can be blocked for part of the week."""
    set_calendar(db, days=1, slots=2)
    room = make_room(db, "K2", capacity=30)
    activity = make_activity(
        db, "Sbor", teachers=[make_teacher(db, "P Marek")],
        students=[make_student(db, "S1")],
    )
    block(db, OwnerType.ROOM, room.id, 0, 8 * 60, 8 * 60 + SLOT)

    run = solve(db)
    item = _by_activity(items_of(db, run), activity)[0]
    assert item.start_minute >= abs_minute(0, 8 * 60 + SLOT)


def test_fixed_lesson(db):
    """A fixed lesson must stay exactly where it was put."""
    set_calendar(db, days=2, slots=3)
    hall = make_room(db, "K2", capacity=60)
    make_room(db, "A1")
    choir = make_group(
        db, "Sbor", GroupType.ENSEMBLE, students=[make_student(db, "S1")]
    )
    fixed_start = abs_minute(1, 8 * 60 + SLOT)
    rehearsal = make_activity(
        db, "Generální zkouška", teachers=[make_teacher(db, "P Marek")],
        groups=[choir], fixed_start=fixed_start, fixed_room=hall, align=False,
    )

    run = solve(db)
    item = _by_activity(items_of(db, run), rehearsal)[0]
    assert item.start_minute == fixed_start
    assert item.room_id == hall.id


def test_parallel_lessons(db):
    """Linked split groups must start at the same moment (HC12)."""
    set_calendar(db, days=1, slots=3)
    make_room(db, "P1", capacity=16, features=["computers"])
    make_room(db, "A1", capacity=16)
    kvinta = make_group(db, "Kvinta", GroupType.CLASS)
    half_a = make_group(
        db, "INF 1", GroupType.SUBGROUP, students=[make_student(db, "S1", kvinta)]
    )
    half_b = make_group(
        db, "INF 2", GroupType.SUBGROUP, students=[make_student(db, "S2", kvinta)]
    )
    first = make_activity(
        db, "Informatika 1", teachers=[make_teacher(db, "K Procházka")],
        groups=[half_a], features=["computers"],
    )
    second = make_activity(
        db, "Informatika 2", teachers=[make_teacher(db, "J Novák")], groups=[half_b]
    )
    make_link(db, LinkKind.SAME_START, first, second)

    run = solve(db)
    items = items_of(db, run)
    assert (
        _by_activity(items, first)[0].start_minute
        == _by_activity(items, second)[0].start_minute
    )


def test_not_simultaneous_link(db):
    """HC13 – two activities without a shared person can still be forced apart."""
    set_calendar(db, days=1, slots=2)
    make_room(db, "A1")
    make_room(db, "A2")
    left = make_activity(
        db, "Aktivita A", teachers=[make_teacher(db, "T1")],
        students=[make_student(db, "S1")],
    )
    right = make_activity(
        db, "Aktivita B", teachers=[make_teacher(db, "T2")],
        students=[make_student(db, "S2")],
    )
    make_link(db, LinkKind.NOT_SIMULTANEOUS, left, right)

    run = solve(db)
    items = items_of(db, run)
    assert not overlaps(_by_activity(items, left)[0], _by_activity(items, right)[0])


def test_before_link(db):
    """HC14 – A must finish before B starts."""
    set_calendar(db, days=1, slots=2)
    make_room(db, "A1")
    make_room(db, "A2")
    first = make_activity(
        db, "Teorie", teachers=[make_teacher(db, "T1")], students=[make_student(db, "S1")]
    )
    second = make_activity(
        db, "Praxe", teachers=[make_teacher(db, "T2")], students=[make_student(db, "S2")]
    )
    make_link(db, LinkKind.BEFORE, first, second)

    run = solve(db)
    items = items_of(db, run)
    assert (
        _by_activity(items, first)[0].end_minute
        <= _by_activity(items, second)[0].start_minute
    )


def test_required_number_of_lessons(db):
    """HC11 – exactly occurrences_per_cycle placements, no more, no less."""
    set_calendar(db, days=4, slots=2)
    make_room(db, "A1")
    kvinta = make_group(db, "Kvinta", students=[make_student(db, "S1")])
    math = make_activity(
        db, "Matematika Kvinta", teachers=[make_teacher(db, "J Novák")],
        groups=[kvinta], occurrences=4,
    )

    run = solve(db)
    items = _by_activity(items_of(db, run), math)
    assert len(items) == 4
    assert sorted(i.occurrence_index for i in items) == [0, 1, 2, 3]


def test_locked_lesson(db):
    """Re-optimisation must not move a locked lesson."""
    set_calendar(db, days=2, slots=3)
    make_room(db, "A1")
    make_room(db, "A2")
    kvinta = make_group(db, "Kvinta", students=[make_student(db, "S1")])
    math = make_activity(
        db, "Matematika", teachers=[make_teacher(db, "J Novák")], groups=[kvinta]
    )
    run = solve(db)
    item = _by_activity(items_of(db, run), math)[0]

    item.lock_time = True
    item.lock_room = True
    locked_start, locked_room = item.start_minute, item.room_id
    db.commit()

    second_run = solve(db, base_version_id=run.schedule_version_id, reoptimize=True)
    assert second_run.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
    moved = _by_activity(items_of(db, second_run), math)[0]
    assert moved.start_minute == locked_start
    assert moved.room_id == locked_room
    assert moved.lock_time and moved.lock_room


def test_reoptimisation_keeps_unlocked_lessons_stable(db):
    """SC15 – a small change must not reshuffle the whole school."""
    set_calendar(db, days=3, slots=4)
    make_room(db, "A1")
    make_room(db, "A2")
    kvinta = make_group(db, "Kvinta", students=[make_student(db, "S1")])
    subject = make_subject(db, "Matematika")
    make_activity(
        db, "Matematika", teachers=[make_teacher(db, "J Novák")], groups=[kvinta],
        occurrences=3, subject=subject,
    )
    make_activity(
        db, "Čeština", teachers=[make_teacher(db, "E Svobodová")], groups=[kvinta],
        occurrences=2,
    )
    first = solve(db)
    before = {
        (i.activity_id, i.occurrence_index): i.start_minute for i in items_of(db, first)
    }

    second = solve(db, base_version_id=first.schedule_version_id, reoptimize=True)
    after = {
        (i.activity_id, i.occurrence_index): i.start_minute for i in items_of(db, second)
    }
    unchanged = sum(1 for key, value in before.items() if after.get(key) == value)
    assert unchanged >= len(before) - 1


def test_infeasible_schedule(db):
    """An impossible dataset must be reported, with a reason."""
    set_calendar(db, days=1, slots=1)
    make_room(db, "A1")
    teacher = make_teacher(db, "Jan Novák")
    student = make_student(db, "Anna Nováková")
    # Two lessons for the same teacher and student, but only one slot exists.
    make_activity(db, "Matematika", teachers=[teacher], students=[student])
    make_activity(db, "Fyzika", teachers=[teacher], students=[student])

    run = solve(db, time_limit=10)
    assert run.status == SolverStatus.INFEASIBLE
    assert run.diagnostics, "the run must explain why there is no solution"
    codes = {issue["code"] for issue in run.diagnostics}
    assert codes & {"TEACHER_CAPACITY", "STUDENT_CAPACITY", "INFEASIBLE_LAYER"}


def test_infeasible_missing_room_feature_is_explained(db):
    """No room has a stage, so the diagnosis must name that, not 'NO SOLUTION'."""
    set_calendar(db, days=1, slots=2)
    make_room(db, "A1")
    drama_students = [make_student(db, f"S{i}") for i in range(3)]
    drama = make_group(db, "Drama A", GroupType.CROSS_CLASS, students=drama_students)
    activity = make_activity(
        db, "Drama A", teachers=[make_teacher(db, "M Němcová")], groups=[drama]
    )
    # Require a feature that no room has.
    from app.models import ActivityRoomRequirement, RoomFeature

    stage = RoomFeature(name="stage")
    db.add(stage)
    db.flush()
    db.add(ActivityRoomRequirement(activity_id=activity.id, feature_id=stage.id))
    db.commit()

    run = solve(db, time_limit=5)
    assert run.status == SolverStatus.INFEASIBLE
    codes = {issue["code"] for issue in run.diagnostics}
    assert "NO_COMPATIBLE_ROOM" in codes or "FEATURE_NOT_AVAILABLE" in codes
    messages = " ".join(issue["message"] for issue in run.diagnostics)
    assert "Drama A" in messages


def test_penalty_breakdown_is_reported(db):
    """§13 – the result carries the score and its decomposition."""
    set_calendar(db, days=2, slots=4)
    make_room(db, "A1")
    kvinta = make_group(db, "Kvinta", students=[make_student(db, "S1")])
    make_activity(
        db, "Matematika", teachers=[make_teacher(db, "J Novák")], groups=[kvinta],
        occurrences=3,
    )
    run = solve(db)
    assert run.best_score is not None
    assert isinstance(run.penalties, dict)


def test_solver_stores_absolute_time_not_slot_index(db):
    """§34 – results are stored as cycle minutes, duration and room."""
    set_calendar(db, days=2, slots=2)
    make_room(db, "A1")
    make_activity(
        db, "Matematika", teachers=[make_teacher(db, "J Novák")],
        students=[make_student(db, "S1")],
    )
    run = solve(db)
    item = db.query(ScheduledActivity).filter(
        ScheduledActivity.version_id == run.schedule_version_id
    ).one()
    assert item.duration_minutes == SLOT
    assert item.day_ordinal == item.start_minute // 1440
    assert item.room_id is not None
