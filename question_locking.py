import logging
import time
from datetime import datetime, timedelta, timezone
from typing import MutableMapping, Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from models import QuestaoLock

logger = logging.getLogger(__name__)

RESERVA_DURACAO = timedelta(seconds=90)


def limpar_locks_expirados(db: Session) -> int:
    """Remove todos os locks expirados da tabela questao_locks.

    Deve ser chamada periodicamente (ex: no inicio de cada ciclo do fragmento
    do juiz) para evitar acumulo de registros zumbis deixados por juizes que
    fecharam o navegador ou perderam a conexao sem liberar o lock.
    """
    agora = datetime.now(timezone.utc)
    resultado = db.execute(
        delete(QuestaoLock).where(QuestaoLock.expires_at <= agora)
    )
    db.commit()
    if resultado.rowcount:
        logger.info(
            "Limpeza de locks: %d registro(s) expirado(s) removido(s).",
            resultado.rowcount,
        )
    return resultado.rowcount


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
    """Renova a reserva por mais RESERVA_DURACAO segundos.

    Tenta ate 3 vezes com intervalo de 1 segundo em caso de falha
    transiente de conexao (OperationalError), mitigando cold‑starts
    e micro‑desconexoes do Neon.
    """
    agora = datetime.now(timezone.utc)
    for tentativa in range(3):
        try:
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
        except OperationalError:
            db.rollback()
            if tentativa < 2:
                logger.warning(
                    "Renovacao de lock falhou (tentativa %d/3) — "
                    "retentando em 1s. questao=%d session=%s",
                    tentativa + 1,
                    questao_id,
                    session_token[:8],
                )
                time.sleep(1)
            else:
                logger.error(
                    "Renovacao de lock esgotada apos 3 tentativas. "
                    "questao=%d session=%s",
                    questao_id,
                    session_token[:8],
                )
    return False


def obter_ou_renovar_reserva_questao(
    db: Session,
    questao_id: int,
    ator_id: int,
    nome_ator: str,
    session_token: str,
) -> dict:
    """Tenta renovar o lock; se falhar, tenta reassumi-lo automaticamente.

    Retorna um dicionario com as chaves prontas para serem aplicadas ao
    st.session_state do Streamlit:

    - lock_owned (bool):       se o juiz atual detem o lock
    - lock_owner (str|None):   nome de quem detem o lock (o proprio ou outro)
    - lock_lost (bool):        True se o lock foi perdido para outro juiz
    - lock_message (str|None): mensagem para exibir ao juiz
    - expires_at (datetime|None): instante de expiracao do lock atual

    Se a renovacao falhar por expiracao (ninguem reassumiu), tenta um
    reservar_questao() imediatamente.  Se outro juiz ja detem o lock,
    retorna os dados desse juiz para que a UI possa informa-lo.
    """
    # 1. Tentar renovar (com retry interno para OperationalError)
    renovada = renovar_reserva_questao(db, questao_id, session_token)
    if renovada:
        reserva = db.execute(
            select(QuestaoLock).where(QuestaoLock.questao_id == questao_id)
        ).scalar_one_or_none()
        return {
            "lock_owned": True,
            "lock_owner": nome_ator,
            "lock_lost": False,
            "lock_message": None,
            "expires_at": reserva.expires_at if reserva else None,
        }

    # 2. Renovacao falhou — tentar reassumir o lock
    try:
        resultado = reservar_questao(
            db, questao_id, ator_id, nome_ator, session_token
        )
    except Exception:
        logger.exception(
            "Falha ao tentar reassumir lock. questao=%d session=%s",
            questao_id,
            session_token[:8],
        )
        return {
            "lock_owned": False,
            "lock_owner": None,
            "lock_lost": True,
            "lock_message": (
                "Erro de conexao ao verificar a reserva. "
                "O sistema tentara novamente em instantes."
            ),
            "expires_at": None,
        }

    if resultado["reservada"]:
        return {
            "lock_owned": True,
            "lock_owner": nome_ator,
            "lock_lost": False,
            "lock_message": None,
            "expires_at": resultado["expires_at"],
        }

    # 3. Nao foi possivel reassumir — lock pertence a outro ou esta livre
    if resultado["nome_ator"]:
        return {
            "lock_owned": False,
            "lock_owner": resultado["nome_ator"],
            "lock_lost": True,
            "lock_message": (
                f"Questao reservada por {resultado['nome_ator']}. "
                "Clique em 'Tentar reassumir' para verificar se foi liberada."
            ),
            "expires_at": resultado["expires_at"],
        }

    return {
        "lock_owned": False,
        "lock_owner": None,
        "lock_lost": True,
        "lock_message": (
            "A reserva expirou e nao foi possivel reassumi-la. "
            "Tente novamente ou recarregue a pagina."
        ),
        "expires_at": None,
    }


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
        "question_lock_session",
        "question_lock_owned",
        "question_lock_owner",
        "question_lock_lost",
        "question_lock_message",
        "judge_feedback",
        "judge_panel_context",
        "editing_attempt_id",
    ):
        session_state.pop(chave, None)
