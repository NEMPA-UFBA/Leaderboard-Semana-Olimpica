import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import LoginSession

COOKIE_NAME = "batalha_login"
DURACAO_SESSAO = timedelta(hours=12)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _como_utc(valor: datetime) -> datetime:
    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


def criar_sessao_login(
    db: Session,
    user_id: int,
    agora: datetime | None = None,
) -> tuple[str, datetime]:
    inicio = agora or datetime.now(timezone.utc)
    expiracao = inicio + DURACAO_SESSAO
    token = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            user_id=user_id,
            token_hash=_hash_token(token),
            created_at=inicio,
            expires_at=expiracao,
        )
    )
    db.commit()
    return token, expiracao


def buscar_sessao_login(
    db: Session,
    token: str,
    agora: datetime | None = None,
) -> LoginSession | None:
    if not isinstance(token, str) or not token:
        return None

    sessao = (
        db.query(LoginSession)
        .filter_by(token_hash=_hash_token(token))
        .first()
    )
    if sessao is None:
        return None
    momento = _como_utc(agora or datetime.now(timezone.utc))
    if sessao.revoked_at is not None or _como_utc(sessao.expires_at) <= momento:
        db.delete(sessao)
        db.commit()
        return None
    return sessao


def revogar_sessao_login(db: Session, token: str | None) -> bool:
    if not isinstance(token, str) or not token:
        return False

    sessao = (
        db.query(LoginSession)
        .filter_by(token_hash=_hash_token(token))
        .first()
    )
    if sessao is None:
        return False
    db.delete(sessao)
    db.commit()
    return True
