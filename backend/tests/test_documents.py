from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.file_storage import resolve_private_storage_root
from app.main import create_app
from app.models import DocumentMetadata, UserRole
from app.security import hash_password
from conftest import TEST_JWT_SECRET


def create_application(client, headers, reference="DOC-APP-1"):
    response = client.post(
        "/api/applications",
        json={"institution_name": "Upload Test Institute", "reference_number": reference},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def upload(client, application_id, headers, payload, filename="certificate.pdf", mime="application/pdf", category="fire_safety"):
    return client.post(
        f"/api/applications/{application_id}/documents",
        data={"category": category},
        files={"file": (filename, payload, mime)},
        headers=headers,
    )


def token_for(client, email, password="a-long-test-password-123"):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_valid_upload_extracts_text_stores_metadata_privately_and_serves_content(client, applicant_headers, pdf_bytes):
    application_id = create_application(client, applicant_headers)

    response = upload(client, application_id, applicant_headers, pdf_bytes, filename="../../safe-name.pdf")

    assert response.status_code == 201
    metadata = response.json()
    assert metadata["filename"] == "safe-name.pdf"
    assert metadata["application_id"] == application_id
    assert metadata["sha256"]
    assert metadata["size_bytes"] == len(pdf_bytes)
    assert metadata["processing_status"] == "Awaiting manual fields"
    assert metadata["extraction_status"] == "text_extracted"
    assert metadata["extracted_text_char_count"] > 0
    assert metadata["content_available"] is True
    assert "storage_key" not in metadata

    listed = client.get(f"/api/applications/{application_id}/documents", headers=applicant_headers)
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == metadata["id"]
    assert "extracted_text" not in listed.json()[0]

    extracted = client.get(
        f"/api/applications/{application_id}/documents/{metadata['id']}/extracted-text",
        headers=applicant_headers,
    )
    assert extracted.status_code == 200
    assert "Synthetic PDF extraction test" in extracted.json()["text"]
    assert "[Page 1 | Digital]" in extracted.json()["text"]

    content = client.get(
        f"/api/applications/{application_id}/documents/{metadata['id']}/content",
        headers=applicant_headers,
    )
    assert content.status_code == 200
    assert content.content == pdf_bytes
    assert content.headers["content-type"] == "application/pdf"
    assert content.headers["content-disposition"].startswith("attachment;")
    assert content.headers["cache-control"] == "private, no-store"
    assert str(client.app.state.storage_root) not in content.headers["content-disposition"]
    assert oct(Path(client.app.state.storage_root).stat().st_mode & 0o777) == "0o700"


def test_rejects_invalid_extension_mime_and_signature(client, applicant_headers, pdf_bytes):
    application_id = create_application(client, applicant_headers)

    wrong_extension = upload(client, application_id, applicant_headers, pdf_bytes, filename="not-pdf.txt")
    wrong_mime = upload(client, application_id, applicant_headers, pdf_bytes, filename="wrong-mime.pdf", mime="text/plain")
    bad_signature = upload(client, application_id, applicant_headers, b"not a PDF", filename="fake.pdf")

    assert wrong_extension.status_code == 415
    assert wrong_mime.status_code == 415
    assert bad_signature.status_code == 415
    assert client.get(f"/api/applications/{application_id}/documents", headers=applicant_headers).json() == []


def test_rejects_oversized_upload_using_configured_limit(client, applicant_headers):
    application_id = create_application(client, applicant_headers)
    client.app.state.settings.max_document_size_bytes = 64

    response = upload(client, application_id, applicant_headers, b"%PDF-" + b"x" * 60)

    assert response.status_code == 413
    assert client.get(f"/api/applications/{application_id}/documents", headers=applicant_headers).json() == []
    assert list(Path(client.app.state.storage_root).iterdir()) == []


def test_corrupt_pdf_is_retained_with_explicit_error_status(client, applicant_headers):
    application_id = create_application(client, applicant_headers)

    response = upload(client, application_id, applicant_headers, b"%PDF-1.7\nnot a valid PDF structure")

    assert response.status_code == 201
    assert response.json()["extraction_status"] == "corrupt"
    assert response.json()["processing_status"] == "Upload error"
    extracted = client.get(
        f"/api/applications/{application_id}/documents/{response.json()['id']}/extracted-text",
        headers=applicant_headers,
    )
    assert extracted.json()["text"] == ""


def test_reprocess_empty_scanned_pdf_uses_private_original_and_keeps_access_control(client, applicant_headers, user_factory, monkeypatch):
    application_id = create_application(client, applicant_headers)
    scanned = pymupdf.open()
    page = scanned.new_page()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 24, 24), 0)
    page.insert_image(page.rect, pixmap=pixmap)
    payload = scanned.tobytes()
    scanned.close()

    def unavailable(*_args):
        from app.pdf_extraction import OCRUnavailableError
        raise OCRUnavailableError

    monkeypatch.setattr("app.pdf_extraction.perform_ocr", unavailable)
    uploaded = upload(client, application_id, applicant_headers, payload, category="land_document")
    assert uploaded.status_code == 201
    document_id = uploaded.json()["id"]
    assert uploaded.json()["extraction_status"] == "ocr_unavailable"
    assert uploaded.json()["extracted_text_char_count"] == 0

    user_factory(email="different-owner@example.test")
    other_headers = token_for(client, "different-owner@example.test")
    path = f"/api/applications/{application_id}/documents/{document_id}/reprocess-text"
    assert client.post(path).status_code == 401
    assert client.post(path, headers=other_headers).status_code == 404

    monkeypatch.setattr("app.pdf_extraction.perform_ocr", lambda *_args: "Recovered scanned page text")
    retried = client.post(path, headers=applicant_headers)
    assert retried.status_code == 200
    assert retried.json()["extraction_status"] == "text_extracted_with_ocr"
    assert retried.json()["extracted_text_char_count"] > 0
    extracted = client.get(
        f"/api/applications/{application_id}/documents/{document_id}/extracted-text",
        headers=applicant_headers,
    )
    assert "Recovered scanned page text" in extracted.json()["text"]
    assert "[Page 1 | OCR]" in extracted.json()["text"]
    content = client.get(
        f"/api/applications/{application_id}/documents/{document_id}/content",
        headers=applicant_headers,
    )
    assert content.content == payload


