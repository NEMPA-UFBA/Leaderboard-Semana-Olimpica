from sqlalchemy.orm import Session
from sqlalchemy import func
from models import Tentativa, Equipe, Questao

PONTOS_POR_TENTATIVA = {1: 100, 2: 80, 3: 50}


def registrar_tentativa(
    db: Session, equipe_id: int, questao_id: int, acertou: bool, juiz_id: int
) -> dict:
    """Register an attempt and calculate points automatically."""
    # Check previous attempts
    tentativas_anteriores = (
        db.query(Tentativa)
        .filter_by(equipe_id=equipe_id, questao_id=questao_id)
        .order_by(Tentativa.numero)
        .all()
    )

    # Check if already correct
    for t in tentativas_anteriores:
        if t.acertou:
            return {"erro": "Equipe ja acertou esta questao."}

    # Check if max attempts reached
    if len(tentativas_anteriores) >= 3:
        return {"erro": "Equipe ja esgotou as 3 tentativas nesta questao."}

    numero = len(tentativas_anteriores) + 1

    if acertou:
        pontos = PONTOS_POR_TENTATIVA.get(numero, 0)
    else:
        pontos = 0

    tentativa = Tentativa(
        equipe_id=equipe_id,
        questao_id=questao_id,
        numero=numero,
        acertou=acertou,
        pontos=pontos,
        juiz_id=juiz_id,
    )
    db.add(tentativa)
    db.commit()

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


def excluir_tentativa(db: Session, tentativa_id: int) -> None:
    """Delete an attempt and recalculate the remaining attempts for the same question."""
    tentativa = db.get(Tentativa, tentativa_id)
    if tentativa is None:
        raise LookupError("Tentativa nao encontrada.")

    equipe_id = tentativa.equipe_id
    questao_id = tentativa.questao_id
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

    db.commit()
