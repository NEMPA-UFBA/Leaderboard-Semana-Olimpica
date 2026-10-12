from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from models import Base, Equipe, Questao, Regata, Tentativa, User
from scripts.migrate_sqlite_to_neon import copy_sqlite_database


def _create_source_database(path):
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
        db.commit()
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
        "tentativas": 1,
    }
    with Session(target_engine) as db:
        question = db.execute(select(Questao)).scalar_one()
        assert question.id == 18
        assert question.imagem == b"imagem-de-teste"
        assert question.imagem_filename == "questao.png"
        assert db.execute(select(User)).scalar_one().password_hash == "bcrypt-hash"
        assert db.execute(select(Tentativa)).scalar_one().id == 22

        next_team = Equipe(nome="Equipe seguinte")
        db.add(next_team)
        db.commit()
        assert next_team.id > 12

    target_engine.dispose()


def test_copy_sqlite_refuses_a_nonempty_target(tmp_path):
    source_path = tmp_path / "source.db"
    _create_source_database(source_path)
    target_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(target_engine)

    with pytest.raises(RuntimeError, match="nao esta vazio"):
        copy_sqlite_database(source_path, target_engine)

    target_engine.dispose()