def test_reprocess_refuses_to_overwrite_existing_extracted_evidence(client, applicant_headers, pdf_bytes):
    application_id = create_application(client, applicant_headers)
    uploaded = upload(client, application_id, applicant_headers, pdf_bytes)
    document_id = uploaded.json()["id"]

    response = client.post(
        f"/api/applications/{application_id}/documents/{document_id}/reprocess-text",
        headers=applicant_headers,
    )

    assert response.status_code == 409
    assert "already stored" in response.json()["detail"]


def test_encrypted_and_scanned_pdfs_report_extraction_limits(client, applicant_headers, monkeypatch):
    application_id = create_application(client, applicant_headers)
    encrypted = pymupdf.open()
    encrypted.new_page().insert_text((72, 72), "Secret text")
    encrypted_bytes = encrypted.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    encrypted.close()
    encrypted_result = upload(client, application_id, applicant_headers, encrypted_bytes, category="faculty_list")
    assert encrypted_result.status_code == 201
    assert encrypted_result.json()["extraction_status"] == "encrypted"

    scanned = pymupdf.open()
    page = scanned.new_page()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), 0)
    page.insert_image(page.rect, pixmap=pixmap)
    scanned_bytes = scanned.tobytes()
    scanned.close()
    monkeypatch.setattr("app.pdf_extraction.perform_ocr", lambda page, dpi, pixels, timeout: "Scanned OCR sample")
    scanned_result = upload(client, application_id, applicant_headers, scanned_bytes, category="land_document")
    assert scanned_result.status_code == 201
    assert scanned_result.json()["extraction_status"] == "text_extracted_with_ocr"
    text = client.get(
        f"/api/applications/{application_id}/documents/{scanned_result.json()['id']}/extracted-text",
        headers=applicant_headers,
    ).json()["text"]
    assert "[Page 1 | OCR]" in text and "Scanned OCR sample" in text


