from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.database import create_database_engine, initialize_database
from app.models import ApplicationRecord


def test_database_initialization_creates_usable_sqlite_database(tmp_path):
    database_path = tmp_path / "initialized.db"
    engine = create_database_engine(f"sqlite:///{database_path}")

    try:
        initialize_database(engine)

        assert database_path.is_file()
        expected_tables = {
            "users",
            "applications",
            "document_metadata",
            "document_extraction_records",
            "validation_findings",
            "verification_records",
            "reviewer_decisions",
            "audit_logs",
            "institutional_reference_records",
            "regulatory_sources",
            "regulatory_source_passages",
            "regulatory_rules",
            "regulatory_category_configs",
            "validation_runs",
            "validation_run_results",
            "document_corrections",
            "document_correction_extractions",
            "audit_events",
        }
        assert set(inspect(engine).get_table_names()) == expected_tables
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1

        with Session(engine) as session:
            session.add(ApplicationRecord(id="APP-DB-TEST", institution_name="Persisted"))
            session.commit()

        # Re-running initialization is additive and leaves existing rows intact.
        initialize_database(engine)
        with Session(engine) as session:
            assert session.scalar(
                select(ApplicationRecord.institution_name).where(ApplicationRecord.id == "APP-DB-TEST")
            ) == "Persisted"
    finally:
        engine.dispose()


def test_initialization_adds_owner_column_to_phase2_database_without_losing_rows(tmp_path):
    database_path = tmp_path / "phase2.db"
    engine = create_database_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE applications (id VARCHAR(64) PRIMARY KEY, "
                "institution_name VARCHAR(300) NOT NULL)"
            )
            connection.exec_driver_sql(
                "INSERT INTO applications (id, institution_name) VALUES ('APP-LEGACY', 'Legacy Demo')"
            )

        initialize_database(engine)

        columns = {column["name"] for column in inspect(engine).get_columns("applications")}
        assert "owner_user_id" in columns
        assert "is_synthetic" in columns
        with engine.connect() as connection:
            row = connection.exec_driver_sql(
                "SELECT id, institution_name, owner_user_id FROM applications WHERE id='APP-LEGACY'"
            ).one()
        assert tuple(row) == ("APP-LEGACY", "Legacy Demo", None)
    finally:
        engine.dispose()


def test_initialization_adds_phase4_document_columns_without_losing_metadata(tmp_path):
    database_path = tmp_path / "phase3-documents.db"
    engine = create_database_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE applications (id VARCHAR(64) PRIMARY KEY, "
                "institution_name VARCHAR(300) NOT NULL)"
            )
            connection.exec_driver_sql(
                "INSERT INTO applications (id, institution_name) VALUES ('APP-LEGACY-DOC', 'Legacy Institute')"
            )
            connection.exec_driver_sql(
                "CREATE TABLE document_metadata ("
                "id VARCHAR(64) PRIMARY KEY, application_id VARCHAR(64) NOT NULL, "
                "category VARCHAR(80) NOT NULL, filename VARCHAR(512), sha256 VARCHAR(64), "
                "size_bytes INTEGER, uploaded_at DATETIME, processing_status VARCHAR(80) NOT NULL, "
                "field_source VARCHAR(20) NOT NULL, issuer VARCHAR(300) NOT NULL, "
                "document_number VARCHAR(200) NOT NULL, issue_date DATE, expiry_date DATE, "
                "institution_id_on_doc VARCHAR(100) NOT NULL, created_at DATETIME NOT NULL)"
            )
            connection.exec_driver_sql(
                "INSERT INTO document_metadata (id, application_id, category, filename, sha256, "
                "size_bytes, processing_status, field_source, issuer, document_number, "
                "institution_id_on_doc, created_at) VALUES "
                "('DOC-LEGACY', 'APP-LEGACY-DOC', 'fire_safety', 'legacy.pdf', 'old-hash', 10, "
                "'Awaiting manual fields', 'none', '', '', '', CURRENT_TIMESTAMP)"
            )

        initialize_database(engine)

        columns = {column["name"] for column in inspect(engine).get_columns("document_metadata")}
        assert {"storage_key", "extracted_text", "extraction_status", "extracted_at", "duplicate_hash_detected"} <= columns
        with engine.connect() as connection:
            row = connection.exec_driver_sql(
                "SELECT id, filename, sha256, storage_key, extraction_status, duplicate_hash_detected "
                "FROM document_metadata WHERE id='DOC-LEGACY'"
            ).one()
        assert tuple(row) == ("DOC-LEGACY", "legacy.pdf", "old-hash", None, "not_processed", 0)
    finally:
        engine.dispose()


def test_initialization_adds_validation_evidence_and_reference_authorization_columns(tmp_path):
    database_path = tmp_path / "phase6-validation.db"
    engine = create_database_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE applications (id VARCHAR(64) PRIMARY KEY, institution_name VARCHAR(300) NOT NULL)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE validation_findings (id VARCHAR(64) PRIMARY KEY, application_id VARCHAR(64) NOT NULL, "
                "finding_key VARCHAR(160) NOT NULL)"
            )
            connection.exec_driver_sql(
                "INSERT INTO validation_findings (id, application_id, finding_key) "
                "VALUES ('LEGACY-FINDING', 'LEGACY-APP', 'legacy-key')"
            )
            connection.exec_driver_sql(
                "CREATE TABLE reviewer_decisions (id VARCHAR(64) PRIMARY KEY, finding_id VARCHAR(64), "
                "status VARCHAR(40) NOT NULL, created_at DATETIME NOT NULL)"
            )
            connection.exec_driver_sql(
                "INSERT INTO reviewer_decisions VALUES ('LEGACY-DECISION', 'LEGACY-FINDING', 'Resolved', CURRENT_TIMESTAMP)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE institutional_reference_records (institution_id VARCHAR(100) PRIMARY KEY, "
                "name VARCHAR(300) NOT NULL, faculty_count INTEGER NOT NULL, state VARCHAR(100) NOT NULL, "
                "source_label VARCHAR(120) NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
            )
            connection.exec_driver_sql(
                "INSERT INTO institutional_reference_records VALUES "
                "('LEGACY-REF', 'Legacy Institute', 12, 'State', 'legacy', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )

        initialize_database(engine)

        finding_columns = {column["name"] for column in inspect(engine).get_columns("validation_findings")}
        reference_columns = {
            column["name"] for column in inspect(engine).get_columns("institutional_reference_records")
        }
        assert {"rule_version", "status", "document_ids_json", "evidence_json", "resolution_type"} <= finding_columns
        assert "is_authorized" in reference_columns
        decision_columns = {column["name"] for column in inspect(engine).get_columns("reviewer_decisions")}
        assert "decision_type" in decision_columns
        run_result_columns = {column["name"] for column in inspect(engine).get_columns("validation_run_results")}
        assert "revalidation_state" in run_result_columns
        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT finding_key, status, document_ids_json FROM validation_findings WHERE id='LEGACY-FINDING'"
            ).one() == ("legacy-key", "Resolved", "[]")
            assert connection.exec_driver_sql(
                "SELECT institution_id, is_authorized FROM institutional_reference_records WHERE institution_id='LEGACY-REF'"
            ).one() == ("LEGACY-REF", 0)
    finally:
        engine.dispose()
