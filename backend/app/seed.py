"""DEMO dataset (§28).

Contents:
  3 classes / 60 students / 12 teachers / 10 rooms (5 specialised)
  15 individual music lessons, 2 cross-class drama groups, 1 choir,
  1 split computer-science lesson, teacher unavailability and preferences.

The dataset deliberately contains situations that exercise every basic hard
constraint (shared students across groups, a single piano room, a fixed
lesson, teachers who are unavailable part of the week).
"""
from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Activity,
    ActivityLink,
    ActivityRoomPolicy,
    ActivityRoomRequirement,
    ActivityStudent,
    ActivityStudentGroup,
    ActivityTeacher,
    ActivityTimeWindow,
    AvailabilityWindow,
    Room,
    RoomFeature,
    RoomFeatureAssignment,
    Schedule,
    Student,
    StudentGroup,
    StudentGroupMember,
    Subject,
    Teacher,
)
from app.models.calendar import MINUTES_PER_DAY
from app.models.enums import (
    ActivityKind,
    AvailabilityKind,
    GroupType,
    LinkKind,
    OwnerType,
    RoomPolicyKind,
    TimeWindowKind,
)
from app.services.bootstrap import bootstrap

FEATURES = [
    "piano", "grand_piano", "drums", "stage", "projector",
    "computers", "chemistry_lab", "soundproof", "gym",
]

FIRST_NAMES = [
    "Anna", "Jan", "Petr", "Eliška", "Tereza", "Jakub", "Adam", "Klára",
    "Marek", "Lucie", "Ondřej", "Barbora", "Filip", "Nikola", "Tomáš",
    "Kristýna", "David", "Veronika", "Martin", "Simona",
]
LAST_NAMES = [
    "Nováková", "Novák", "Svoboda", "Dvořáková", "Černý", "Procházková",
    "Kučera", "Veselá", "Horák", "Němcová", "Marek", "Pospíšilová",
    "Malý", "Krejčí", "Beneš", "Fialová", "Sedláček", "Doležalová",
    "Zeman", "Kolářová",
]

CLASS_NAMES = ["Kvarta", "Kvinta", "Sexta"]

SUBJECTS = [
    ("Matematika", "MAT", "#3b6ea5"),
    ("Český jazyk", "CJ", "#a53b52"),
    ("Anglický jazyk", "AJ", "#3ba576"),
    ("Dějepis", "DEJ", "#a5843b"),
    ("Informatika", "INF", "#5c3ba5"),
    ("Chemie", "CHE", "#3ba5a1"),
    ("Tělesná výchova", "TV", "#7a7a7a"),
    ("Klavír", "KLV", "#b0562e"),
    ("Housle", "HOU", "#8e2ea5"),
    ("Kytara", "KYT", "#2e6ba5"),
    ("Dramatická výchova", "DRA", "#a52e6b"),
    ("Sborový zpěv", "SBOR", "#2ea55c"),
]