def test_ocr_unavailable_is_reported_without_failing_upload(client, applicant_headers, monkeypatch):
    from app.pdf_extraction import OCRUnavailableError

    application_id = create_application(client, applicant_headers)
    scanned = pymupdf.open()
    page = scanned.new_page()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), 0)
    page.insert_image(page.rect, pixmap=pixmap)
    scanned_bytes = scanned.tobytes()
    scanned.close()

    def unavailable(*_args):
        raise OCRUnavailableError

    monkeypatch.setattr("app.pdf_extraction.perform_ocr", unavailable)
    response = upload(client, application_id, applicant_headers, scanned_bytes)
    assert response.status_code == 201
    assert response.json()["extraction_status"] == "ocr_unavailable"


def test_mixed_pdf_keeps_digital_and_ocr_page_provenance(client, applicant_headers, monkeypatch):
    application_id = create_application(client, applicant_headers)
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Digital page has enough readable text")
    scanned_page = doc.new_page()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), 0)
    scanned_page.insert_image(scanned_page.rect, pixmap=pixmap)
    payload = doc.tobytes()
    doc.close()
    monkeypatch.setattr("app.pdf_extraction.perform_ocr", lambda *_args: "Recognized scanned page")

    response = upload(client, application_id, applicant_headers, payload)
    assert response.status_code == 201
    extracted = client.get(
        f"/api/applications/{application_id}/documents/{response.json()['id']}/extracted-text",
        headers=applicant_headers,
    ).json()
    assert extracted["extraction_status"] == "text_extracted_with_ocr"
    assert "[Page 1 | Digital]" in extracted["text"]
    assert "[Page 2 | OCR]" in extracted["text"]


def test_pdf_page_and_ocr_page_limits_are_enforced(client, applicant_headers, monkeypatch):
    application_id = create_application(client, applicant_headers)
    two_pages = pymupdf.open()
    for _ in range(2):
        page = two_pages.new_page()
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), 0)
        page.insert_image(page.rect, pixmap=pixmap)
    payload = two_pages.tobytes()
    two_pages.close()

    client.app.state.settings.pdf_max_pages = 1
    page_limit = upload(client, application_id, applicant_headers, payload)
    assert page_limit.status_code == 201
    assert page_limit.json()["extraction_status"] == "page_limit_exceeded"

    client.app.state.settings.pdf_max_pages = 10
    client.app.state.settings.ocr_max_pages = 1
    monkeypatch.setattr("app.pdf_extraction.perform_ocr", lambda *_args: "Recognized page")
    ocr_limit = upload(client, application_id, applicant_headers, payload, category="faculty_list")
    assert ocr_limit.status_code == 201
    assert ocr_limit.json()["extraction_status"] == "ocr_page_limit_exceeded"
    extracted = client.get(
        f"/api/applications/{application_id}/documents/{ocr_limit.json()['id']}/extracted-text",
        headers=applicant_headers,
    ).json()["text"]
    assert "[Page 1 | OCR]" in extracted
    assert "[Page 2 | OCR]" not in extracted


def test_blank_pdf_is_saved_with_empty_extraction_status(client, applicant_headers):
    application_id = create_application(client, applicant_headers)
    blank = pymupdf.open()
    blank.new_page()
    blank_bytes = blank.tobytes()
    blank.close()

    response = upload(client, application_id, applicant_headers, blank_bytes)

    assert response.status_code == 201
    assert response.json()["extraction_status"] == "empty"
    assert response.json()["extracted_text_char_count"] == 0


