from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
import question_tags
from models import Questao, Regata, Tag, User
from question_tags import atualizar_tags_questao, garantir_tags_padrao


def test_default_tags_are_seeded_and_legacy_difficulty_is_migrated():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    regata = Regata(nome="Regata")
    session.add(regata)
    session.flush()
    questao = Questao(regata_id=regata.id, nivel="medio", enunciado="Teste")
    session.add(questao)
    session.commit()

    garantir_tags_padrao(session)
    garantir_tags_padrao(session)

    assert session.query(Tag).count() == 10
    assert [(tag.nome, tag.categoria) for tag in questao.tags] == [
        ("Médio", "dificuldade")
    ]

    session.close()
    engine.dispose()


def test_question_tags_use_the_questao_relationship_model(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    regata = Regata(nome="Regata")
    session.add(regata)
    session.flush()
    questao = Questao(regata_id=regata.id, nivel="facil", enunciado="Teste")
    session.add(questao)
    session.commit()
    garantir_tags_padrao(session)
    monkeypatch.setattr(question_tags, "Tag", User, raising=False)

    atualizar_tags_questao(
        session,
        questao,
        "dificil",
        ["Matemática", "Combinatória"],
        ["Invariantes"],
    )

    assert questao.nivel == "dificil"
    assert {(tag.nome, tag.categoria) for tag in questao.tags} == {
        ("Difícil", "dificuldade"),
        ("Matemática", "disciplina"),
        ("Combinatória", "área"),
        ("Invariantes", "personalizada"),
    }

    session.close()
    engine.dispose()