def seed_demo(db: Session, *, seed: int = 42) -> dict[str, int]:
    """Idempotent-ish: refuses to run twice on a non-empty database."""
    if db.execute(select(Student)).first() is not None:
        return {"skipped": 1}

    rng = random.Random(seed)
    bootstrap(db)

    features = {}
    for name in FEATURES:
        feature = RoomFeature(name=name)
        db.add(feature)
        features[name] = feature
    db.flush()

    subjects = {}
    for name, code, color in SUBJECTS:
        subject = Subject(name=name, code=code, color=color)
        db.add(subject)
        subjects[code] = subject
    db.flush()

    # --- rooms: 5 ordinary classrooms + 5 specialised ---------------------
    rooms: dict[str, Room] = {}
    room_specs = [
        ("Učebna A1", "A1", "A", "1", 32, []),
        ("Učebna A2", "A2", "A", "1", 32, []),
        ("Učebna A3", "A3", "A", "2", 28, ["projector"]),
        ("Učebna B1", "B1", "B", "1", 24, ["projector"]),
        ("Učebna B2", "B2", "B", "1", 24, []),
        ("Klavírní studio K1", "K1", "B", "2", 4, ["piano", "soundproof"]),
        ("Koncertní sál K2", "K2", "B", "2", 60, ["grand_piano", "stage", "piano"]),
        ("Divadelní sál D1", "D1", "C", "1", 40, ["stage", "soundproof"]),
        ("Počítačová učebna P1", "P1", "A", "2", 16, ["computers", "projector"]),
        ("Tělocvična T1", "T1", "C", "0", 60, ["gym"]),
    ]
    for name, code, building, floor, capacity, feature_names in room_specs:
        room = Room(
            name=name, code=code, building=building, floor=floor, capacity=capacity
        )
        db.add(room)
        db.flush()
        for feature_name in feature_names:
            db.add(
                RoomFeatureAssignment(room_id=room.id, feature_id=features[feature_name].id)
            )
        rooms[code] = room
    db.flush()

    # --- teachers ---------------------------------------------------------
    teacher_specs = [
        ("Jan", "Novák", "MAT"),
        ("Eva", "Svobodová", "CJ"),
        ("Petra", "Dvořáková", "AJ"),
        ("Martin", "Černý", "DEJ"),
        ("Karel", "Procházka", "INF"),
        ("Hana", "Kučerová", "CHE"),
        ("Roman", "Veselý", "TV"),
        ("Jan", "Dvořák", "KLV"),
        ("Lenka", "Veselá", "HOU"),
        ("Tomáš", "Horák", "KYT"),
        ("Michaela", "Němcová", "DRA"),
        ("Pavel", "Marek", "SBOR"),
    ]
    teachers: dict[str, Teacher] = {}
    for first, last, subject_code in teacher_specs:
        teacher = Teacher(
            first_name=first,
            last_name=last,
            external_id=f"T{len(teachers) + 1:03d}",
            max_minutes_per_day=6 * 45,
            max_consecutive_minutes=3 * 45,
        )
        db.add(teacher)
        teachers[subject_code] = teacher
    db.flush()

    # --- classes and students --------------------------------------------
    classes: dict[str, StudentGroup] = {}
    students_by_class: dict[str, list[Student]] = {}
    counter = 0
    for class_name in CLASS_NAMES:
        group = StudentGroup(name=class_name, code=class_name.upper(), type=GroupType.CLASS)
        db.add(group)
        db.flush()
        classes[class_name] = group
        students_by_class[class_name] = []
        for _ in range(20):
            counter += 1
            student = Student(
                first_name=rng.choice(FIRST_NAMES),
                last_name=rng.choice(LAST_NAMES),
                external_id=f"S{counter:04d}",
                class_group_id=group.id,
            )
            db.add(student)
            db.flush()
            db.add(StudentGroupMember(group_id=group.id, student_id=student.id))
            students_by_class[class_name].append(student)
    db.flush()

    # Named students used by the documentation examples.
    anna = students_by_class["Kvinta"][0]
    anna.first_name, anna.last_name = "Anna", "Nováková"
    honza = students_by_class["Kvarta"][0]
    honza.first_name, honza.last_name = "Jan", "Malý"
    db.flush()

    def make_group(name: str, code: str, group_type: GroupType, members: list[Student]):
        group = StudentGroup(name=name, code=code, type=group_type)
        db.add(group)
        db.flush()
        for student in members:
            db.add(StudentGroupMember(group_id=group.id, student_id=student.id))
        db.flush()
        return group

    # --- split computer science (Kvinta halves) ---------------------------
    kvinta = students_by_class["Kvinta"]
    inf_a = make_group("Kvinta – informatika 1", "KV-INF-1", GroupType.SUBGROUP, kvinta[:10])
    inf_b = make_group("Kvinta – informatika 2", "KV-INF-2", GroupType.SUBGROUP, kvinta[10:])

    # --- cross class drama groups and choir -------------------------------
    drama_a_members = (
        students_by_class["Kvinta"][:6]
        + students_by_class["Kvarta"][:6]
        + students_by_class["Sexta"][:5]
    )
    drama_b_members = (
        students_by_class["Kvinta"][6:11]
        + students_by_class["Kvarta"][6:11]
        + students_by_class["Sexta"][5:10]
    )
    drama_a = make_group("Drama A", "DRAMA-A", GroupType.CROSS_CLASS, drama_a_members)
    drama_b = make_group("Drama B", "DRAMA-B", GroupType.CROSS_CLASS, drama_b_members)
    choir_members = [
        s for cls in CLASS_NAMES for s in students_by_class[cls][::2]
    ]
    choir = make_group("Sbor", "SBOR", GroupType.ENSEMBLE, choir_members)

    # --- activities -------------------------------------------------------
    def add_activity(
        name: str,
        subject_code: str | None,
        teacher_codes: list[str],
        *,
        groups: list[StudentGroup] = (),
        students: list[Student] = (),
        duration: int = 45,
        occurrences: int = 1,
        features_required: list[str] = (),
        preferred_rooms: list[str] = (),
        allowed_rooms: list[str] = (),
        kind: ActivityKind = ActivityKind.STANDARD,
        align: bool = True,
        min_capacity: int | None = None,
        fixed_start: int | None = None,
        fixed_room: str | None = None,
    ) -> Activity:
        activity = Activity(
            name=name,
            subject_id=subjects[subject_code].id if subject_code else None,
            kind=kind,
            duration_minutes=duration,
            occurrences_per_cycle=occurrences,
            align_to_periods=align,
            min_capacity=min_capacity,
            fixed_start_minute=fixed_start,
            fixed_room_id=rooms[fixed_room].id if fixed_room else None,
        )
        db.add(activity)
        db.flush()
        for code in teacher_codes:
            db.add(ActivityTeacher(activity_id=activity.id, teacher_id=teachers[code].id))
        for group in groups:
            db.add(ActivityStudentGroup(activity_id=activity.id, group_id=group.id))
        for student in students:
            db.add(ActivityStudent(activity_id=activity.id, student_id=student.id))
        for feature_name in features_required:
            db.add(
                ActivityRoomRequirement(
                    activity_id=activity.id, feature_id=features[feature_name].id
                )
            )
        for code in preferred_rooms:
            db.add(
                ActivityRoomPolicy(
                    activity_id=activity.id,
                    room_id=rooms[code].id,
                    kind=RoomPolicyKind.PREFERRED,
                )
            )
        for code in allowed_rooms:
            db.add(
                ActivityRoomPolicy(
                    activity_id=activity.id,
                    room_id=rooms[code].id,
                    kind=RoomPolicyKind.ALLOWED,
                )
            )
        db.flush()
        return activity

    core_plan = [("MAT", 4), ("CJ", 3), ("AJ", 3), ("DEJ", 2), ("CHE", 2)]
    for class_name, group in classes.items():
        for subject_code, occurrences in core_plan:
            add_activity(
                f"{subjects[subject_code].name} {class_name}",
                subject_code,
                [subject_code],
                groups=[group],
                occurrences=occurrences,
                features_required=["chemistry_lab"] if subject_code == "CHE" else [],
            )
        add_activity(
            f"Tělesná výchova {class_name}",
            "TV",
            ["TV"],
            groups=[group],
            occurrences=2,
            features_required=["gym"],
        )

    # Split computer science: two halves that must start at the same time.
    inf1 = add_activity(
        "Informatika Kvinta – skupina 1", "INF", ["INF"], groups=[inf_a],
        occurrences=1, features_required=["computers"],
    )
    inf2 = add_activity(
        "Informatika Kvinta – skupina 2", "INF", ["MAT"], groups=[inf_b],
        occurrences=1, features_required=["projector"],
    )
    db.add(
        ActivityLink(
            kind=LinkKind.SAME_START,
            activity_a_id=inf1.id,
            activity_b_id=inf2.id,
            note="Půlená informatika musí běžet paralelně.",
        )
    )

    # Cross class drama and choir.
    add_activity(
        "Drama A", "DRA", ["DRA"], groups=[drama_a], duration=90, occurrences=1,
        kind=ActivityKind.CROSS_CLASS, features_required=["stage"], min_capacity=20,
    )
    add_activity(
        "Drama B", "DRA", ["DRA"], groups=[drama_b], duration=90, occurrences=1,
        kind=ActivityKind.CROSS_CLASS, features_required=["stage"], min_capacity=15,
    )
    add_activity(
        "Sbor", "SBOR", ["SBOR"], groups=[choir], duration=60, occurrences=1,
        kind=ActivityKind.ENSEMBLE, preferred_rooms=["K2"],
    )

    # A fixed lesson (HC09): choir dress rehearsal, Wednesday 15:00 in K2.
    add_activity(
        "Generální zkouška sboru", "SBOR", ["SBOR"], groups=[choir], duration=60,
        occurrences=1, kind=ActivityKind.ENSEMBLE, align=False,
        fixed_start=2 * MINUTES_PER_DAY + 15 * 60, fixed_room="K2",
    )

    # --- 15 individual music lessons --------------------------------------
    instrument_specs = [("KLV", "piano"), ("HOU", None), ("KYT", None)]
    all_students = [s for cls in CLASS_NAMES for s in students_by_class[cls]]
    individual_students = [anna, honza] + [
        s for s in all_students if s.id not in {anna.id, honza.id}
    ][:13]
    for index, student in enumerate(individual_students):
        subject_code, required_feature = instrument_specs[index % 3]
        duration = [45, 30, 60][index % 3]
        activity = add_activity(
            f"{subjects[subject_code].name} – {student.full_name}",
            subject_code,
            [subject_code],
            students=[student],
            duration=duration,
            occurrences=1,
            kind=ActivityKind.INDIVIDUAL,
            align=False,
            features_required=[required_feature] if required_feature else [],
        )
        # Individual lessons are restricted to two afternoons.
        for ordinal in ((index % 2), (index % 2) + 2):
            db.add(
                ActivityTimeWindow(
                    activity_id=activity.id,
                    kind=TimeWindowKind.ALLOWED,
                    day_ordinal=ordinal,
                    start_minute=13 * 60,
                    end_minute=19 * 60,
                )
            )
    db.flush()

    # --- availability and preferences -------------------------------------
    # Jan Dvořák (piano) does not teach on Monday morning.
    db.add(
        AvailabilityWindow(
            owner_type=OwnerType.TEACHER, owner_id=teachers["KLV"].id,
            kind=AvailabilityKind.UNAVAILABLE, day_ordinal=0,
            start_minute=0, end_minute=12 * 60, note="Externí spolupráce",
        )
    )
    # Michaela Němcová (drama) only teaches Wednesday and Thursday.
    for ordinal in (0, 1, 4):
        db.add(
            AvailabilityWindow(
                owner_type=OwnerType.TEACHER, owner_id=teachers["DRA"].id,
                kind=AvailabilityKind.UNAVAILABLE, day_ordinal=ordinal,
                start_minute=0, end_minute=24 * 60,
            )
        )
    # Hana Kučerová (chemistry) leaves early on Friday.
    db.add(
        AvailabilityWindow(
            owner_type=OwnerType.TEACHER, owner_id=teachers["CHE"].id,
            kind=AvailabilityKind.UNAVAILABLE, day_ordinal=4,
            start_minute=12 * 60, end_minute=24 * 60,
        )
    )
    # Preferred morning slot for the mathematician (SC03).
    for ordinal in range(5):
        db.add(
            AvailabilityWindow(
                owner_type=OwnerType.TEACHER, owner_id=teachers["MAT"].id,
                kind=AvailabilityKind.PREFERRED, day_ordinal=ordinal,
                start_minute=8 * 60, end_minute=12 * 60,
            )
        )
    # The concert hall is blocked on Friday afternoon.
    db.add(
        AvailabilityWindow(
            owner_type=OwnerType.ROOM, owner_id=rooms["K2"].id,
            kind=AvailabilityKind.UNAVAILABLE, day_ordinal=4,
            start_minute=13 * 60, end_minute=24 * 60, note="Pronájem",
        )
    )
    # One student has a standing medical appointment.
    db.add(
        AvailabilityWindow(
            owner_type=OwnerType.STUDENT, owner_id=honza.id,
            kind=AvailabilityKind.UNAVAILABLE, day_ordinal=3,
            start_minute=8 * 60, end_minute=10 * 60,
        )
    )

    if db.execute(select(Schedule)).first() is None:
        db.add(Schedule(name="Školní rok – hlavní rozvrh", description="Výchozí rozvrh"))

    db.commit()
    return {
        "students": len(all_students),
        "teachers": len(teachers),
        "rooms": len(rooms),
        "groups": len(classes) + 5,
        "activities": db.execute(select(Activity)).unique().scalars().all().__len__(),
    }
