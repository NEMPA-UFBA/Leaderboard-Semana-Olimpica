import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from models import AuditLog, QuestaoLock, Tentativa, Equipe
from question_locking import RESERVA_DURACAO
from team_utils import chave_ordenacao_equipe

logger = logging.getLogger(__name__)

PONTOS_POR_TENTATIVA = {1: 100, 2: 80, 3: 50}


def _lock_equipe_questao(
    db: Session, equipe_id: int, questao_id: int
) -> bool:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            select(func.pg_advisory_xact_lock(equipe_id, questao_id))
        )
        return (
            db.execute(
                select(Equipe.id).where(Equipe.id == equipe_id)
            ).scalar_one_or_none()
            is not None
        )

    return (
        db.execute(
            select(Equipe.id)
            .where(Equipe.id == equipe_id)
            .with_for_update()
        ).scalar_one_or_none()
        is not None
    )


def _tentativa_snapshot(tentativa: Tentativa) -> dict:
    return {
        "numero": tentativa.numero,
        "acertou": tentativa.acertou,
        "pontos": tentativa.pontos,
    }


def _validar_reserva_questao(
    db: Session, questao_id: int, session_token: str | None
) -> str | None:
    if session_token is None:
        return None

    reserva = db.execute(
        select(QuestaoLock)
        .where(QuestaoLock.questao_id == questao_id)
        .with_for_update()
    ).scalar_one_or_none()
    if reserva is None or reserva.session_token != session_token:
        nome_responsavel = reserva.nome_ator if reserva else None
        if nome_responsavel:
            return f"Questao reservada por {nome_responsavel}. Atualize a tela."
        return "A reserva desta questao expirou. Atualize a tela e tente novamente."

    agora = datetime.now(timezone.utc)
    reserva.expires_at = agora + RESERVA_DURACAO
    reserva.updated_at = agora
    return None


def registrar_tentativa(
    db: Session,
    equipe_id: int,
    questao_id: int,
    acertou: bool,
    juiz_id: int,
    session_token: str | None = None,
) -> dict:
    """Register an attempt and calculate points automatically.

    Tenta ate 3 vezes em caso de falha transiente de conexao
    (OperationalError).  A constraint unique no banco garante que
    retentativas nao produzam duplicatas.
    """
    for tentativa_retry in range(3):
        try:
            if not _lock_equipe_questao(db, equipe_id, questao_id):
                db.rollback()
                return {"erro": "Equipe nao encontrada."}

            erro_reserva = _validar_reserva_questao(db, questao_id, session_token)
            if erro_reserva:
                db.rollback()
                return {"erro": erro_reserva}

            tentativas_anteriores = (
                db.query(Tentativa)
                .filter_by(equipe_id=equipe_id, questao_id=questao_id)
                .order_by(Tentativa.numero)
                .all()
            )

            if any(t.acertou for t in tentativas_anteriores):
                db.rollback()
                return {"erro": "Equipe ja acertou esta questao."}

            if len(tentativas_anteriores) >= 3:
                db.rollback()
                return {"erro": "Equipe ja esgotou as 3 tentativas nesta questao."}

            numero = len(tentativas_anteriores) + 1
            pontos = PONTOS_POR_TENTATIVA.get(numero, 0) if acertou else 0
            db.add(
                Tentativa(
                    equipe_id=equipe_id,
                    questao_id=questao_id,
                    numero=numero,
                    acertou=acertou,
                    pontos=pontos,
                    juiz_id=juiz_id,
                )
            )
            db.commit()

            return {
                "numero": numero,
                "acertou": acertou,
                "pontos": pontos,
            }

        except IntegrityError:
            db.rollback()
            return {
                "erro": (
                    "A tentativa nao foi registrada porque outro juiz "
                    "atualizou esta equipe. Atualize a tela e tente novamente."
                )
            }

        except OperationalError:
            db.rollback()
            if tentativa_retry < 2:
                logger.warning(
                    "Falha de conexao ao registrar tentativa "
                    "(tentativa %d/3) — retentando em 1.5s. "
                    "equipe=%d questao=%d",
                    tentativa_retry + 1,
                    equipe_id,
                    questao_id,
                )
                time.sleep(1.5)
                continue
            logger.error(
                "Registro de tentativa esgotado apos 3 tentativas. "
                "equipe=%d questao=%d",
                equipe_id,
                questao_id,
            )
            return {
                "erro": (
                    "O banco de dados nao respondeu a tempo. "
                    "Tente novamente."
                )
            }

        except Exception:
            logger.exception(
                "Erro interno ao registrar tentativa. "
                "equipe=%d questao=%d",
                equipe_id,
                questao_id,
            )
            db.rollback()
            return {
                "erro": (
                    "Erro interno ao registrar a tentativa. "
                    "Recarregue a pagina e tente novamente."
                )
            }

    # So alcancado se todos os retries de OperationalError falharem
    return {
        "erro": (
            "O banco de dados nao respondeu apos 3 tentativas. "
            "Tente novamente mais tarde."
        )
    }


def calcular_leaderboard(db: Session) -> list[dict]:
    """Calculate global leaderboard across all regatas, sorted by total points descending."""
    results = (
        db.query(Equipe.nome, func.coalesce(func.sum(Tentativa.pontos), 0).label("pontos"))
        .outerjoin(Tentativa, Tentativa.equipe_id == Equipe.id)
        .group_by(Equipe.id)
        .order_by(func.sum(Tentativa.pontos).desc())
        .all()
    )

    if db.query(Tentativa.id).first() is None:
        results.sort(key=lambda item: chave_ordenacao_equipe(item[0]))

    return [{"equipe": nome, "pontos": pontos} for nome, pontos in results]


