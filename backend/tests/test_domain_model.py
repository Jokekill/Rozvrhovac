"""Phase 1 – domain model and CRUD API."""
from __future__ import annotations

from app.models import Student, StudentGroup, StudentGroupMember
from app.models.enums import GroupType
from app.services.participants import students_of


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_bootstrap_creates_cycle_and_weights(client):
    days = client.get("/api/cycle/days").json()
    assert [d["ordinal"] for d in days] == [0, 1, 2, 3, 4]
    assert days[0]["name"] == "Pondělí"
    periods = client.get("/api/cycle/periods").json()
    assert len(periods) == 9  # the zeroth hour plus eight regular ones
    assert periods[0]["name"] == "0. hodina"
    assert periods[0]["start_minute"] == 7 * 60 + 10
    assert periods[1]["start_minute"] == 8 * 60

    # The zeroth hour must sit inside the teaching day, or it is unreachable.
    assert days[0]["start_minute"] <= periods[0]["start_minute"]

    config = client.get("/api/cycle").json()
    assert config["core_day_start_minute"] == periods[1]["start_minute"]
    assert config["core_block_periods"] == 4
    assert config["min_student_lessons_per_day"] == 4


def test_student_crud(client):
    group = client.post(
        "/api/groups", json={"name": "Kvinta", "code": "KV", "type": "CLASS"}
    ).json()
    created = client.post(
        "/api/students",
        json={"first_name": "Anna", "last_name": "Nováková", "class_group_id": group["id"]},
    )
    assert created.status_code == 201
    student = created.json()
    assert student["full_name"] == "Anna Nováková"
    assert student["class_group_name"] == "Kvinta"

    updated = client.put(f"/api/students/{student['id']}", json={"last_name": "Malá"}).json()
    assert updated["full_name"] == "Anna Malá"

    assert client.delete(f"/api/students/{student['id']}").status_code == 204
    assert client.get(f"/api/students/{student['id']}").status_code == 404


def test_group_membership_is_many_to_many(db):
    """A student may be in a class, a subgroup and an ensemble at once."""
    students = [Student(first_name="S", last_name=str(i)) for i in range(3)]
    db.add_all(students)
    db.flush()
    groups = [
        StudentGroup(name="Kvinta", type=GroupType.CLASS),
        StudentGroup(name="Drama A", type=GroupType.CROSS_CLASS),
        StudentGroup(name="Sbor", type=GroupType.ENSEMBLE),
    ]
    db.add_all(groups)
    db.flush()
    for group in groups:
        db.add(StudentGroupMember(group_id=group.id, student_id=students[0].id))
    db.commit()
    db.refresh(students[0])
    assert len(students[0].memberships) == 3


def test_room_features_roundtrip(client):
    piano = client.post("/api/room-features", json={"name": "piano"}).json()
    stage = client.post("/api/room-features", json={"name": "stage"}).json()
    room = client.post(
        "/api/rooms",
        json={"name": "Koncertní sál", "code": "K2", "capacity": 60,
              "feature_ids": [piano["id"], stage["id"]]},
    ).json()
    assert sorted(room["feature_names"]) == ["piano", "stage"]
    room = client.put(f"/api/rooms/{room['id']}", json={"feature_ids": [piano["id"]]}).json()
    assert room["feature_names"] == ["piano"]


def test_activity_participants_expand_groups(client, db):
    from app.models import Activity

    payload_students = []
    for i in range(4):
        payload_students.append(
            client.post(
                "/api/students", json={"first_name": "S", "last_name": f"{i}"}
            ).json()
        )
    group = client.post(
        "/api/groups",
        json={"name": "Drama A", "type": "CROSS_CLASS",
              "student_ids": [s["id"] for s in payload_students[:3]]},
    ).json()
    teacher = client.post(
        "/api/teachers", json={"first_name": "M", "last_name": "Němcová"}
    ).json()
    activity = client.post(
        "/api/activities",
        json={
            "name": "Drama A",
            "duration_minutes": 90,
            "occurrences_per_cycle": 1,
            "teacher_ids": [teacher["id"]],
            "group_ids": [group["id"]],
            "student_ids": [payload_students[3]["id"]],
        },
    ).json()
    assert activity["participant_count"] == 4
    orm = db.get(Activity, activity["id"])
    assert len(students_of(db, orm)) == 4


