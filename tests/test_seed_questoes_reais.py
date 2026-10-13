import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Questao, Regata, Tag, User
from question_tags import NIVEIS_TAG
from scripts import seed_questoes_reais as seed


@pytest.fixture
def seed_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    yield db
    db.close()
    engine.dispose()


def _payload():
    return {
        "juizes": [{"nome": "Teste Um", "username": "teste_um"}],
        "regatas": [
            {
                "nome": "Regata Seed Teste",
                "questoes": [
                    {
                        "ordem": 1,
                        "nivel": "facil",
                        "enunciado": "Questao um",
                        "imagem": "static/q1.png",
                        "gabarito": "Resposta privada",
                        "tags": [
                            {"nome": "Matemática", "categoria": "disciplina"}
                        ],
                    },
                    {
                        "ordem": 2,
                        "nivel": "medio",
                        "enunciado": "Questao dois",
                        "imagem": None,
                        "gabarito": "Outra resposta privada",
                        "tags": [],
                    },
                ],
            }
        ],
    }


def test_seed_data_loads_private_json_and_rejects_nonsequential_questions(
    tmp_path, monkeypatch
):
    seed_file = tmp_path / "seed.json"
    monkeypatch.setattr(seed, "SEED_FILE", seed_file)
    seed_file.write_text(json.dumps(_payload()), encoding="utf-8")

    payload = seed._load_seed_data()
    assert len(payload["regatas"][0]["questoes"]) == 2

    payload["regatas"][0]["questoes"][1]["ordem"] = 3
    seed_file.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="sem lacunas"):
        seed._load_seed_data()


def test_question_seed_is_idempotent_and_keeps_question_order(seed_db):
    payload = _payload()
    images = {"static/q1.png": b"question image"}

    first = seed._seed_questions(
        seed_db, Regata, Questao, Tag, payload, images, NIVEIS_TAG
    )
    seed_db.commit()
    second = seed._seed_questions(
        seed_db, Regata, Questao, Tag, payload, images, NIVEIS_TAG
    )
    seed_db.commit()

    questions = (
        seed_db.query(Questao)
        .order_by(Questao.id)
        .all()
    )
    assert first == (1, 2)
    assert second == (0, 0)
    assert [question.enunciado for question in questions] == [
        "Questao um",
        "Questao dois",
    ]
    assert questions[0].imagem == b"question image"
    assert {tag.nome for tag in questions[0].tags} == {
        "Fácil",
        "Matemática",
    }


def test_question_seed_refuses_to_append_after_unrelated_questions(seed_db):
    regatta = Regata(nome="Regata Seed Teste", ativa=False)
    seed_db.add(regatta)
    seed_db.flush()
    seed_db.add(
        Questao(
            regata_id=regatta.id,
            nivel="facil",
            enunciado="Questao de teste nao relacionada",
        )
    )
    seed_db.commit()

    with pytest.raises(RuntimeError, match="nao corresponde ao seed"):
        seed._seed_questions(
            seed_db, Regata, Questao, Tag, _payload(),
            {"static/q1.png": b"question image"},
            NIVEIS_TAG,
        )
    seed_db.rollback()


def test_judge_seed_forces_password_change_and_skips_existing_users(seed_db):
    judges = [{"nome": "Teste Um", "username": "teste_um"}]

    created = seed._seed_judges(seed_db, User, judges, "bcrypt-hash")
    seed_db.commit()
    existing_password_hash = seed_db.query(User).one().password_hash
    rerun = seed._seed_judges(seed_db, User, judges, None)
    seed_db.commit()

    user = seed_db.query(User).one()
    assert created == (1, 0)
    assert rerun == (0, 1)
    assert user.role == "juiz"
    assert user.must_change_password is True
    assert user.password_hash == existing_password_hash