def corrigir_tentativa(
    db: Session,
    tentativa_id: int,
    ator_id: int,
    ator_role: str,
    acertou: bool,
    session_token: str | None = None,
) -> dict:
    """Set an attempt result and record a change atomically."""
    if not isinstance(acertou, bool):
        raise ValueError("O resultado corrigido deve ser verdadeiro ou falso.")

    tentativa = db.query(Tentativa).filter_by(id=tentativa_id).first()
    if tentativa is None:
        raise LookupError("Tentativa nao encontrada.")

    if not _lock_equipe_questao(
        db, tentativa.equipe_id, tentativa.questao_id
    ):
        db.rollback()
        raise LookupError("Equipe da tentativa nao encontrada.")

    erro_reserva = _validar_reserva_questao(
        db, tentativa.questao_id, session_token
    )
    if erro_reserva:
        db.rollback()
        return {"erro": erro_reserva}

    tentativa = (
        db.query(Tentativa)
        .populate_existing()
        .filter_by(id=tentativa_id)
        .first()
    )
    if tentativa is None:
        db.rollback()
        raise LookupError("Tentativa nao encontrada.")

    if not tentativa.acertou and acertou:
        tentativa_posterior = (
            db.query(Tentativa)
            .filter(
                Tentativa.equipe_id == tentativa.equipe_id,
                Tentativa.questao_id == tentativa.questao_id,
                Tentativa.numero > tentativa.numero,
            )
            .first()
        )
        if tentativa_posterior is not None:
            db.rollback()
            return {
                "erro": (
                    "Exclua as tentativas posteriores antes de corrigir "
                    "esta tentativa como certa."
                )
            }

    try:
        antes = _tentativa_snapshot(tentativa)
        tentativa.acertou = acertou
        tentativa.pontos = (
            PONTOS_POR_TENTATIVA.get(tentativa.numero, 0)
            if tentativa.acertou
            else 0
        )
        depois = _tentativa_snapshot(tentativa)
        if antes == depois:
            db.commit()
            return depois

        db.add(
            AuditLog(
                ator_id=ator_id,
                ator_role=ator_role,
                equipe_id=tentativa.equipe_id,
                tentativa_id=tentativa.id,
                acao="correcao",
                detalhes={"antes": antes, "depois": depois},
            )
        )
        db.commit()
        return depois
    except OperationalError:
        logger.exception(
            "Falha de conexao ao corrigir tentativa. "
            "tentativa=%d ator=%d",
            tentativa_id,
            ator_id,
        )
        db.rollback()
        return {
            "erro": (
                "O banco de dados nao respondeu a tempo. "
                "Tente novamente."
            )
        }
    except Exception:
        logger.exception(
            "Erro interno ao corrigir tentativa. "
            "tentativa=%d ator=%d",
            tentativa_id,
            ator_id,
        )
        db.rollback()
        return {
            "erro": (
                "Erro interno ao corrigir a tentativa. "
                "Recarregue a pagina e tente novamente."
            )
        }


def excluir_tentativa(
    db: Session,
    tentativa_id: int,
    ator_id: int,
    ator_role: str,
    session_token: str | None = None,
) -> dict | None:
    """Delete an attempt and recalculate the remaining attempts for the same question."""
    tentativa = db.query(Tentativa).filter_by(id=tentativa_id).first()
    if tentativa is None:
        raise LookupError("Tentativa nao encontrada.")

    if not _lock_equipe_questao(
        db, tentativa.equipe_id, tentativa.questao_id
    ):
        db.rollback()
        raise LookupError("Equipe da tentativa nao encontrada.")

    erro_reserva = _validar_reserva_questao(
        db, tentativa.questao_id, session_token
    )
    if erro_reserva:
        db.rollback()
        return {"erro": erro_reserva}

    tentativa = (
        db.query(Tentativa)
        .populate_existing()
        .filter_by(id=tentativa_id)
        .first()
    )
    if tentativa is None:
        db.rollback()
        raise LookupError("Tentativa nao encontrada.")

    equipe_id = tentativa.equipe_id
    questao_id = tentativa.questao_id
    snapshot = _tentativa_snapshot(tentativa)

    try:
        db.delete(tentativa)
        db.flush()

        restantes = (
            db.query(Tentativa)
            .filter_by(equipe_id=equipe_id, questao_id=questao_id)
            .order_by(Tentativa.created_at, Tentativa.id)
            .all()
        )

        for numero, tentativa_restante in enumerate(restantes, start=1):
            tentativa_restante.numero = numero
            tentativa_restante.pontos = (
                PONTOS_POR_TENTATIVA.get(numero, 0)
                if tentativa_restante.acertou
                else 0
            )

        db.add(
            AuditLog(
                ator_id=ator_id,
                ator_role=ator_role,
                equipe_id=equipe_id,
                tentativa_id=tentativa_id,
                acao="exclusao",
                detalhes={"excluida": snapshot},
            )
        )
        db.commit()
    except OperationalError:
        logger.exception(
            "Falha de conexao ao excluir tentativa. "
            "tentativa=%d ator=%d",
            tentativa_id,
            ator_id,
        )
        db.rollback()
        return {
            "erro": (
                "O banco de dados nao respondeu a tempo. "
                "Tente novamente."
            )
        }
    except Exception:
        logger.exception(
            "Erro interno ao excluir tentativa. "
            "tentativa=%d ator=%d",
            tentativa_id,
            ator_id,
        )
        db.rollback()
        return {
            "erro": (
                "Erro interno ao excluir a tentativa. "
                "Recarregue a pagina e tente novamente."
            )
        }
