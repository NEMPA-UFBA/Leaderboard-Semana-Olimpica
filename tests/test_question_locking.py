from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import QuestaoLock, Regata, Questao
from question_locking import (
    RESERVA_DURACAO,
    liberar_reserva_ao_sair_da_tela,
    liberar_reserva_questao,
    renovar_reserva_questao,
    reservar_questao,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    regata = Regata(nome="Regata teste")
    session.add(regata)
    session.flush()
    questao = Questao(
        regata_id=regata.id,
        nivel="facil",
        enunciado="Questao teste",
    )
    session.add(questao)
    session.commit()
    yield session, questao.id
    session.close()
    engine.dispose()


def test_reserva_bloqueia_outra_sessao_e_libera_ao_sair(db):
    session, questao_id = db

    primeira = reservar_questao(
        session, questao_id, 1, "Juiza Um", "sessao-1"
    )
    segunda = reservar_questao(
        session, questao_id, 2, "Juiza Dois", "sessao-2"
    )

    assert primeira["reservada"] is True
    assert segunda["reservada"] is False
    assert segunda["nome_ator"] == "Juiza Um"

    assert liberar_reserva_questao(session, questao_id, "sessao-1") is True
    segunda = reservar_questao(
        session, questao_id, 2, "Juiza Dois", "sessao-2"
    )
    assert segunda["reservada"] is True


def test_juiz_pode_assumir_reserva_de_uma_sessao_anterior(db):
    session, questao_id = db

    primeira = reservar_questao(
        session, questao_id, 1, "Juiz Um", "sessao-antiga"
    )
    assumida = reservar_questao(
        session, questao_id, 1, "Juiz Um", "sessao-atual"
    )

    assert primeira["reservada"] is True
    assert assumida["reservada"] is True
    assert renovar_reserva_questao(session, questao_id, "sessao-antiga") is False
    assert renovar_reserva_questao(session, questao_id, "sessao-atual") is True


def test_reserva_pode_ser_renovada_e_tem_expiracao_curta(db):
    session, questao_id = db
    reserva = reservar_questao(
        session, questao_id, 1, "Juiza Um", "sessao-1"
    )
    assert reserva["expires_at"] > datetime.now(timezone.utc)
    assert renovar_reserva_questao(session, questao_id, "sessao-1") is True
    assert renovar_reserva_questao(session, questao_id, "sessao-2") is False
    assert RESERVA_DURACAO == timedelta(seconds=90)


def test_sessao_pode_assumir_reserva_expirada(db):
    session, questao_id = db
    session.add(
        QuestaoLock(
            questao_id=questao_id,
            session_token="sessao-expirada",
            ator_id=1,
            nome_ator="Juiza Antiga",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            updated_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        )
    )
    session.commit()

    reserva = reservar_questao(
        session, questao_id, 2, "Juiza Nova", "sessao-nova"
    )

    assert reserva["reservada"] is True
    assert reserva["nome_ator"] == "Juiza Nova"


def test_sair_da_tela_libera_reserva_e_limpa_estado(db):
    session, questao_id = db
    reservar_questao(session, questao_id, 1, "Juiza Um", "sessao-1")
    estado = {
        "question_lock_id": questao_id,
        "question_lock_session": "sessao-1",
        "question_lock_owned": True,
        "question_lock_owner": "Juiza Um",
    }

    liberar_reserva_ao_sair_da_tela(session, estado)

    assert "question_lock_id" not in estado
    assert estado["question_lock_session"] == "sessao-1"
    assert session.query(QuestaoLock).count() == 0
    assert reservar_questao(
        session, questao_id, 2, "Juiza Dois", "sessao-2"
    )["reservada"] is True