def test_individual_lesson_bulk_editor(client):
    student = client.post(
        "/api/students", json={"first_name": "Anna", "last_name": "Nováková"}
    ).json()
    teacher = client.post(
        "/api/teachers", json={"first_name": "Jan", "last_name": "Dvořák"}
    ).json()
    subject = client.post("/api/subjects", json={"name": "Klavír", "code": "KLV"}).json()
    rows = client.post(
        "/api/individual-lessons/bulk",
        json={
            "rows": [
                {
                    "student_id": student["id"],
                    "teacher_id": teacher["id"],
                    "subject_id": subject["id"],
                    "duration_minutes": 45,
                    "occurrences_per_cycle": 1,
                    "allowed_day_ordinals": [0, 1],
                }
            ]
        },
    ).json()
    assert len(rows) == 1
    assert rows[0]["student_name"] == "Anna Nováková"
    assert rows[0]["allowed_day_ordinals"] == [0, 1]
    listed = client.get("/api/individual-lessons").json()
    assert len(listed) == 1
    # It is a perfectly ordinary activity underneath.
    activity = client.get(f"/api/activities/{rows[0]['id']}").json()
    assert activity["kind"] == "INDIVIDUAL"
    assert activity["participant_count"] == 1


def test_audit_log_records_changes(client, db):
    from app.models import AuditLog

    student = client.post(
        "/api/students", json={"first_name": "Petr", "last_name": "Malý"}
    ).json()
    client.put(f"/api/students/{student['id']}", json={"last_name": "Velký"})
    actions = [row.action for row in db.query(AuditLog).all()]
    assert "CREATE" in actions and "UPDATE" in actions


def test_seed_demo_dataset(db):
    from app.models import Activity, Room, Teacher
    from app.seed import seed_demo

    stats = seed_demo(db)
    assert stats["students"] == 60
    assert db.query(Teacher).count() == 12
    assert db.query(Room).count() == 10
    individual = db.query(Activity).filter(Activity.kind == "INDIVIDUAL").count()
    assert individual == 15


def test_setting_a_class_makes_the_student_a_member_of_it(client):
    """A class is an ordinary group, so class lessons must include the student."""
    kvinta = client.post(
        "/api/groups", json={"name": "Kvinta", "code": "KV", "type": "CLASS"}
    ).json()
    kvarta = client.post(
        "/api/groups", json={"name": "Kvarta", "code": "KA", "type": "CLASS"}
    ).json()

    student = client.post(
        "/api/students",
        json={"first_name": "Anna", "last_name": "Nováková", "class_group_id": kvinta["id"]},
    ).json()
    assert client.get(f"/api/groups/{kvinta['id']}").json()["student_ids"] == [student["id"]]

    # Moving to another class moves the membership with it.
    client.put(f"/api/students/{student['id']}", json={"class_group_id": kvarta["id"]})
    assert client.get(f"/api/groups/{kvinta['id']}").json()["student_ids"] == []
    assert client.get(f"/api/groups/{kvarta['id']}").json()["student_ids"] == [student["id"]]

    # Clearing the class removes it again.
    client.put(f"/api/students/{student['id']}", json={"class_group_id": None})
    assert client.get(f"/api/groups/{kvarta['id']}").json()["student_ids"] == []


def test_class_membership_survives_an_unrelated_update(client):
    kvinta = client.post(
        "/api/groups", json={"name": "Kvinta", "code": "KV", "type": "CLASS"}
    ).json()
    student = client.post(
        "/api/students",
        json={"first_name": "Petr", "last_name": "Malý", "class_group_id": kvinta["id"]},
    ).json()
    client.put(f"/api/students/{student['id']}", json={"last_name": "Velký"})
    assert client.get(f"/api/groups/{kvinta['id']}").json()["member_count"] == 1
