import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import User, Equipe, Regata, Questao, Tentativa
from scoring import registrar_tentativa, calcular_leaderboard, excluir_tentativa


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed data
    juiz = User(username="juiz1", password_hash="hash", role="juiz")
    equipe_a = Equipe(nome="Equipe A")
    equipe_b = Equipe(nome="Equipe B")
    regata = Regata(nome="Regata 1", ativa=True)
    session.add_all([juiz, equipe_a, equipe_b, regata])
    session.commit()

    questao = Questao(
        regata_id=regata.id, nivel="facil", enunciado="Questao teste", imagem=b"img", imagem_filename="q.png"
    )
    session.add(questao)
    session.commit()

    yield session
    session.close()


def test_acerto_primeira_tentativa(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").first()
    questao = db.query(Questao).first()
    juiz = db.query(User).first()

    result = registrar_tentativa(db, equipe.id, questao.id, True, juiz.id)
    assert result["numero"] == 1
    assert result["pontos"] == 100
    assert result["acertou"] is True


def test_acerto_segunda_tentativa(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").first()
    questao = db.query(Questao).first()
    juiz = db.query(User).first()

    # 1st attempt: wrong
    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    # 2nd attempt: correct
    result = registrar_tentativa(db, equipe.id, questao.id, True, juiz.id)
    assert result["numero"] == 2
    assert result["pontos"] == 80


def test_acerto_terceira_tentativa(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").first()
    questao = db.query(Questao).first()
    juiz = db.query(User).first()

    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    result = registrar_tentativa(db, equipe.id, questao.id, True, juiz.id)
    assert result["numero"] == 3
    assert result["pontos"] == 50


def test_bloqueia_apos_3_tentativas(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").first()
    questao = db.query(Questao).first()
    juiz = db.query(User).first()

    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)

    result = registrar_tentativa(db, equipe.id, questao.id, True, juiz.id)
    assert result["erro"] == "Equipe ja esgotou as 3 tentativas nesta questao."


def test_bloqueia_apos_acerto(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").first()
    questao = db.query(Questao).first()
    juiz = db.query(User).first()

    registrar_tentativa(db, equipe.id, questao.id, True, juiz.id)
    result = registrar_tentativa(db, equipe.id, questao.id, True, juiz.id)
    assert result["erro"] == "Equipe ja acertou esta questao."


def test_erro_terceira_tentativa_zero_pontos(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").first()
    questao = db.query(Questao).first()
    juiz = db.query(User).first()

    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    result = registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    assert result["numero"] == 3
    assert result["pontos"] == 0
    assert result["acertou"] is False


def test_calcular_leaderboard(db):
    equipe_a = db.query(Equipe).filter_by(nome="Equipe A").first()
    equipe_b = db.query(Equipe).filter_by(nome="Equipe B").first()
    questao = db.query(Questao).first()
    juiz = db.query(User).first()
    regata = db.query(Regata).first()

    # Equipe A: acerta de primeira (100 pts)
    registrar_tentativa(db, equipe_a.id, questao.id, True, juiz.id)
    # Equipe B: erra, depois acerta (80 pts)
    registrar_tentativa(db, equipe_b.id, questao.id, False, juiz.id)
    registrar_tentativa(db, equipe_b.id, questao.id, True, juiz.id)

    ranking = calcular_leaderboard(db)
    assert len(ranking) == 2
    assert ranking[0]["equipe"] == "Equipe A"
    assert ranking[0]["pontos"] == 100
    assert ranking[1]["equipe"] == "Equipe B"
    assert ranking[1]["pontos"] == 80


def test_excluir_unica_tentativa(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").first()
    questao = db.query(Questao).first()
    juiz = db.query(User).first()

    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    tentativa = db.query(Tentativa).first()

    excluir_tentativa(db, tentativa.id)

    restantes = db.query(Tentativa).filter_by(equipe_id=equipe.id, questao_id=questao.id).all()
    assert restantes == []


def test_excluir_primeira_renumera_e_recalcula_pontos(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").first()
    questao = db.query(Questao).first()
    juiz = db.query(User).first()

    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    registrar_tentativa(db, equipe.id, questao.id, True, juiz.id)

    primeira = db.query(Tentativa).filter_by(
        equipe_id=equipe.id, questao_id=questao.id, numero=1
    ).first()
    excluir_tentativa(db, primeira.id)

    restantes = (
        db.query(Tentativa)
        .filter_by(equipe_id=equipe.id, questao_id=questao.id)
        .order_by(Tentativa.numero)
        .all()
    )
    assert [(t.numero, t.acertou, t.pontos) for t in restantes] == [
        (1, False, 0),
        (2, True, 80),
    ]


def test_excluir_tentativa_do_meio_renumera(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").first()
    questao = db.query(Questao).first()
    juiz = db.query(User).first()

    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    registrar_tentativa(db, equipe.id, questao.id, True, juiz.id)

    segunda = db.query(Tentativa).filter_by(
        equipe_id=equipe.id, questao_id=questao.id, numero=2
    ).first()
    excluir_tentativa(db, segunda.id)

    restantes = (
        db.query(Tentativa)
        .filter_by(equipe_id=equipe.id, questao_id=questao.id)
        .order_by(Tentativa.numero)
        .all()
    )
    assert [(t.numero, t.acertou, t.pontos) for t in restantes] == [
        (1, False, 0),
        (2, True, 80),
    ]


def test_excluir_tentativa_atualiza_leaderboard(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").first()
    questao = db.query(Questao).first()
    juiz = db.query(User).first()

    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    registrar_tentativa(db, equipe.id, questao.id, True, juiz.id)
    assert next(r for r in calcular_leaderboard(db) if r["equipe"] == equipe.nome)["pontos"] == 80

    primeira = db.query(Tentativa).filter_by(
        equipe_id=equipe.id, questao_id=questao.id, numero=1
    ).first()
    excluir_tentativa(db, primeira.id)

    assert next(r for r in calcular_leaderboard(db) if r["equipe"] == equipe.nome)["pontos"] == 100


def test_excluir_tentativa_inexistente_informa_erro(db):
    with pytest.raises(LookupError, match="Tentativa nao encontrada"):
        excluir_tentativa(db, 999)
