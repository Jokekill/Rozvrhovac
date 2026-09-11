"""Full-size test dataset: an eight year gymnasium plus a lyceum.

Shape (all of it configurable through :class:`SchoolSpec`):

* 8 gymnasium classes of 25-30 students (Prima ... Oktáva),
* 4 lyceum classes of 25 students,
* one split computer-science group pair per class, linked with SAME_START,
* cross-class ensembles: choir, chamber orchestra, two drama groups, jazz band,
* individual instrument tuition for roughly a quarter of the school,
* 20 rooms, of which 12 are specialised,
* teachers sized from the actual teaching load, not guessed.

The academic grid runs 08:00-15:20 (eight periods) with an optional zeroth
hour at 07:10, while art tuition may be placed between 13:00 and 20:00, so the
two deliberately overlap: an afternoon solo lesson really can collide with a
class lesson, which is exactly the tension the solver has to resolve.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

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
    CycleConfig,
    Day,
    Period,
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

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
LESSON = 45
ART_WINDOW = (13 * 60, 20 * 60)
# The zeroth hour widens the teaching day; the core grid still starts at 08:00.
CORE_DAY_START = 8 * 60
DAY_WINDOW = (7 * 60 + 10, 20 * 60)

PERIODS = [
    ("0. hodina", 7 * 60 + 10, 7 * 60 + 55),
    ("1. hodina", 8 * 60, 8 * 60 + 45),
    ("2. hodina", 8 * 60 + 55, 9 * 60 + 40),
    ("3. hodina", 9 * 60 + 50, 10 * 60 + 35),
    ("4. hodina", 10 * 60 + 55, 11 * 60 + 40),
    ("5. hodina", 11 * 60 + 50, 12 * 60 + 35),
    ("6. hodina", 12 * 60 + 45, 13 * 60 + 30),
    ("7. hodina", 13 * 60 + 40, 14 * 60 + 25),
    ("8. hodina", 14 * 60 + 35, 15 * 60 + 20),
]

GYMNASIUM_CLASSES = [
    "Prima", "Sekunda", "Tercie", "Kvarta", "Kvinta", "Sexta", "Septima", "Oktáva",
]
LYCEUM_CLASSES = ["1. L", "2. L", "3. L", "4. L"]

SUBJECTS: list[tuple[str, str, str]] = [
    ("MAT", "Matematika", "#3b6ea5"),
    ("CJ", "Český jazyk a literatura", "#a53b52"),
    ("AJ", "Anglický jazyk", "#3ba576"),
    ("NJ", "Německý jazyk", "#2e8b8b"),
    ("DEJ", "Dějepis", "#a5843b"),
    ("ZEM", "Zeměpis", "#6b8e23"),
    ("BIO", "Biologie", "#4f9a4f"),
    ("FYZ", "Fyzika", "#4a5fa5"),
    ("CHE", "Chemie", "#3ba5a1"),
    ("TV", "Tělesná výchova", "#7a7a7a"),
    ("HV", "Hudební výchova", "#2ea55c"),
    ("VV", "Výtvarná výchova", "#b06a2e"),
    ("INF", "Informatika", "#5c3ba5"),
    ("KLV", "Klavír", "#b0562e"),
    ("HOU", "Housle", "#8e2ea5"),
    ("KYT", "Kytara", "#2e6ba5"),
    ("FLE", "Příčná flétna", "#8b6f2e"),
    ("VLC", "Violoncello", "#7a2e5c"),
    ("ZPV", "Sólový zpěv", "#a52e6b"),
    ("BIC", "Bicí nástroje", "#5c5c5c"),
    ("DRA", "Dramatická výchova", "#a52e2e"),
    ("SBOR", "Sborový zpěv", "#2e8b57"),
    ("ORCH", "Orchestr", "#46578b"),
]

# subject code -> weekly lessons, per curriculum
CURRICULUM: dict[str, dict[str, int]] = {
    "gymnazium_lower": {
        "MAT": 4, "CJ": 4, "AJ": 3, "DEJ": 2, "ZEM": 2, "BIO": 2,
        "FYZ": 2, "CHE": 2, "TV": 2, "HV": 1, "VV": 1,
    },
    "gymnazium_upper": {
        "MAT": 4, "CJ": 4, "AJ": 3, "NJ": 2, "DEJ": 2, "ZEM": 2,
        "BIO": 2, "FYZ": 2, "CHE": 2, "TV": 2,
    },
    "lyceum": {
        "MAT": 3, "CJ": 4, "AJ": 3, "NJ": 2, "DEJ": 2, "BIO": 2,
        "CHE": 2, "TV": 2, "HV": 2, "VV": 2,
    },
}

# subject code -> required room feature for the whole-class lesson
SUBJECT_FEATURE = {
    "CHE": "chemistry_lab",
    "FYZ": "physics_lab",
    "TV": "gym",
    "INF": "computers",
}

INSTRUMENTS: list[tuple[str, str | None, tuple[int, ...]]] = [
    # subject code, required room feature, possible lesson lengths
    ("KLV", "piano", (30, 45, 45, 60)),
    ("HOU", "music_room", (30, 45, 45)),
    ("KYT", "music_room", (30, 45)),
    ("FLE", "music_room", (30, 45)),
    ("VLC", "music_room", (45, 45, 60)),
    ("ZPV", "music_room", (30, 45)),
    ("BIC", "drums", (30, 45)),
]

FIRST_NAMES_F = [
    "Anna", "Eliška", "Tereza", "Klára", "Lucie", "Barbora", "Nikola", "Kristýna",
    "Veronika", "Simona", "Adéla", "Natálie", "Karolína", "Michaela", "Kateřina",
    "Markéta", "Aneta", "Petra", "Denisa", "Viktorie", "Sofie", "Julie", "Ema",
    "Laura", "Magdaléna", "Štěpánka", "Vendula", "Iveta", "Zuzana", "Hana",
]
FIRST_NAMES_M = [
    "Jan", "Petr", "Jakub", "Adam", "Marek", "Ondřej", "Filip", "Tomáš", "David",
    "Martin", "Matěj", "Vojtěch", "Lukáš", "Daniel", "Štěpán", "Josef", "Michal",
    "Radek", "Pavel", "Šimon", "Dominik", "Antonín", "Kryštof", "Václav", "Matyáš",
    "Sebastian", "Oliver", "Richard", "Jonáš", "Vít",
]
SURNAMES = [
    "Novák", "Svoboda", "Novotný", "Dvořák", "Černý", "Procházka", "Kučera",
    "Veselý", "Horák", "Němec", "Marek", "Pospíšil", "Malý", "Krejčí", "Beneš",
    "Fiala", "Sedláček", "Doležal", "Zeman", "Kolář", "Navrátil", "Čermák",
    "Vaněk", "Urban", "Blažek", "Kratochvíl", "Bartoš", "Vlček", "Polák",
    "Musil", "Kopecký", "Šimek", "Konečný", "Sýkora", "Melichar", "Štěpánek",
]


def _feminine(surname: str) -> str:
    if surname.endswith("ý"):
        return surname[:-1] + "á"
    if surname.endswith("ek"):
        return surname[:-2] + "ková"
    if surname.endswith(("a", "e")):
        return surname + "ová"
    return surname + "ová"


@dataclass
class SchoolSpec:
    """Knobs for the generator, so the dataset can be resized."""

    seed: int = 7
    gymnasium_classes: tuple[str, ...] = tuple(GYMNASIUM_CLASSES)
    lyceum_classes: tuple[str, ...] = tuple(LYCEUM_CLASSES)
    gymnasium_class_sizes: tuple[int, int] = (25, 30)
    lyceum_class_size: int = 25
    solo_share: float = 0.27
    second_solo_share: float = 0.22
    ensemble_share: float = 0.30
    rooms_ordinary: int = 10
    lessons_per_teacher: int = 20
    tags: dict = field(default_factory=dict)


@dataclass
class Stats:
    students: int = 0
    teachers: int = 0
    rooms: int = 0
    groups: int = 0
    activities: int = 0
    occurrences: int = 0
    solo_lessons: int = 0
    ensembles: int = 0

    def as_dict(self) -> dict[str, int]:
        return self.__dict__.copy()


def seed_school(db: Session, spec: SchoolSpec | None = None) -> dict[str, int]:
    """Create the full school. Refuses to run on a non-empty database."""
    spec = spec or SchoolSpec()
    if db.execute(select(Student)).first() is not None:
        return {"skipped": 1}

    rng = random.Random(spec.seed)
    bootstrap(db)
    stats = Stats()

    # ---- calendar -------------------------------------------------------
    for day in db.execute(select(Day)).scalars():
        day.start_minute, day.end_minute = DAY_WINDOW
    db.execute(Period.__table__.delete())
    for index, (name, start, end) in enumerate(PERIODS):
        db.add(Period(index=index, name=name, start_minute=start, end_minute=end))
    config = db.get(CycleConfig, 1)
    config.individual_preferred_start = ART_WINDOW[0]
    config.individual_preferred_end = ART_WINDOW[1]
    config.max_student_minutes_per_day = 8 * LESSON
    config.core_day_start_minute = CORE_DAY_START
    config.core_block_periods = 4
    config.min_student_lessons_per_day = 4
    # SC18 already owns the zeroth hour, so SC13 must not charge for it twice.
    config.early_threshold_minute = DAY_WINDOW[0]
    db.flush()

    # ---- features, rooms -------------------------------------------------
    feature_names = [
        "classroom", "projector", "computers", "chemistry_lab", "physics_lab",
        "gym", "music_room", "piano", "grand_piano", "drums",
        "stage", "soundproof",
    ]
    features = {}
    for name in feature_names:
        feature = RoomFeature(name=name)
        db.add(feature)
        features[name] = feature
    db.flush()

    room_specs: list[tuple[str, str, str, str, int, list[str]]] = []
    for index in range(1, spec.rooms_ordinary + 1):
        building = "A" if index <= 4 else "B"
        room_specs.append(
            (
                f"Učebna {building}{index}",
                f"{building}{index}",
                building,
                str((index - 1) % 3),
                32,
                ["classroom"] + (["projector"] if index % 2 else []),
            )
        )
    room_specs += [
        ("Laboratoř chemie", "LCH", "B", "1", 30, ["classroom", "chemistry_lab", "projector"]),
        ("Laboratoř fyziky", "LFY", "B", "2", 30, ["classroom", "physics_lab", "projector"]),
        ("Počítačová učebna P1", "P1", "A", "2", 17, ["classroom", "computers", "projector"]),
        ("Počítačová učebna P2", "P2", "A", "2", 17, ["classroom", "computers", "projector"]),
        ("Tělocvična", "T1", "C", "0", 80, ["gym"]),
        ("Klavírní studio K1", "K1", "D", "1", 4, ["music_room", "piano", "soundproof"]),
        ("Klavírní studio K2", "K2", "D", "1", 4, ["music_room", "piano", "soundproof"]),
        ("Hudební studio S1", "S1", "D", "1", 12, ["music_room", "soundproof", "drums"]),
        ("Divadelní sál", "D1", "D", "0", 45, ["stage", "soundproof"]),
        (
            "Koncertní sál",
            "KS",
            "D",
            "0",
            80,
            ["classroom", "music_room", "piano", "grand_piano", "stage"],
        ),
    ]
    rooms: dict[str, Room] = {}
    for name, code, building, floor, capacity, feature_list in room_specs:
        room = Room(
            name=name, code=code, building=building, floor=floor, capacity=capacity
        )
        db.add(room)
        db.flush()
        for feature_name in feature_list:
            db.add(
                RoomFeatureAssignment(room_id=room.id, feature_id=features[feature_name].id)
            )
        rooms[code] = room
    db.flush()
    stats.rooms = len(rooms)

    # ---- subjects --------------------------------------------------------
    subjects: dict[str, Subject] = {}
    for code, name, color in SUBJECTS:
        subject = Subject(name=name, code=code, color=color)
        db.add(subject)
        subjects[code] = subject
    db.flush()

    # ---- classes and students -------------------------------------------
    used_external_ids = 0

    def make_person_name() -> tuple[str, str]:
        if rng.random() < 0.5:
            return rng.choice(FIRST_NAMES_F), _feminine(rng.choice(SURNAMES))
        return rng.choice(FIRST_NAMES_M), rng.choice(SURNAMES)

    classes: dict[str, StudentGroup] = {}
    class_students: dict[str, list[Student]] = {}
    class_kind: dict[str, str] = {}

    def make_class(name: str, code: str, size: int, kind: str) -> None:
        nonlocal used_external_ids
        group = StudentGroup(name=name, code=code, type=GroupType.CLASS)
        db.add(group)
        db.flush()
        classes[name] = group
        class_kind[name] = kind
        class_students[name] = []
        for _ in range(size):
            used_external_ids += 1
            first, last = make_person_name()
            student = Student(
                first_name=first,
                last_name=last,
                external_id=f"S{used_external_ids:04d}",
                class_group_id=group.id,
            )
            db.add(student)
            db.flush()
            db.add(StudentGroupMember(group_id=group.id, student_id=student.id))
            class_students[name].append(student)
        db.flush()

    for index, name in enumerate(spec.gymnasium_classes):
        size = rng.randint(*spec.gymnasium_class_sizes)
        kind = "gymnazium_lower" if index < 4 else "gymnazium_upper"
        make_class(name, f"G-{name.upper()}", size, kind)
    for name in spec.lyceum_classes:
        make_class(name, f"L-{name.replace(' ', '').replace('.', '')}", spec.lyceum_class_size, "lyceum")

    all_students = [s for group in class_students.values() for s in group]
    stats.students = len(all_students)

    # ---- teachers sized from the real load -------------------------------
    lesson_load: dict[str, int] = {}
    for class_name in classes:
        for code, count in CURRICULUM[class_kind[class_name]].items():
            lesson_load[code] = lesson_load.get(code, 0) + count
        lesson_load["INF"] = lesson_load.get("INF", 0) + 2  # two split groups

    teachers_by_subject: dict[str, list[Teacher]] = {}
    teacher_index = 0

    def make_teacher(subject_codes: list[str], *, max_day: int = 6 * LESSON) -> Teacher:
        nonlocal teacher_index
        teacher_index += 1
        first, last = make_person_name()
        teacher = Teacher(
            first_name=first,
            last_name=last,
            external_id=f"T{teacher_index:03d}",
            max_minutes_per_day=max_day,
            max_consecutive_minutes=3 * LESSON,
        )
        db.add(teacher)
        db.flush()
        for code in subject_codes:
            teachers_by_subject.setdefault(code, []).append(teacher)
        return teacher

    for code, total in sorted(lesson_load.items()):
        needed = max(1, -(-total // spec.lessons_per_teacher))
        if code == "INF":
            # Both halves of a split lesson run at the same moment.
            needed = max(2, needed)
        for _ in range(needed):
            make_teacher([code])

    for code, _, _ in INSTRUMENTS:
        count = 3 if code == "KLV" else 2 if code in {"HOU", "ZPV"} else 1
        for _ in range(count):
            make_teacher([code], max_day=5 * LESSON)

    choir_master = make_teacher(["SBOR", "HV"])
    conductor = make_teacher(["ORCH"])
    drama_teachers = [make_teacher(["DRA"]), make_teacher(["DRA"])]
    teachers_by_subject.setdefault("HV", []).append(choir_master)
    db.flush()
    stats.teachers = teacher_index

    teacher_minutes: dict[int, int] = {}

    def pick_teacher(code: str, minutes: int, *, exclude: set[int] | None = None) -> Teacher:
        """Least loaded qualified teacher, so nobody is over-booked by accident.

        ``exclude`` keeps the two halves of a split lesson apart: they are tied
        with SAME_START, so one teacher could never cover both.
        """
        candidates = [
            t for t in teachers_by_subject[code] if not exclude or t.id not in exclude
        ]
        if not candidates:
            candidates = teachers_by_subject[code]
        chosen = min(candidates, key=lambda t: teacher_minutes.get(t.id, 0))
        teacher_minutes[chosen.id] = teacher_minutes.get(chosen.id, 0) + minutes
        return chosen

    # ---- activity helper -------------------------------------------------
    def add_activity(
        name: str,
        subject_code: str,
        teachers: list[Teacher],
        *,
        groups: list[StudentGroup] = (),
        students: list[Student] = (),
        duration: int = LESSON,
        occurrences: int = 1,
        required_features: list[str] = (),
        preferred_rooms: list[str] = (),
        kind: ActivityKind = ActivityKind.STANDARD,
        align: bool = True,
        art_window: bool = False,
        allowed_days: list[int] | None = None,
        min_capacity: int | None = None,
        fixed_start: int | None = None,
        fixed_room: str | None = None,
    ) -> Activity:
        activity = Activity(
            name=name,
            subject_id=subjects[subject_code].id,
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
        for teacher in teachers:
            db.add(ActivityTeacher(activity_id=activity.id, teacher_id=teacher.id))
        for group in groups:
            db.add(ActivityStudentGroup(activity_id=activity.id, group_id=group.id))
        for student in students:
            db.add(ActivityStudent(activity_id=activity.id, student_id=student.id))
        for feature_name in required_features:
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
        if art_window:
            for ordinal in allowed_days if allowed_days is not None else range(5):
                db.add(
                    ActivityTimeWindow(
                        activity_id=activity.id,
                        kind=TimeWindowKind.ALLOWED,
                        day_ordinal=ordinal,
                        start_minute=ART_WINDOW[0],
                        end_minute=ART_WINDOW[1],
                    )
                )
        db.flush()
        stats.activities += 1
        stats.occurrences += occurrences
        return activity

    # ---- ordinary class lessons -----------------------------------------
    home_rooms = [
        code
        for code, room in rooms.items()
        if "classroom" in {fa.feature.name for fa in room.feature_assignments}
        and room.capacity >= 30
    ]
    for index, (class_name, group) in enumerate(classes.items()):
        home = home_rooms[index % len(home_rooms)]
        for code, count in CURRICULUM[class_kind[class_name]].items():
            feature = SUBJECT_FEATURE.get(code)
            add_activity(
                f"{subjects[code].name} {class_name}",
                code,
                [pick_teacher(code, count * LESSON)],
                groups=[group],
                occurrences=count,
                required_features=[feature] if feature else ["classroom"],
                preferred_rooms=[] if feature else [home],
            )

    # ---- split computer science, linked SAME_START -----------------------
    for class_name, group in classes.items():
        members = class_students[class_name]
        half = len(members) // 2
        first_half = make_group_helper(db, f"{class_name} – informatika 1", f"{group.code}-INF1", members[:half])
        second_half = make_group_helper(db, f"{class_name} – informatika 2", f"{group.code}-INF2", members[half:])
        first_teacher = pick_teacher("INF", LESSON)
        second_teacher = pick_teacher("INF", LESSON, exclude={first_teacher.id})
        left = add_activity(
            f"Informatika {class_name} – skupina 1", "INF",
            [first_teacher], groups=[first_half],
            required_features=["computers"], kind=ActivityKind.SPLIT,
        )
        right = add_activity(
            f"Informatika {class_name} – skupina 2", "INF",
            [second_teacher], groups=[second_half],
            required_features=["computers"], kind=ActivityKind.SPLIT,
        )
        db.add(
            ActivityLink(
                kind=LinkKind.SAME_START,
                activity_a_id=left.id,
                activity_b_id=right.id,
                note="Půlená informatika musí běžet paralelně.",
            )
        )
    db.flush()

    # ---- cross class ensembles ------------------------------------------
    pool = list(all_students)
    rng.shuffle(pool)
    cursor = 0

    def take(count: int) -> list[Student]:
        nonlocal cursor
        chunk = pool[cursor : cursor + count]
        cursor += count
        return chunk

    # Sizes are capped so that a scaled down school still produces valid
    # ensembles instead of asking for more members than it has students.
    budget = max(1, int(len(all_students) * spec.ensemble_share * 4))
    def sized(wanted: int) -> int:
        return max(4, min(wanted, budget // 5))

    ensemble_specs = [
        ("Pěvecký sbor", "SBOR", "SBOR", sized(44), 90, [choir_master], ["grand_piano"], None),
        ("Komorní orchestr", "ORCH", "ORCH", sized(26), 90, [conductor], ["grand_piano"], None),
        ("Dramatický soubor A", "DRAMA-A", "DRA", sized(20), 90, [drama_teachers[0]], ["stage"], None),
        ("Dramatický soubor B", "DRAMA-B", "DRA", sized(18), 90, [drama_teachers[1]], ["stage"], None),
        ("Jazzový band", "JAZZ", "ORCH", sized(12), 90, [conductor], ["music_room"], None),
    ]
    for name, code, subject_code, size, duration, teachers, required, min_cap in ensemble_specs:
        members = take(size)
        group = make_group_helper(db, name, code, members, GroupType.ENSEMBLE)
        add_activity(
            name, subject_code, teachers, groups=[group], duration=duration,
            required_features=required, kind=ActivityKind.ENSEMBLE, align=False,
            art_window=True, min_capacity=min_cap,
        )
        stats.ensembles += 1

    # A fixed dress rehearsal, Thursday 17:00 in the concert hall (HC09).
    choir_group = db.execute(
        select(StudentGroup).where(StudentGroup.code == "SBOR")
    ).scalars().one()
    add_activity(
        "Generální zkouška sboru", "SBOR", [choir_master], groups=[choir_group],
        duration=90, kind=ActivityKind.ENSEMBLE, align=False,
        fixed_start=3 * MINUTES_PER_DAY + 17 * 60, fixed_room="KS",
    )

    # ---- individual tuition ---------------------------------------------
    solo_students = rng.sample(all_students, int(len(all_students) * spec.solo_share))
    for student in solo_students:
        code, feature, lengths = rng.choice(INSTRUMENTS)
        duration = rng.choice(lengths)
        occurrences = 2 if rng.random() < spec.second_solo_share else 1
        days = sorted(rng.sample(range(5), rng.choice([2, 2, 3])))
        add_activity(
            f"{subjects[code].name} – {student.full_name}",
            code,
            [pick_teacher(code, duration * occurrences)],
            students=[student],
            duration=duration,
            occurrences=occurrences,
            required_features=[feature] if feature else [],
            kind=ActivityKind.INDIVIDUAL,
            align=False,
            art_window=True,
            allowed_days=days,
        )
        stats.solo_lessons += 1

    # ---- availability and preferences -----------------------------------
    all_teachers = db.execute(select(Teacher)).scalars().all()

    # A teacher of a fixed lesson must stay available on that day, otherwise the
    # dataset contradicts itself before the solver even starts.
    fixed_days: dict[int, set[int]] = {}
    for activity in db.execute(
        select(Activity).where(Activity.fixed_start_minute.isnot(None))
    ).scalars():
        day_ordinal = activity.fixed_start_minute // MINUTES_PER_DAY
        for link in activity.teachers:
            fixed_days.setdefault(link.teacher_id, set()).add(day_ordinal)

    part_timers = rng.sample(all_teachers, max(4, len(all_teachers) // 6))
    for teacher in part_timers:
        choices = [d for d in range(5) if d not in fixed_days.get(teacher.id, set())]
        if not choices:
            continue
        free_day = rng.choice(choices)
        db.add(
            AvailabilityWindow(
                owner_type=OwnerType.TEACHER, owner_id=teacher.id,
                kind=AvailabilityKind.UNAVAILABLE, day_ordinal=free_day,
                start_minute=0, end_minute=24 * 60, note="Nepracovní den",
            )
        )
    for teacher in rng.sample(all_teachers, max(3, len(all_teachers) // 8)):
        for ordinal in range(5):
            db.add(
                AvailabilityWindow(
                    owner_type=OwnerType.TEACHER, owner_id=teacher.id,
                    kind=AvailabilityKind.PREFERRED, day_ordinal=ordinal,
                    start_minute=8 * 60, end_minute=12 * 60,
                )
            )
    db.add(
        AvailabilityWindow(
            owner_type=OwnerType.ROOM, owner_id=rooms["KS"].id,
            kind=AvailabilityKind.UNAVAILABLE, day_ordinal=4,
            start_minute=16 * 60, end_minute=24 * 60, note="Pronájem sálu",
        )
    )
    for student in rng.sample(all_students, 8):
        db.add(
            AvailabilityWindow(
                owner_type=OwnerType.STUDENT, owner_id=student.id,
                kind=AvailabilityKind.UNAVAILABLE, day_ordinal=rng.randrange(5),
                start_minute=14 * 60, end_minute=24 * 60, note="Pravidelná absence",
            )
        )

    if db.execute(select(Schedule)).first() is None:
        db.add(
            Schedule(
                name="Školní rok – gymnázium a lyceum",
                description="Osmileté gymnázium (8 tříd) a lyceum (4 třídy).",
            )
        )

    stats.groups = db.execute(select(StudentGroup)).scalars().all().__len__()
    db.commit()
    return stats.as_dict()


def make_group_helper(
    db: Session,
    name: str,
    code: str,
    members: list[Student],
    group_type: GroupType = GroupType.SUBGROUP,
) -> StudentGroup:
    group = StudentGroup(name=name, code=code, type=group_type)
    db.add(group)
    db.flush()
    for student in members:
        db.add(StudentGroupMember(group_id=group.id, student_id=student.id))
    db.flush()
    return group
