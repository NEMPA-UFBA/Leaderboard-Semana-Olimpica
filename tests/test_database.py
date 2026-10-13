import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import database
from auth import hash_password, verify_password
from models import Base, User


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgres://user:pass@host/db", "postgresql+psycopg2://user:pass@host/db"),
        (
            "postgresql://user:pass@host/db",
            "postgresql+psycopg2://user:pass@host/db",
        ),
        (
            "postgresql+psycopg2://user:pass@host/db",
            "postgresql+psycopg2://user:pass@host/db",
        ),
        ("sqlite:///data.db", "sqlite:///data.db"),
    ],
)
def test_normalize_database_url_uses_installed_postgres_driver(url, expected):
    assert database._normalize_database_url(url) == expected


@pytest.fixture
def isolated_database(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(
        database, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False)
    )
    monkeypatch.setattr(database, "_initialized", False)
    yield engine
    engine.dispose()


def test_init_db_requires_secret_and_can_retry(isolated_database, monkeypatch):
    monkeypatch.setattr(database, "_get_initial_admin_password", lambda: None)

    with pytest.raises(RuntimeError, match="ADMIN_INITIAL_PASSWORD"):
        database.init_db()

    assert database._initialized is False

    initial_password = "test-bootstrap-secret-123"
    monkeypatch.setattr(
        database, "_get_initial_admin_password", lambda: initial_password
    )
    database.init_db()

    with database.SessionLocal() as db:
        admin = db.query(User).filter_by(username="admin").one()
        assert verify_password(initial_password, admin.password_hash)
        assert admin.must_change_password is True


def test_init_db_requires_legacy_default_admin_to_change_password(
    isolated_database, monkeypatch
):
    Base.metadata.create_all(bind=isolated_database)
    with database.SessionLocal() as db:
        db.add(
            User(
                username="admin",
                password_hash=hash_password("admin"),
                role="admin",
                must_change_password=False,
            )
        )
        db.commit()

    monkeypatch.setattr(
        database,
        "_get_initial_admin_password",
        lambda: pytest.fail("Existing admin must not need a bootstrap secret."),
    )
    database.init_db()

    with database.SessionLocal() as db:
        admin = db.query(User).filter_by(username="admin").one()
        assert admin.must_change_password is True


def test_migrate_existing_users_table_adds_password_change_flag(
    isolated_database,
):
    with isolated_database.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE users ("
                "id INTEGER PRIMARY KEY, "
                "username VARCHAR(50) NOT NULL, "
                "password_hash VARCHAR(128) NOT NULL, "
                "role VARCHAR(10) NOT NULL, "
                "created_at DATETIME)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO users (username, password_hash, role) "
                "VALUES ('existing-judge', 'hash', 'juiz')"
            )
        )

    database._ensure_user_password_migration()

    columns = {
        column["name"]: column
        for column in inspect(isolated_database).get_columns("users")
    }
    assert columns["must_change_password"]["nullable"] is False
    with isolated_database.connect() as conn:
        value = conn.execute(
            text("SELECT must_change_password FROM users WHERE username = 'existing-judge'")
        ).scalar_one()
    assert value == 0
