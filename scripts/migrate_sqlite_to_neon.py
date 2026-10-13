import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Boolean, DateTime, JSON, func, inspect, select, text
from sqlalchemy.engine import Engine

from database import DB_PATH, engine
from models import Base

TABLE_ORDER = (
    "users",
    "equipes",
    "regatas",
    "questoes",
    "tags",
    "questao_tags",
    "tentativas",
    "audit_log",
)
OPTIONAL_TABLES = {"audit_log", "tags", "questao_tags"}
REQUIRED_TABLES = set(TABLE_ORDER) - OPTIONAL_TABLES
IGNORED_TABLES = {"questao_locks", "login_sessions"}
DEFAULT_SOURCE = Path(DB_PATH)
DEFAULT_COLUMNS = {"enunciado", "must_change_password"}
SEQUENCE_TABLES = tuple(
    name for name in TABLE_ORDER if name not in {"questao_tags"}
)


def _read_source(source_path: Path) -> tuple[dict[str, int], dict[str, list[dict]]]:
    if not source_path.is_file():
        raise FileNotFoundError(f"Arquivo SQLite nao encontrado: {source_path}")

    with sqlite3.connect(source_path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Integridade do SQLite invalida: {integrity}")

        source_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        missing_tables = REQUIRED_TABLES - source_tables
        extra_tables = source_tables - set(TABLE_ORDER) - IGNORED_TABLES
        if missing_tables or extra_tables:
            raise RuntimeError(
                "O esquema SQLite nao corresponde ao esperado. "
                f"Tabelas ausentes: {sorted(missing_tables)}; "
                f"tabelas inesperadas: {sorted(extra_tables)}."
            )

        conn.row_factory = sqlite3.Row
        rows = {}
        for name in TABLE_ORDER:
            if name not in source_tables:
                rows[name] = []
                continue
            columns = {
                row[1] for row in conn.execute(f'PRAGMA table_info("{name}")')
            }
            order_by = "id" if "id" in columns else "questao_id, tag_id"
            rows[name] = [
                dict(row)
                for row in conn.execute(
                    f'SELECT * FROM "{name}" ORDER BY {order_by}'
                )
            ]

    counts = {name: len(rows[name]) for name in TABLE_ORDER}
    return counts, rows


def _prepare_row(table_name: str, row: dict, target_table) -> dict:
    target_columns = set(target_table.c.keys())
    source_columns = set(row)
    missing_columns = target_columns - source_columns
    unexpected_columns = source_columns - target_columns
    if unexpected_columns or missing_columns - DEFAULT_COLUMNS:
        raise RuntimeError(
            f"Colunas incompatíveis em {table_name}. "
            f"Ausentes: {sorted(missing_columns)}; "
            f"inesperadas: {sorted(unexpected_columns)}."
        )

    prepared = {}
    for name, value in row.items():
        column_type = target_table.c[name].type
        if value is not None and isinstance(column_type, Boolean):
            value = bool(value)
        elif value is not None and isinstance(column_type, DateTime):
            if isinstance(value, str):
                value = datetime.fromisoformat(value)
            if column_type.timezone and value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            elif column_type.timezone:
                value = value.astimezone(timezone.utc)
            elif value.tzinfo is not None:
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
        elif value is not None and isinstance(column_type, JSON):
            value = json.loads(value) if isinstance(value, str) else value
        prepared[name] = value

    if "enunciado" in missing_columns:
        prepared["enunciado"] = ""
    if "must_change_password" in missing_columns:
        prepared["must_change_password"] = False
    return prepared


def _reset_postgres_sequences(connection, table_names: tuple[str, ...]) -> None:
    for name in table_names:
        sequence = connection.execute(
            text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
            {"table_name": name},
        ).scalar_one()
        if sequence is None:
            raise RuntimeError(f"Nao foi encontrada a sequence de {name}.")

        table = Base.metadata.tables[name]
        maximum_id = connection.execute(select(func.max(table.c.id))).scalar_one()
        value = maximum_id if maximum_id is not None else 1
        called = maximum_id is not None
        connection.execute(
            text(
                "SELECT setval(CAST(:sequence AS regclass), :value, :called)"
            ),
            {"sequence": sequence, "value": value, "called": called},
        )


def copy_sqlite_database(source_path: Path, target_engine: Engine) -> dict[str, int]:
    source_counts, source_rows = _read_source(source_path)

    with target_engine.begin() as connection:
        existing_tables = inspect(connection).get_table_names()
        if existing_tables:
            raise RuntimeError(
                "O banco de destino nao esta vazio; nenhuma alteracao foi feita. "
                f"Tabelas encontradas: {sorted(existing_tables)}."
            )

        Base.metadata.create_all(bind=connection)
        for name in TABLE_ORDER:
            table = Base.metadata.tables[name]
            prepared_rows = [
                _prepare_row(name, row, table) for row in source_rows[name]
            ]
            if prepared_rows:
                connection.execute(table.insert(), prepared_rows)

        if target_engine.dialect.name == "postgresql":
            _reset_postgres_sequences(connection, SEQUENCE_TABLES)

        target_counts = {
            name: connection.execute(
                select(func.count()).select_from(Base.metadata.tables[name])
            ).scalar_one()
            for name in TABLE_ORDER
        }
        if target_counts != source_counts:
            raise RuntimeError(
                "A verificacao de contagens falhou; a transacao sera revertida. "
                f"Origem: {source_counts}; destino: {target_counts}."
            )

    return source_counts


def _target_tables(target_engine: Engine) -> list[str]:
    with target_engine.connect() as connection:
        if target_engine.dialect.name == "postgresql":
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        tables = inspect(connection).get_table_names()
        connection.rollback()
    return tables


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copia data.db para um banco PostgreSQL vazio."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Executa a copia. Sem esta opcao, apenas valida e mostra uma previa.",
    )
    parser.add_argument(
        "--confirm-test-branch",
        action="store_true",
        help="Confirma que DATABASE_URL aponta para uma branch Neon de teste.",
    )
    args = parser.parse_args()

    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "DATABASE_URL nao aponta para PostgreSQL; confira o .env."
        )

    source_counts, _ = _read_source(args.source)
    target_tables = _target_tables(engine)
    print(f"Arquivo de origem: {args.source}")
    print(f"Contagens a importar: {source_counts}")
    print(f"Tabelas no destino: {target_tables}")

    if target_tables:
        raise RuntimeError(
            "O destino nao esta vazio. A importacao foi bloqueada sem alterar dados."
        )
    if not args.apply:
        print("Previa concluida; nenhum dado foi alterado.")
        print("Para importar, use --apply --confirm-test-branch.")
        return
    if not args.confirm_test_branch:
        raise RuntimeError(
            "Confirme que DATABASE_URL aponta para a branch de teste "
            "usando --confirm-test-branch."
        )

    counts = copy_sqlite_database(args.source, engine)
    print(f"Importacao concluida e verificada: {counts}")


if __name__ == "__main__":
    main()
