"""Generating test data from the GUI (§22 doplněk).

Generation is destructive, so the tests pin down the guard rails as much as
the happy path.
"""
from __future__ import annotations

from app.models.enums import ActivityKind


def test_info_reports_an_empty_database(client):
    info = client.get("/api/datasets").json()
    assert info["enabled"] is True
    assert info["database_empty"] is True
    assert info["students"] == 0
    assert info["max_gymnasium_classes"] == 8
    assert info["max_lyceum_classes"] == 4


def test_generate_small_school(client):
    result = client.post(
        "/api/datasets/generate",
        json={
            "preset": "school",
            "gymnasium_classes": 2,
            "lyceum_classes": 1,
            "gymnasium_class_min": 10,
            "gymnasium_class_max": 12,
            "lyceum_class_size": 10,
            "solo_share": 0.3,
            "rooms_ordinary": 6,
        },
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["stats"]["students"] >= 30
    assert body["solver_run_id"] is None

    students = client.get("/api/students").json()
    assert len(students) == body["stats"]["students"]
    assert all(student["class_group_name"] for student in students)

    activities = client.get("/api/activities").json()
    kinds = {activity["kind"] for activity in activities}
    assert ActivityKind.INDIVIDUAL in kinds
    assert ActivityKind.ENSEMBLE in kinds

    # The generated dataset must be solvable, not merely present.
    issues = client.post("/api/solver/validate").json()
    assert [i for i in issues if i["severity"] == "ERROR"] == []


def test_generate_refuses_to_mix_with_existing_data(client):
    payload = {
        "preset": "school",
        "gymnasium_classes": 1,
        "lyceum_classes": 0,
        "gymnasium_class_min": 8,
        "gymnasium_class_max": 8,
        "rooms_ordinary": 4,
    }
    assert client.post("/api/datasets/generate", json=payload).status_code == 200

    second = client.post("/api/datasets/generate", json=payload)
    assert second.status_code == 409
    assert "studentů" in second.json()["detail"]


def test_reset_replaces_the_previous_dataset(client):
    payload = {
        "preset": "school",
        "gymnasium_classes": 1,
        "lyceum_classes": 0,
        "gymnasium_class_min": 8,
        "gymnasium_class_max": 8,
        "rooms_ordinary": 4,
    }
    client.post("/api/datasets/generate", json=payload)
    first_count = len(client.get("/api/students").json())

    regenerated = client.post(
        "/api/datasets/generate", json={**payload, "reset": True, "seed": 99}
    )
    assert regenerated.status_code == 200
    assert regenerated.json()["reset"] is True
    assert regenerated.json()["removed"], "the wipe must report what it deleted"
    assert len(client.get("/api/students").json()) == first_count

    # The calendar and the constraint weights are rebuilt, not left empty.
    assert len(client.get("/api/cycle/days").json()) == 5
    assert len(client.get("/api/constraint-weights").json()) >= 15


def test_generate_demo_preset_and_run_the_solver(client):
    result = client.post(
        "/api/datasets/generate",
        json={"preset": "demo", "solve": True, "time_limit_seconds": 20},
    ).json()
    assert result["stats"]["students"] == 60
    assert result["solver_run_id"] is not None

    run = client.get(f"/api/solver/runs/{result['solver_run_id']}").json()
    assert run["status"] in ("OPTIMAL", "FEASIBLE")
    assert run["schedule_version_id"]

    version = client.get(f"/api/versions/{run['schedule_version_id']}").json()
    assert version["item_count"] > 0


def test_invalid_class_sizes_are_rejected(client):
    bad = client.post(
        "/api/datasets/generate",
        json={"preset": "school", "gymnasium_class_min": 30, "gymnasium_class_max": 20},
    )
    assert bad.status_code == 422


def test_generation_can_be_switched_off(client, monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ALLOW_DATASET_GENERATION", "false")
    try:
        response = client.post("/api/datasets/generate", json={"preset": "demo"})
        assert response.status_code == 403
        assert "vypnuté" in response.json()["detail"]
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
