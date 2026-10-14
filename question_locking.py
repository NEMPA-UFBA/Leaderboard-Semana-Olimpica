from datetime import datetime, timedelta, timezone
from typing import MutableMapping, Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from models import QuestaoLock

RESERVA_DURACAO = timedelta(seconds=90)


def reservar_questao(
    db: Session,
    questao_id: int,
    ator_id: int,
    nome_ator: str,
    session_token: str,
) -> dict:
    agora = datetime.now(timezone.utc)
    valores = {
        "questao_id": questao_id,
        "session_token": session_token,
        "ator_id": ator_id,
        "nome_ator": nome_ator,
        "expires_at": agora + RESERVA_DURACAO,
        "updated_at": agora,
    }
    dialeto = db.get_bind().dialect.name
    if dialeto == "postgresql":
        inserir = postgresql_insert(QuestaoLock)
    elif dialeto == "sqlite":
        inserir = sqlite_insert(QuestaoLock)
    else:
        raise RuntimeError(
            f"Reservas de questoes nao suportam o banco {dialeto}."
        )

    resultado = db.execute(
        inserir.values(**valores)
        .on_conflict_do_update(
            index_elements=[QuestaoLock.questao_id],
            set_={
                "session_token": session_token,
                "ator_id": ator_id,
                "nome_ator": nome_ator,
                "expires_at": valores["expires_at"],
                "updated_at": agora,
            },
            where=or_(
                QuestaoLock.session_token == session_token,
                QuestaoLock.ator_id == ator_id,
                QuestaoLock.expires_at <= agora,
            ),
        )
        .returning(QuestaoLock.session_token)
    ).scalar_one_or_none()

    db.commit()
    if resultado == session_token:
        return {
            "reservada": True,
            "nome_ator": nome_ator,
            "expires_at": valores["expires_at"],
        }

    reserva = db.execute(
        select(QuestaoLock).where(QuestaoLock.questao_id == questao_id)
    ).scalar_one_or_none()
    db.commit()
    if reserva is None:
        return {"reservada": False, "nome_ator": None, "expires_at": None}
    return {
        "reservada": False,
        "nome_ator": reserva.nome_ator,
        "expires_at": reserva.expires_at,
    }


def renovar_reserva_questao(
    db: Session, questao_id: int, session_token: str
) -> bool:
    agora = datetime.now(timezone.utc)
    resultado = db.execute(
        update(QuestaoLock)
        .where(
            QuestaoLock.questao_id == questao_id,
            QuestaoLock.session_token == session_token,
        )
        .values(
            expires_at=agora + RESERVA_DURACAO,
            updated_at=agora,
        )
    )
    db.commit()
    return resultado.rowcount == 1


def liberar_reserva_questao(
    db: Session, questao_id: int, session_token: str
) -> bool:
    resultado = db.execute(
        delete(QuestaoLock).where(
            QuestaoLock.questao_id == questao_id,
            QuestaoLock.session_token == session_token,
        )
    )
    db.commit()
    return resultado.rowcount == 1


def liberar_reserva_ao_trocar_equipe(
    db: Session,
    session_state: MutableMapping[str, Any],
    equipe_anterior_id: int,
    equipe_nova_id: int,
    questao_id: int,
    session_token: str,
) -> bool:
    if (
        equipe_anterior_id == equipe_nova_id
        or session_state.get("question_lock_id") != questao_id
        or not session_state.get("question_lock_owned")
    ):
        return False

    liberada = liberar_reserva_questao(db, questao_id, session_token)
    session_state["question_lock_owned"] = False
    session_state["question_lock_owner"] = None
    session_state["question_lock_lost"] = not liberada
    session_state.pop("question_lock_message", None)
    return liberada


def liberar_reserva_ao_sair_da_tela(
    db: Session, session_state: MutableMapping[str, Any]
) -> None:
    questao_id = session_state.get("question_lock_id")
    session_token = session_state.get("question_lock_session")
    if questao_id is not None and session_token:
        liberar_reserva_questao(db, questao_id, session_token)

    for chave in (
        "question_lock_id",
        "question_lock_owned",
        "question_lock_owner",
        "question_lock_lost",
        "question_lock_message",
    ):
        session_state.pop(chave, None)
