from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from models import AuditLog, Base, Equipe, Questao, Regata, Tag, Tentativa, User
from scripts.migrate_sqlite_to_neon import copy_sqlite_database


def _create_source_database(path, include_audit=True, include_tags=True):
    source_engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(source_engine)
    with Session(source_engine) as db:
        judge = User(
            id=8,
            username="judge-test",
            password_hash="bcrypt-hash",
            role="juiz",
            must_change_password=True,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        team = Equipe(id=12, nome="Equipe teste")
        regatta = Regata(id=15, nome="Regata teste", ativa=True)
        question = Questao(
            id=18,
            regata_id=regatta.id,
            nivel="facil",
            enunciado="Questao com imagem",
            imagem=b"imagem-de-teste",
            imagem_filename="questao.png",
        )
        question.tags = [Tag(nome="Combinatória", categoria="área")]
        attempt = Tentativa(
            id=22,
            equipe_id=team.id,
            questao_id=question.id,
            numero=1,
            acertou=True,
            pontos=100,
            juiz_id=judge.id,
        )
        db.add_all([judge, team, regatta, question, attempt])
        if include_audit:
            db.add(
                AuditLog(
                    ator_id=judge.id,
                    ator_role="juiz",
                    equipe_id=team.id,
                    tentativa_id=attempt.id,
                    acao="correcao",
                    detalhes={
                        "antes": {"numero": 1, "acertou": False, "pontos": 0},
                        "depois": {"numero": 1, "acertou": True, "pontos": 100},
                    },
                )
            )
        db.commit()
    if not include_audit:
        AuditLog.__table__.drop(source_engine)
    if not include_tags:
        Base.metadata.tables["questao_tags"].drop(source_engine)
        Base.metadata.tables["tags"].drop(source_engine)
    source_engine.dispose()


def test_copy_sqlite_preserves_rows_images_and_ids(tmp_path):
    source_path = tmp_path / "source.db"
    _create_source_database(source_path)
    target_engine = create_engine("sqlite:///:memory:")

    counts = copy_sqlite_database(source_path, target_engine)

    assert counts == {
        "users": 1,
        "equipes": 1,
        "regatas": 1,
        "questoes": 1,
        "tags": 1,
        "questao_tags": 1,
        "tentativas": 1,
        "audit_log": 1,
    }
    with Session(target_engine) as db:
        question = db.execute(select(Questao)).scalar_one()
        assert question.id == 18
        assert question.imagem == b"imagem-de-teste"
        assert question.imagem_filename == "questao.png"
        assert [tag.nome for tag in question.tags] == ["Combinatória"]
        assert db.execute(select(User)).scalar_one().password_hash == "bcrypt-hash"
        assert db.execute(select(Tentativa)).scalar_one().id == 22
        assert db.execute(select(AuditLog)).scalar_one().detalhes == {
            "antes": {"numero": 1, "acertou": False, "pontos": 0},
            "depois": {"numero": 1, "acertou": True, "pontos": 100},
        }

        next_team = Equipe(nome="Equipe seguinte")
        db.add(next_team)
        db.commit()
        assert next_team.id > 12

    target_engine.dispose()


def test_copy_sqlite_without_audit_table_creates_empty_audit_table(tmp_path):
    source_path = tmp_path / "legacy-source.db"
    _create_source_database(
        source_path, include_audit=False, include_tags=False
    )
    target_engine = create_engine("sqlite:///:memory:")

    counts = copy_sqlite_database(source_path, target_engine)

    assert counts["audit_log"] == 0
    assert counts["tags"] == 0
    assert counts["questao_tags"] == 0
    with Session(target_engine) as db:
        assert db.query(AuditLog).count() == 0

    target_engine.dispose()


def test_copy_sqlite_refuses_a_nonempty_target(tmp_path):
    source_path = tmp_path / "source.db"
    _create_source_database(source_path)
    target_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(target_engine)

    with pytest.raises(RuntimeError, match="nao esta vazio"):
        copy_sqlite_database(source_path, target_engine)

    target_engine.dispose()
