from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from models import AuditLog, QuestaoLock, Tentativa, Equipe
from question_locking import RESERVA_DURACAO

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
    """Register an attempt and calculate points automatically."""
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
    except IntegrityError:
        db.rollback()
        return {
            "erro": (
                "A tentativa nao foi registrada porque outro juiz atualizou "
                "esta equipe. Atualize a tela e tente novamente."
            )
        }

    return {
        "numero": numero,
        "acertou": acertou,
        "pontos": pontos,
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
            PONTOS_POR_TENTATIVA.get(numero, 0) if tentativa_restante.acertou else 0
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
