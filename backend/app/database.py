"""SQLAlchemy engine, sessions, and database initialization."""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base for future SQLAlchemy models; no application models are defined yet."""


def create_database_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine, with SQLite's thread option when applicable."""
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create sessions that are committed explicitly by API handlers."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Yield a request-scoped session and always close it."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def initialize_database(engine: Engine) -> None:
    """Create missing tables and apply additive document ownership/extraction migrations."""
    # Import registers all mapped classes on Base.metadata before create_all.
    from app import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    columns = {column["name"] for column in inspect(engine).get_columns("applications")}
    with engine.begin() as connection:
        if "owner_user_id" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE applications ADD COLUMN owner_user_id VARCHAR(36) "
                "REFERENCES users (id) ON DELETE SET NULL"
            )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_applications_owner_user_id "
            "ON applications (owner_user_id)"
        )
        document_columns = {
            column["name"]
            for column in inspect(connection).get_columns("document_metadata")
        }
        document_migrations = {
            "storage_key": "VARCHAR(64)",
            "extracted_text": "TEXT",
            "extraction_status": "VARCHAR(80) NOT NULL DEFAULT 'not_processed'",
            "extracted_at": "DATETIME",
            "duplicate_hash_detected": "BOOLEAN NOT NULL DEFAULT 0",
        }
        for column_name, column_definition in document_migrations.items():
            if column_name not in document_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE document_metadata ADD COLUMN {column_name} {column_definition}"
                )
        finding_columns = {column["name"] for column in inspect(connection).get_columns("validation_findings")}
        finding_migrations = {
            "rule_version": "INTEGER",
            "status": "VARCHAR(40) NOT NULL DEFAULT 'Open'",
            "document_ids_json": "JSON NOT NULL DEFAULT '[]'",
            "evidence_json": "JSON NOT NULL DEFAULT '[]'",
            "resolution_type": "VARCHAR(40)",
        }
        for column_name, column_definition in finding_migrations.items():
            if column_name not in finding_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE validation_findings ADD COLUMN {column_name} {column_definition}"
                )
        run_result_columns = {column["name"] for column in inspect(connection).get_columns("validation_run_results")}
        if "revalidation_state" not in run_result_columns:
            connection.exec_driver_sql("ALTER TABLE validation_run_results ADD COLUMN revalidation_state VARCHAR(40)")
        decision_columns = {column["name"] for column in inspect(connection).get_columns("reviewer_decisions")}
        if "decision_type" not in decision_columns:
            connection.exec_driver_sql("ALTER TABLE reviewer_decisions ADD COLUMN decision_type VARCHAR(40)")
        application_columns = {column["name"] for column in inspect(connection).get_columns("applications")}
        if "is_synthetic" not in application_columns:
            connection.exec_driver_sql("ALTER TABLE applications ADD COLUMN is_synthetic BOOLEAN NOT NULL DEFAULT 0")
        reference_columns = {
            column["name"] for column in inspect(connection).get_columns("institutional_reference_records")
        }
        if "is_authorized" not in reference_columns:
            connection.exec_driver_sql(
                "ALTER TABLE institutional_reference_records "
                "ADD COLUMN is_authorized BOOLEAN NOT NULL DEFAULT 0"
            )
        # Preserve each finding's latest existing reviewer decision as its current status.
        connection.exec_driver_sql(
            "UPDATE validation_findings SET status = ("
            "SELECT reviewer_decisions.status FROM reviewer_decisions "
            "WHERE reviewer_decisions.finding_id = validation_findings.id "
            "ORDER BY reviewer_decisions.created_at DESC, reviewer_decisions.id DESC LIMIT 1) "
            "WHERE EXISTS (SELECT 1 FROM reviewer_decisions "
            "WHERE reviewer_decisions.finding_id = validation_findings.id)"
        )
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_document_storage_key "
            "ON document_metadata (storage_key) WHERE storage_key IS NOT NULL"
        )
