import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from dotenv import load_dotenv

# Carrega as variáveis do .env (se o arquivo existir)
load_dotenv()

# Caminho de segurança (fallback) para o SQLite local
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")
FALLBACK_URL = f"sqlite:///{DB_PATH}"

# 1. Tenta pegar a URL do .env
DATABASE_URL = os.environ.get("DATABASE_URL")

# 2. Se não achar, tenta pegar dos Secrets (útil para quando for pro Streamlit Cloud)
if not DATABASE_URL:
    try:
        DATABASE_URL = st.secrets.get("DATABASE_URL")
    except StreamlitSecretNotFoundError:
        DATABASE_URL = None

# 3. Se não achar em lugar nenhum, usa o banco local
if not DATABASE_URL:
    DATABASE_URL = FALLBACK_URL

def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace(
            "postgres://", "postgresql+psycopg2://", 1
        )
    if database_url.startswith("postgresql://"):
        return database_url.replace(
            "postgresql://", "postgresql+psycopg2://", 1
        )
    return database_url


DATABASE_URL = _normalize_database_url(DATABASE_URL)

# O argumento "check_same_thread" só existe no SQLite. Se for Postgres, ele quebra.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


_initialized = False


def _get_initial_admin_password() -> str | None:
    password = os.environ.get("ADMIN_INITIAL_PASSWORD")
    if password:
        return password

    try:
        return st.secrets.get("ADMIN_INITIAL_PASSWORD")
    except StreamlitSecretNotFoundError:
        return None


def _ensure_user_password_migration():
    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    if "must_change_password" not in columns:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN "
                "must_change_password BOOLEAN NOT NULL DEFAULT 0"
            ))


def init_db():
    """Create tables and bootstrap an admin account when needed."""
    global _initialized
    if _initialized:
        return

    # Import here to avoid circular imports
    from models import User
    from auth import hash_password, password_validation_error, verify_password

    Base.metadata.create_all(bind=engine)
    _ensure_user_password_migration()

    # Migrate: add enunciado column if missing (for existing databases)
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns("questoes")]
    if "enunciado" not in columns:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE questoes ADD COLUMN enunciado TEXT DEFAULT ''"))
            conn.commit()

    # Migrate: remove FK constraint on juiz_id in tentativas (for existing databases)
    if "tentativas" in inspector.get_table_names():
        fks = inspector.get_foreign_keys("tentativas")
        has_juiz_fk = any(
            fk.get("referred_table") == "users" for fk in fks
        )
        if has_juiz_fk:
            with engine.connect() as conn:
                conn.execute(text(
                    "CREATE TABLE tentativas_new ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "equipe_id INTEGER NOT NULL REFERENCES equipes(id), "
                    "questao_id INTEGER NOT NULL REFERENCES questoes(id), "
                    "numero INTEGER NOT NULL, "
                    "acertou BOOLEAN NOT NULL, "
                    "pontos INTEGER NOT NULL DEFAULT 0, "
                    "juiz_id INTEGER NOT NULL, "
                    "created_at DATETIME)"
                ))
                conn.execute(text(
                    "INSERT INTO tentativas_new SELECT * FROM tentativas"
                ))
                conn.execute(text("DROP TABLE tentativas"))
                conn.execute(text("ALTER TABLE tentativas_new RENAME TO tentativas"))
                conn.commit()

    # Create default admin if not exists
    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").first()
        if not admin:
            initial_password = _get_initial_admin_password()
            if not initial_password:
                raise RuntimeError(
                    "Configure ADMIN_INITIAL_PASSWORD in Streamlit Secrets "
                    "or the environment before creating the initial admin."
                )
            if not isinstance(initial_password, str):
                raise RuntimeError("ADMIN_INITIAL_PASSWORD must be a string.")
            password_error = password_validation_error(initial_password)
            if password_error:
                raise RuntimeError(
                    f"Invalid ADMIN_INITIAL_PASSWORD: {password_error}"
                )
            admin = User(
                username="admin",
                password_hash=hash_password(initial_password),
                role="admin",
                must_change_password=True,
            )
            db.add(admin)
            db.commit()
        elif admin.role != "admin":
            raise RuntimeError(
                "The reserved username 'admin' exists but does not have the admin role."
            )
        elif not admin.must_change_password and verify_password(
            "admin", admin.password_hash
        ):
            admin.must_change_password = True
            db.commit()
    finally:
        db.close()

    _initialized = True


def get_db():
    """Create a fresh session. Ensures DB is initialized first."""
    init_db()
    db = SessionLocal()
    return db
