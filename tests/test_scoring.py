import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import AuditLog, User, Equipe, Regata, Questao, Tentativa
from scoring import (
    calcular_leaderboard,
    corrigir_tentativa,
    excluir_tentativa,
    registrar_tentativa,
)
from question_locking import reservar_questao


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


def test_reserva_impede_outra_sessao_de_registrar_tentativa(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").one()
    questao = db.query(Questao).one()
    juiz1 = db.query(User).one()
    juiz2 = User(username="juiz2", password_hash="hash", role="juiz")
    db.add(juiz2)
    db.commit()
    reservar_questao(db, questao.id, juiz1.id, "Juiz Um", "sessao-1")

    result = registrar_tentativa(
        db,
        equipe.id,
        questao.id,
        False,
        juiz2.id,
        "sessao-2",
    )

    assert "reservada por Juiz Um" in result["erro"]
    assert db.query(Tentativa).count() == 0


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


def test_leaderboard_sem_tentativas_usa_ordem_grega(db):
    db.add_all(
        [
            Equipe(nome="Time Gama"),
            Equipe(nome="Time Alfa"),
            Equipe(nome="Time Beta"),
        ]
    )
    db.commit()

    ranking = calcular_leaderboard(db)

    assert [item["equipe"] for item in ranking[:3]] == [
        "Time Alfa",
        "Time Beta",
        "Time Gama",
    ]
    assert all(item["pontos"] == 0 for item in ranking)


def test_excluir_unica_tentativa(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").first()
    questao = db.query(Questao).first()
    juiz = db.query(User).first()

    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    tentativa = db.query(Tentativa).first()

    excluir_tentativa(db, tentativa.id, juiz.id, juiz.role)

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
    excluir_tentativa(db, primeira.id, juiz.id, juiz.role)

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
    excluir_tentativa(db, segunda.id, juiz.id, juiz.role)

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
    excluir_tentativa(db, primeira.id, juiz.id, juiz.role)

    assert next(r for r in calcular_leaderboard(db) if r["equipe"] == equipe.nome)["pontos"] == 100


def test_excluir_tentativa_inexistente_informa_erro(db):
    with pytest.raises(LookupError, match="Tentativa nao encontrada"):
        excluir_tentativa(db, 999, 1, "juiz")


def test_corrigir_tentativa_registra_auditoria(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").first()
    questao = db.query(Questao).first()
    juiz = db.query(User).first()
    outro_juiz = User(
        username="juiz2",
        password_hash="hash",
        role="juiz",
        nome="Juiza Dois",
    )
    db.add(outro_juiz)
    db.commit()
    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    tentativa = db.query(Tentativa).one()

    result = corrigir_tentativa(
        db, tentativa.id, outro_juiz.id, outro_juiz.role, True
    )

    registro = db.query(AuditLog).one()
    assert result == {"numero": 1, "acertou": True, "pontos": 100}
    assert registro.ator_id == outro_juiz.id
    assert registro.ator_role == "juiz"
    assert tentativa.juiz_id == juiz.id
    assert registro.equipe_id == equipe.id
    assert registro.tentativa_id == tentativa.id
    assert registro.acao == "correcao"
    assert registro.detalhes == {
        "antes": {"numero": 1, "acertou": False, "pontos": 0},
        "depois": {"numero": 1, "acertou": True, "pontos": 100},
    }


def test_correction_can_set_wrong_without_toggling_and_audits_change(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").one()
    questao = db.query(Questao).one()
    juiz = db.query(User).one()
    registrar_tentativa(db, equipe.id, questao.id, True, juiz.id)
    tentativa = db.query(Tentativa).one()

    result = corrigir_tentativa(
        db, tentativa.id, juiz.id, juiz.role, False
    )

    assert result == {"numero": 1, "acertou": False, "pontos": 0}
    assert db.query(AuditLog).one().detalhes == {
        "antes": {"numero": 1, "acertou": True, "pontos": 100},
        "depois": {"numero": 1, "acertou": False, "pontos": 0},
    }


def test_correction_with_same_result_does_not_create_audit_entry(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").one()
    questao = db.query(Questao).one()
    juiz = db.query(User).one()
    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    tentativa = db.query(Tentativa).one()

    result = corrigir_tentativa(
        db, tentativa.id, juiz.id, juiz.role, False
    )

    assert result == {"numero": 1, "acertou": False, "pontos": 0}
    assert db.query(AuditLog).count() == 0


def test_reserva_impede_outra_sessao_de_corrigir_tentativa(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").one()
    questao = db.query(Questao).one()
    juiz1 = db.query(User).one()
    juiz2 = User(username="juiz2", password_hash="hash", role="juiz")
    db.add(juiz2)
    db.commit()
    registrar_tentativa(db, equipe.id, questao.id, False, juiz1.id)
    tentativa = db.query(Tentativa).one()
    reservar_questao(db, questao.id, juiz1.id, "Juiz Um", "sessao-1")

    result = corrigir_tentativa(
        db, tentativa.id, juiz2.id, juiz2.role, True, "sessao-2"
    )

    assert "reservada por Juiz Um" in result["erro"]
    assert db.query(Tentativa).one().acertou is False
    assert db.query(AuditLog).count() == 0


def test_corrigir_como_certa_bloqueia_se_houver_tentativa_posterior(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").first()
    questao = db.query(Questao).first()
    juiz = db.query(User).first()
    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    registrar_tentativa(db, equipe.id, questao.id, False, juiz.id)
    primeira = db.query(Tentativa).filter_by(numero=1).one()

    result = corrigir_tentativa(db, primeira.id, juiz.id, juiz.role, True)

    assert "erro" in result
    assert db.query(AuditLog).count() == 0
    assert db.query(Tentativa).filter_by(numero=1).one().acertou is False


def test_excluir_tentativa_registra_auditoria(db):
    equipe = db.query(Equipe).filter_by(nome="Equipe A").first()
    questao = db.query(Questao).first()
    juiz = db.query(User).first()
    registrar_tentativa(db, equipe.id, questao.id, True, juiz.id)
    tentativa = db.query(Tentativa).one()

    excluir_tentativa(db, tentativa.id, juiz.id, juiz.role)

    registro = db.query(AuditLog).one()
    assert registro.ator_id == juiz.id
    assert registro.equipe_id == equipe.id
    assert registro.tentativa_id == tentativa.id
    assert registro.acao == "exclusao"
    assert registro.detalhes == {
        "excluida": {"numero": 1, "acertou": True, "pontos": 100}
    }
