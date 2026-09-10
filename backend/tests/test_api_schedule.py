"""API level tests: solving, viewing, manual editing and versioning."""
from __future__ import annotations

from app.models.enums import GroupType
from tests.factory import (
    SLOT,
    abs_minute,
    make_activity,
    make_group,
    make_room,
    make_student,
    make_teacher,
    set_calendar,
)


def _small_school(db):
    set_calendar(db, days=2, slots=3)
    make_room(db, "A1", capacity=30)
    make_room(db, "K1", capacity=4, features=["piano"])
    kvinta = make_group(db, "Kvinta", GroupType.CLASS)
    anna = make_student(db, "Anna Nováková", kvinta)
    make_student(db, "Petr Malý", kvinta)
    math_teacher = make_teacher(db, "Jan Novák")
    piano_teacher = make_teacher(db, "Jan Dvořák")
    math = make_activity(
        db, "Matematika Kvinta", teachers=[math_teacher], groups=[kvinta], occurrences=2
    )
    piano = make_activity(
        db, "Klavír – Anna", teachers=[piano_teacher], students=[anna], features=["piano"]
    )
    db.commit()
    return {
        "class": kvinta,
        "anna": anna,
        "math": math,
        "piano": piano,
        "math_teacher": math_teacher,
    }


def _run_solver(client, **kwargs):
    response = client.post("/api/solver/runs", json={"time_limit_seconds": 10, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


def test_solver_run_endpoint_produces_a_version(client, db):
    _small_school(db)
    run = _run_solver(client)
    assert run["status"] in ("OPTIMAL", "FEASIBLE")
    assert run["schedule_version_id"]

    version = client.get(f"/api/versions/{run['schedule_version_id']}").json()
    assert version["item_count"] == 3
    assert len(version["items"]) == 3
    item = version["items"][0]
    assert item["activity_name"]
    assert item["teacher_names"]


def test_validate_endpoint_reports_dataset_problems(client, db):
    _small_school(db)
    issues = client.post("/api/solver/validate").json()
    assert isinstance(issues, list)
    assert all("severity" in issue for issue in issues)


def test_student_view_shows_personal_timetable(client, db):
    world = _small_school(db)
    run = _run_solver(client)
    version_id = run["schedule_version_id"]

    view = client.get(
        f"/api/versions/{version_id}/view",
        params={"scope": "student", "entity_id": world["anna"].id},
    ).json()
    names = {item["activity_name"] for item in view["items"]}
    assert "Klavír – Anna" in names, "a student sees their individual lesson"
    assert "Matematika Kvinta" in names, "and their class lessons"
    assert view["title"] == "Anna Nováková"

    # The classmate has the class lessons only.
    petr_id = [s["id"] for s in client.get("/api/students").json() if s["first_name"] == "Petr"][0]
    petr_view = client.get(
        f"/api/versions/{version_id}/view",
        params={"scope": "student", "entity_id": petr_id},
    ).json()
    assert "Klavír – Anna" not in {i["activity_name"] for i in petr_view["items"]}


def test_teacher_and_room_views(client, db):
    world = _small_school(db)
    run = _run_solver(client)
    version_id = run["schedule_version_id"]

    teacher_view = client.get(
        f"/api/versions/{version_id}/view",
        params={"scope": "teacher", "entity_id": world["math_teacher"].id},
    ).json()
    assert all(
        world["math_teacher"].id in item["teacher_ids"] for item in teacher_view["items"]
    )

    room_id = client.get("/api/rooms").json()[0]["id"]
    room_view = client.get(
        f"/api/versions/{version_id}/view", params={"scope": "room", "entity_id": room_id}
    ).json()
    assert all(item["room_id"] == room_id for item in room_view["items"])


def test_move_validation_reports_named_conflicts(client, db):
    world = _small_school(db)
    run = _run_solver(client)
    version = client.get(f"/api/versions/{run['schedule_version_id']}").json()
    piano_item = next(i for i in version["items"] if i["activity_id"] == world["piano"].id)
    math_item = next(i for i in version["items"] if i["activity_id"] == world["math"].id)

    # Move the piano lesson on top of Anna's mathematics lesson.
    check = client.post(
        f"/api/scheduled-activities/{piano_item['id']}/validate-move",
        json={"start_minute": math_item["start_minute"], "room_id": piano_item["room_id"]},
    ).json()
    assert check["ok"] is False
    codes = {c["code"] for c in check["conflicts"]}
    assert "HC01_STUDENT_CONFLICT" in codes
    assert any("Anna" in c["message"] for c in check["conflicts"])
    assert check["room_suggestions"], "the scheduler is told which rooms would work"


def test_move_is_rejected_unless_forced(client, db):
    world = _small_school(db)
    run = _run_solver(client)
    version = client.get(f"/api/versions/{run['schedule_version_id']}").json()
    piano_item = next(i for i in version["items"] if i["activity_id"] == world["piano"].id)
    math_item = next(i for i in version["items"] if i["activity_id"] == world["math"].id)

    blocked = client.patch(
        f"/api/scheduled-activities/{piano_item['id']}",
        json={"start_minute": math_item["start_minute"]},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["conflicts"]

    forced = client.patch(
        f"/api/scheduled-activities/{piano_item['id']}?force=true",
        json={"start_minute": math_item["start_minute"]},
    )
    assert forced.status_code == 200
    assert forced.json()["start_minute"] == math_item["start_minute"]


def test_valid_move_updates_day_ordinal(client, db):
    _small_school(db)
    run = _run_solver(client)
    version = client.get(f"/api/versions/{run['schedule_version_id']}").json()
    item = version["items"][0]
    target = abs_minute(1, 8 * 60)

    check = client.post(
        f"/api/scheduled-activities/{item['id']}/validate-move",
        json={"start_minute": target, "room_id": item["room_id"]},
    ).json()
    if check["ok"]:
        moved = client.patch(
            f"/api/scheduled-activities/{item['id']}",
            json={"start_minute": target, "room_id": item["room_id"]},
        ).json()
        assert moved["day_ordinal"] == 1


def test_lock_unlock_roundtrip(client, db):
    _small_school(db)
    run = _run_solver(client)
    version = client.get(f"/api/versions/{run['schedule_version_id']}").json()
    item = version["items"][0]

    locked = client.post(
        f"/api/scheduled-activities/{item['id']}/lock",
        json={"lock_time": True, "lock_room": False},
    ).json()
    assert locked["lock_time"] is True and locked["lock_room"] is False

    unlocked = client.post(f"/api/scheduled-activities/{item['id']}/unlock").json()
    assert unlocked["lock_time"] is False


def test_version_duplicate_publish_and_compare(client, db):
    _small_school(db)
    run = _run_solver(client)
    version_id = run["schedule_version_id"]

    copy = client.post(
        f"/api/versions/{version_id}/duplicate", json={"name": "Draft 2"}
    ).json()
    assert copy["item_count"] == 3
    assert copy["status"] == "DRAFT"

    comparison = client.get(
        f"/api/versions/{version_id}/compare", params={"other": copy["id"]}
    ).json()
    assert comparison["changed"] == 0

    # Move something in the copy and compare again.
    copy_detail = client.get(f"/api/versions/{copy['id']}").json()
    item = copy_detail["items"][0]
    client.patch(
        f"/api/scheduled-activities/{item['id']}?force=true",
        json={"start_minute": item["start_minute"] + SLOT},
    )
    comparison = client.get(
        f"/api/versions/{version_id}/compare", params={"other": copy["id"]}
    ).json()
    assert comparison["changed"] == 1
    assert any(i["change"] == "MOVED" for i in comparison["items"])

    published = client.post(f"/api/versions/{copy['id']}/publish").json()
    assert published["status"] == "PUBLISHED"


def test_reoptimise_from_a_version(client, db):
    _small_school(db)
    first = _run_solver(client)
    second = _run_solver(
        client, base_version_id=first["schedule_version_id"], reoptimize=True
    )
    assert second["status"] in ("OPTIMAL", "FEASIBLE")
    assert second["schedule_version_id"] != first["schedule_version_id"]
    detail = client.get(f"/api/versions/{second['schedule_version_id']}").json()
    assert detail["parent_version_id"] == first["schedule_version_id"]


def test_constraint_weights_are_editable(client):
    weights = client.get("/api/constraint-weights").json()
    assert {w["code"] for w in weights} >= {f"SC{i:02d}" for i in range(1, 16)}

    updated = client.put("/api/constraint-weights/SC01", json={"weight": 5}).json()
    assert updated["weight"] == 5
    disabled = client.put("/api/constraint-weights/SC02", json={"enabled": False}).json()
    assert disabled["enabled"] is False


def test_cancel_marks_the_run(client, db):
    _small_school(db)
    run = _run_solver(client)
    cancelled = client.post(f"/api/solver/runs/{run['id']}/cancel").json()
    assert cancelled["id"] == run["id"]
