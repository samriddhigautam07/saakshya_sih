from datetime import date


def application_payload(**overrides):
    payload = {
        "institution_id": "SYN-INST-9001",
        "institution_name": "Example Synthetic College",
        "category": "Extension of Approval",
        "reference_number": "SYN-REF-9001",
        "submitted_at": "2026-10-26",
        "declared_faculty_count": 42,
    }
    return {**payload, **overrides}


def test_create_application_returns_created_record(client, applicant_headers):
    response = client.post("/api/applications", json=application_payload(), headers=applicant_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["id"].startswith("APP-")
    assert body["institution_id"] == "SYN-INST-9001"
    assert body["submitted_at"] == date(2026, 10, 26).isoformat()
    assert body["declared_faculty_count"] == 42
    assert body["owner_user_id"] is not None
    assert body["documents"] == []
    assert body["findings"] == []
    assert len(body["audit_logs"]) == 1


def test_create_application_accepts_document_metadata_only(client, applicant_headers):
    response = client.post(
        "/api/applications",
        json=application_payload(
            documents=[
                {
                    "category": "fire_safety",
                    "filename": "fire-certificate.pdf",
                    "sha256": "a" * 64,
                    "size_bytes": 1234,
                    "field_source": "manual",
                }
            ]
        ),
        headers=applicant_headers,
    )

    assert response.status_code == 201
    document = response.json()["documents"][0]
    assert document["filename"] == "fire-certificate.pdf"
    assert document["sha256"] == "a" * 64
    assert "file_path" not in document


def test_list_applications_returns_created_records(client, applicant_headers):
    client.post("/api/applications", json=application_payload(), headers=applicant_headers)
    client.post("/api/applications", json=application_payload(reference_number="SYN-REF-9002"), headers=applicant_headers)

    response = client.get("/api/applications", headers=applicant_headers)

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert {item["reference_number"] for item in response.json()} == {"SYN-REF-9001", "SYN-REF-9002"}


def test_list_applications_supports_pagination(client, applicant_headers):
    client.post("/api/applications", json=application_payload(), headers=applicant_headers)
    client.post("/api/applications", json=application_payload(reference_number="SYN-REF-9002"), headers=applicant_headers)

    response = client.get("/api/applications?offset=1&limit=1", headers=applicant_headers)

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_application_detail(client, applicant_headers):
    created = client.post("/api/applications", json=application_payload(), headers=applicant_headers).json()

    response = client.get(f"/api/applications/{created['id']}", headers=applicant_headers)

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["institution_name"] == "Example Synthetic College"


def test_patch_application_updates_only_supplied_fields(client, applicant_headers):
    created = client.post("/api/applications", json=application_payload(), headers=applicant_headers).json()

    response = client.patch(
        f"/api/applications/{created['id']}",
        json={"institution_name": "Updated Synthetic College", "declared_faculty_count": None},
        headers=applicant_headers,
    )

    assert response.status_code == 200
    assert response.json()["institution_name"] == "Updated Synthetic College"
    assert response.json()["declared_faculty_count"] is None
    assert response.json()["reference_number"] == "SYN-REF-9001"


def test_invalid_application_input_returns_422(client, applicant_headers):
    response = client.post(
        "/api/applications",
        json=application_payload(declared_faculty_count=-1, category="Unrecognized Category"),
        headers=applicant_headers,
    )

    assert response.status_code == 422


def test_invalid_empty_patch_returns_422(client, applicant_headers):
    created = client.post("/api/applications", json=application_payload(), headers=applicant_headers).json()

    response = client.patch(f"/api/applications/{created['id']}", json={}, headers=applicant_headers)

    assert response.status_code == 422


def test_missing_application_returns_404_for_detail_and_patch(client, applicant_headers):
    assert client.get("/api/applications/does-not-exist", headers=applicant_headers).status_code == 404
    response = client.patch(
        "/api/applications/does-not-exist",
        json={"institution_name": "Updated"},
        headers=applicant_headers,
    )
    assert response.status_code == 404


def test_duplicate_nonempty_reference_number_returns_409(client, applicant_headers):
    client.post("/api/applications", json=application_payload(), headers=applicant_headers)

    response = client.post("/api/applications", json=application_payload(), headers=applicant_headers)

    assert response.status_code == 409