def test_duplicate_hash_is_flagged_and_preserved(client, applicant_headers, pdf_bytes):
    first_app = create_application(client, applicant_headers, "DOC-APP-DUP-1")
    second_app = create_application(client, applicant_headers, "DOC-APP-DUP-2")

    first = upload(client, first_app, applicant_headers, pdf_bytes)
    second = upload(client, second_app, applicant_headers, pdf_bytes)

    assert first.status_code == second.status_code == 201
    assert first.json()["sha256"] == second.json()["sha256"]
    assert first.json()["duplicate_hash_detected"] is False
    assert second.json()["duplicate_hash_detected"] is True


def test_unauthorized_and_cross_applicant_document_access_is_denied(client, applicant_headers, user_factory, pdf_bytes):
    owner_app = create_application(client, applicant_headers, "DOC-APP-OWNER")
    metadata = upload(client, owner_app, applicant_headers, pdf_bytes).json()
    user_factory(email="other-uploader@example.test")
    other_headers = token_for(client, "other-uploader@example.test")
    document_base = f"/api/applications/{owner_app}/documents"

    assert client.get(document_base).status_code == 401
    assert client.get(document_base, headers=other_headers).status_code == 404
    assert client.get(
        f"{document_base}/{metadata['id']}/content", headers=other_headers
    ).status_code == 404
    assert client.get(
        f"{document_base}/{metadata['id']}/extracted-text", headers=other_headers
    ).status_code == 404
    assert client.post(
        document_base,
        data={"category": "faculty_list"},
        files={"file": ("x.pdf", pdf_bytes, "application/pdf")},
    ).status_code == 401


def test_reviewer_can_read_application_documents_but_rules_manager_cannot(client, applicant_headers, user_factory, pdf_bytes):
    application_id = create_application(client, applicant_headers)
    metadata = upload(client, application_id, applicant_headers, pdf_bytes).json()
    user_factory(email="document-reviewer@example.test", role=UserRole.OFFICIAL_REVIEWER.value)
    user_factory(email="document-admin@example.test", role=UserRole.RULES_MANAGER.value)
    reviewer_headers = token_for(client, "document-reviewer@example.test")
    manager_headers = token_for(client, "document-admin@example.test")
    document_base = f"/api/applications/{application_id}/documents"

    assert client.get(document_base, headers=reviewer_headers).status_code == 200
    assert client.get(f"{document_base}/{metadata['id']}/content", headers=reviewer_headers).status_code == 200
    assert client.get(document_base, headers=manager_headers).status_code == 403
    assert client.get(f"{document_base}/{metadata['id']}/content", headers=manager_headers).status_code == 403


def test_duplicate_category_conflict_removes_uncommitted_file(client, applicant_headers, pdf_bytes):
    application_id = create_application(client, applicant_headers)
    assert upload(client, application_id, applicant_headers, pdf_bytes).status_code == 201

    conflict = upload(client, application_id, applicant_headers, pdf_bytes, category="fire_safety")

    assert conflict.status_code == 409
    documents = client.get(f"/api/applications/{application_id}/documents", headers=applicant_headers).json()
    assert len(documents) == 1
    assert len(list(Path(client.app.state.storage_root).glob("*.pdf"))) == 1


def test_legacy_metadata_without_stored_file_returns_not_found(client, applicant_headers):
    application_id = create_application(client, applicant_headers)
    with client.app.state.session_factory() as session:  # type: Session
        session.add(
            DocumentMetadata(
                application_id=application_id,
                category="fire_safety",
                filename="legacy.pdf",
                processing_status="Awaiting manual fields",
                field_source="none",
                issuer="",
                document_number="",
                institution_id_on_doc="",
            )
        )
        session.commit()
        document = session.scalar(
            select(DocumentMetadata).where(DocumentMetadata.application_id == application_id)
        )
        document_id = document.id

    response = client.get(
        f"/api/applications/{application_id}/documents/{document_id}/content",
        headers=applicant_headers,
    )
    assert response.status_code == 404


def test_storage_root_cannot_be_configured_inside_frontend_repository():
    repository = Path(__file__).resolve().parents[2]

    with pytest.raises(RuntimeError, match="outside the project repository"):
        resolve_private_storage_root(repository / "public" / "uploads")
