"""Phase 6 – CSV import with preview and export in every format."""
from __future__ import annotations

import io

from tests.factory import (
    make_activity,
    make_group,
    make_room,
    make_student,
    make_teacher,
    set_calendar,
)


def _upload(client, entity: str, action: str, text: str, filename: str = "data.csv"):
    return client.post(
        f"/api/imports/{entity}/{action}",
        files={"file": (filename, io.BytesIO(text.encode("utf-8")), "text/csv")},
    )


def test_import_preview_does_not_write(client, db):
    client.post("/api/groups", json={"name": "Kvinta", "code": "KV", "type": "CLASS"})
    csv_text = (
        "external_id,first_name,last_name,class_code\n"
        "S001,Anna,Nováková,KV\n"
        "S002,Jan,Malý,KV\n"
    )
    preview = _upload(client, "students", "preview", csv_text).json()
    assert preview["rows_detected"] == 2
    assert preview["new"] == 2
    assert preview["errors"] == []
    assert preview["committed"] is False
    assert client.get("/api/students").json() == []

    committed = _upload(client, "students", "commit", csv_text).json()
    assert committed["committed"] is True
    students = client.get("/api/students").json()
    assert {s["full_name"] for s in students} == {"Anna Nováková", "Jan Malý"}
    assert students[0]["class_group_name"] == "Kvinta"


def test_import_reports_errors_per_row(client):
    csv_text = (
        "external_id,first_name,last_name,class_code\n"
        "S001,Anna,Nováková,MISSING\n"
        "S002,,Malý,\n"
    )
    preview = _upload(client, "students", "preview", csv_text).json()
    assert preview["rows_detected"] == 2
    assert len(preview["errors"]) == 2
    assert preview["errors"][0]["row"] == 2
    assert "MISSING" in preview["errors"][0]["message"]
    assert "first_name" in preview["errors"][1]["message"]


def test_import_second_run_updates(client):
    csv_text = "external_id,first_name,last_name\nS001,Anna,Nováková\n"
    _upload(client, "students", "commit", csv_text)
    second = _upload(
        client, "students", "commit", "external_id,first_name,last_name\nS001,Anna,Malá\n"
    ).json()
    assert second["updated"] == 1 and second["new"] == 0
    assert client.get("/api/students").json()[0]["full_name"] == "Anna Malá"


def test_import_individual_lessons_csv(client):
    _upload(client, "students", "commit", "external_id,first_name,last_name\nS001,Anna,Nováková\n")
    _upload(client, "teachers", "commit", "external_id,first_name,last_name\nT001,Jan,Dvořák\n")
    client.post("/api/subjects", json={"name": "Klavír", "code": "KLV"})

    csv_text = (
        "student_external_id,subject_code,teacher_external_id,duration_minutes,"
        "occurrences_per_cycle,allowed_days,required_features\n"
        "S001,KLV,T001,45,1,Po;Út,piano\n"
    )
    preview = _upload(client, "individual-lessons", "preview", csv_text).json()
    assert preview["new"] == 1
    assert preview["preview"][0]["allowed_days"] == [0, 1]

    _upload(client, "individual-lessons", "commit", csv_text)
    lessons = client.get("/api/individual-lessons").json()
    assert len(lessons) == 1
    assert lessons[0]["allowed_day_ordinals"] == [0, 1]
    assert lessons[0]["teacher_name"] == "Jan Dvořák"


def test_import_availability_accepts_times_and_day_names(client):
    _upload(client, "teachers", "commit", "external_id,first_name,last_name\nT001,Jan,Dvořák\n")
    csv_text = (
        "owner_type,owner_external_id,kind,day,start,end,note\n"
        "TEACHER,T001,UNAVAILABLE,Po,8:00,12:00,Externí spolupráce\n"
    )
    result = _upload(client, "availability", "commit", csv_text).json()
    assert result["committed"] is True
    windows = client.get("/api/availability", params={"owner_type": "TEACHER"}).json()
    assert windows[0]["day_ordinal"] == 0
    assert windows[0]["start_minute"] == 480 and windows[0]["end_minute"] == 720


def test_import_rooms_with_features(client):
    csv_text = "code,name,building,capacity,features\nK1,Klavírní studio,B,4,piano;soundproof\n"
    _upload(client, "rooms", "commit", csv_text)
    room = client.get("/api/rooms").json()[0]
    assert sorted(room["feature_names"]) == ["piano", "soundproof"]


def _solved_version(client, db):
    set_calendar(db, days=2, slots=3)
    make_room(db, "A1", capacity=30)
    kvinta = make_group(db, "Kvinta")
    anna = make_student(db, "Anna Nováková", kvinta)
    make_activity(
        db, "Matematika Kvinta", teachers=[make_teacher(db, "Jan Novák")],
        groups=[kvinta], occurrences=2,
    )
    db.commit()
    run = client.post("/api/solver/runs", json={"time_limit_seconds": 10}).json()
    return run["schedule_version_id"], anna


def test_export_every_format(client, db):
    version_id, anna = _solved_version(client, db)

    csv_response = client.get(f"/api/exports/schedule/{version_id}", params={"format": "csv"})
    assert csv_response.status_code == 200
    body = csv_response.content.decode("utf-8-sig")
    assert "activity" in body.splitlines()[0]
    assert "Matematika Kvinta" in body

    for fmt, marker in (("xlsx", b"PK"), ("pdf", b"%PDF"), ("ics", b"BEGIN:VCALENDAR")):
        response = client.get(
            f"/api/exports/schedule/{version_id}", params={"format": fmt}
        )
        assert response.status_code == 200, fmt
        assert response.content.startswith(marker), fmt
        assert "attachment" in response.headers["content-disposition"]


def test_export_scopes(client, db):
    version_id, anna = _solved_version(client, db)
    student_csv = client.get(
        f"/api/exports/schedule/{version_id}",
        params={"format": "csv", "scope": "student", "entity_id": anna.id},
    ).content.decode("utf-8-sig")
    assert student_csv.count("Matematika Kvinta") == 2

    empty = client.get(
        f"/api/exports/schedule/{version_id}",
        params={"format": "csv", "scope": "room", "entity_id": 9999},
    ).content.decode("utf-8-sig")
    assert len(empty.strip().splitlines()) == 1
