from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import QuestaoLock, Regata, Questao
from question_locking import (
    RESERVA_DURACAO,
    liberar_reserva_ao_sair_da_tela,
    liberar_reserva_ao_trocar_equipe,
    liberar_reserva_questao,
    limpar_locks_expirados,
    obter_ou_renovar_reserva_questao,
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
    renovada, _ = renovar_reserva_questao(session, questao_id, "sessao-antiga")
    assert renovada is False
    renovada, _ = renovar_reserva_questao(session, questao_id, "sessao-atual")
    assert renovada is True


def test_reserva_pode_ser_renovada_e_tem_expiracao_curta(db):
    session, questao_id = db
    reserva = reservar_questao(
        session, questao_id, 1, "Juiza Um", "sessao-1"
    )
    assert reserva["expires_at"] > datetime.now(timezone.utc)
    renovada, novo_exp = renovar_reserva_questao(session, questao_id, "sessao-1")
    assert renovada is True
    assert novo_exp is not None
    renovada, _ = renovar_reserva_questao(session, questao_id, "sessao-2")
    assert renovada is False
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
        "judge_feedback": {"mensagem": "feedback antigo"},
        "judge_panel_context": (1, questao_id),
        "editing_attempt_id": 10,
    }

    liberar_reserva_ao_sair_da_tela(session, estado)

    assert "question_lock_id" not in estado
    assert "question_lock_session" not in estado
    assert "judge_feedback" not in estado
    assert "judge_panel_context" not in estado
    assert "editing_attempt_id" not in estado
    assert session.query(QuestaoLock).count() == 0
    assert reservar_questao(
        session, questao_id, 2, "Juiza Dois", "sessao-2"
    )["reservada"] is True


def test_trocar_equipe_libera_reserva_sem_reassumir(db):
    session, questao_id = db
    reservar_questao(session, questao_id, 1, "Juiz Um", "sessao-1")
    estado = {
        "question_lock_id": questao_id,
        "question_lock_session": "sessao-1",
        "question_lock_owned": True,
        "question_lock_owner": "Juiz Um",
    }

    liberada = liberar_reserva_ao_trocar_equipe(
        session, estado, 1, 2, questao_id, "sessao-1"
    )

    assert liberada is True
    assert estado["question_lock_id"] == questao_id
    assert estado["question_lock_owned"] is False
    assert estado["question_lock_owner"] is None
    assert session.query(QuestaoLock).count() == 0
    assert reservar_questao(
        session, questao_id, 2, "Juiza Dois", "sessao-2"
    )["reservada"] is True


def test_trocar_equipe_sem_mudar_equipe_preserva_reserva(db):
    session, questao_id = db
    reservar_questao(session, questao_id, 1, "Juiz Um", "sessao-1")
    estado = {
        "question_lock_id": questao_id,
        "question_lock_owned": True,
        "question_lock_owner": "Juiz Um",
    }

    liberada = liberar_reserva_ao_trocar_equipe(
        session, estado, 1, 1, questao_id, "sessao-1"
    )

    assert liberada is False
    assert estado["question_lock_owned"] is True
    assert session.query(QuestaoLock).count() == 1


def test_trocar_equipe_nao_libera_reserva_de_outra_sessao(db):
    session, questao_id = db
    reservar_questao(session, questao_id, 1, "Juiz Um", "sessao-1")
    estado = {
        "question_lock_id": questao_id,
        "question_lock_owned": False,
        "question_lock_owner": "Juiz Um",
    }

    liberada = liberar_reserva_ao_trocar_equipe(
        session, estado, 1, 2, questao_id, "sessao-2"
    )

    assert liberada is False
    assert estado["question_lock_owner"] == "Juiz Um"
    assert session.query(QuestaoLock).count() == 1


# --- Testes da Fase 1 (novas funcoes) ---

def test_limpar_locks_expirados_remove_apenas_expirados(db):
    session, questao_id = db
    agora = datetime.now(timezone.utc)

    # lock ativo — nao deve ser removido
    session.add(
        QuestaoLock(
            questao_id=questao_id,
            session_token="sessao-ativa",
            ator_id=1,
            nome_ator="Juiz Ativo",
            expires_at=agora + timedelta(minutes=5),
            updated_at=agora,
        )
    )
    # lock expirado — deve ser removido
    session.add(
        QuestaoLock(
            questao_id=questao_id + 1,
            session_token="sessao-expirada",
            ator_id=2,
            nome_ator="Juiz Fantasma",
            expires_at=agora - timedelta(seconds=10),
            updated_at=agora - timedelta(minutes=2),
        )
    )
    session.commit()

    removidos = limpar_locks_expirados(session)

    assert removidos == 1
    assert session.query(QuestaoLock).count() == 1
    lock_restante = session.query(QuestaoLock).first()
    assert lock_restante.session_token == "sessao-ativa"


def test_obter_ou_renovar_questao_renova_com_sucesso(db):
    session, questao_id = db
    reservar_questao(session, questao_id, 1, "Juiz Um", "sessao-1")

    estado = obter_ou_renovar_reserva_questao(
        session, questao_id, 1, "Juiz Um", "sessao-1"
    )

    assert estado["lock_owned"] is True
    assert estado["lock_owner"] == "Juiz Um"
    assert estado["lock_lost"] is False
    assert estado["lock_message"] is None
    assert estado["expires_at"] is not None


def test_obter_ou_renovar_questao_reassume_lock_expirado(db):
    session, questao_id = db
    # simulamos um lock expirado de outro juiz
    session.add(
        QuestaoLock(
            questao_id=questao_id,
            session_token="sessao-antiga",
            ator_id=2,
            nome_ator="Juiz Antigo",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            updated_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        )
    )
    session.commit()

    estado = obter_ou_renovar_reserva_questao(
        session, questao_id, 1, "Juiz Novo", "sessao-nova"
    )

    assert estado["lock_owned"] is True
    assert estado["lock_owner"] == "Juiz Novo"
    assert estado["lock_lost"] is False
    assert estado["lock_message"] is None


def test_obter_ou_renovar_questao_informa_novo_dono_quando_ocupado(db):
    session, questao_id = db
    # lock valido de outro juiz
    reservar_questao(session, questao_id, 2, "Juiz Dono", "sessao-dono")

    estado = obter_ou_renovar_reserva_questao(
        session, questao_id, 1, "Juiz Intruso", "sessao-intruso"
    )

    assert estado["lock_owned"] is False
    assert estado["lock_owner"] == "Juiz Dono"
    assert estado["lock_lost"] is True
    assert "Juiz Dono" in estado["lock_message"]


def test_obter_ou_renovar_questao_mesmo_juiz_token_diferente(db):
    """Mesmo juiz (mesmo ator_id) com token novo reassume via UPSERT."""
    session, questao_id = db
    reservar_questao(session, questao_id, 1, "Juiz Um", "sessao-antiga")

    estado = obter_ou_renovar_reserva_questao(
        session, questao_id, 1, "Juiz Um", "sessao-nova"
    )

    assert estado["lock_owned"] is True
    assert estado["lock_owner"] == "Juiz Um"
    # token antigo nao renova mais
    renovada, _ = renovar_reserva_questao(session, questao_id, "sessao-antiga")
    assert renovada is False
    # token novo renova
    renovada, novo_exp = renovar_reserva_questao(session, questao_id, "sessao-nova")
    assert renovada is True
    assert novo_exp is not None
