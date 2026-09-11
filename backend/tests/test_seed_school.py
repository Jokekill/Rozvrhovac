"""The full-size dataset generator must stay valid, not just large.

The suite builds a scaled down school (three classes) so it stays fast, and
then runs exactly the checks that matter: the shape of the data, and the
solver's own pre-flight validation reporting no errors.
"""
from __future__ import annotations

from app.models import Activity, Room, Student, StudentGroup, Teacher
from app.models.enums import ActivityKind, GroupType
from app.seed_school import SchoolSpec, seed_school
from app.solver.diagnostics import validate_dataset
from app.solver.loader import load_solver_input

SMALL = SchoolSpec(
    gymnasium_classes=("Prima", "Kvinta"),
    lyceum_classes=("1. L",),
    gymnasium_class_sizes=(12, 14),
    lyceum_class_size=12,
    solo_share=0.3,
    rooms_ordinary=6,
)


def test_generator_produces_a_consistent_school(db):
    stats = seed_school(db, SMALL)

    assert stats["students"] == db.query(Student).count()
    assert stats["rooms"] == db.query(Room).count()
    assert db.query(Teacher).count() >= 10

    classes = db.query(StudentGroup).filter(StudentGroup.type == GroupType.CLASS).all()
    assert len(classes) == 3
    for group in classes:
        assert len(group.members) >= 12, "every class has real members, not just a name"

    # Every student belongs to exactly one class and may belong to more groups.
    for student in db.query(Student).all():
        assert student.class_group_id is not None
        class_memberships = [
            m for m in student.memberships if m.group.type == GroupType.CLASS
        ]
        assert len(class_memberships) == 1


def test_generator_covers_every_activity_shape(db):
    seed_school(db, SMALL)
    kinds = {kind for (kind,) in db.query(Activity.kind).distinct()}
    assert {
        ActivityKind.STANDARD,
        ActivityKind.SPLIT,
        ActivityKind.ENSEMBLE,
        ActivityKind.INDIVIDUAL,
    } <= kinds

    solos = db.query(Activity).filter(Activity.kind == ActivityKind.INDIVIDUAL).all()
    assert solos, "a school with art tuition needs one-to-one lessons"
    for solo in solos:
        assert len(solo.students) == 1
        assert solo.align_to_periods is False, "solo lessons are not on the period grid"
        assert solo.time_windows, "solo lessons are restricted to the afternoon"

    durations = {a.duration_minutes for a in db.query(Activity).all()}
    assert len(durations) >= 3, "mixed block lengths, not one universal lesson"


def test_ensembles_mix_students_from_several_classes(db):
    seed_school(db, SMALL)
    ensembles = (
        db.query(StudentGroup).filter(StudentGroup.type == GroupType.ENSEMBLE).all()
    )
    assert ensembles
    mixed = 0
    for group in ensembles:
        classes = {m.student.class_group_id for m in group.members}
        if len(classes) > 1:
            mixed += 1
    assert mixed == len(ensembles), "ensembles must cut across classes"


def test_generated_dataset_passes_pre_solve_validation(db):
    """The generator must not hand the solver an impossible school."""
    seed_school(db, SMALL)
    issues = validate_dataset(load_solver_input(db))
    errors = [issue for issue in issues if issue["severity"] == "ERROR"]
    assert errors == [], errors


def test_generator_is_deterministic_and_refuses_to_run_twice(db):
    first = seed_school(db, SMALL)
    assert seed_school(db, SMALL) == {"skipped": 1}
    assert first["students"] > 0
