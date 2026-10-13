from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    LargeBinary,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Table,
)
from sqlalchemy.orm import relationship
from database import Base


questao_tags = Table(
    "questao_tags",
    Base.metadata,
    Column(
        "questao_id",
        Integer,
        ForeignKey("questoes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(10), nullable=False)  # "admin" or "juiz"
    must_change_password = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    login_sessions = relationship(
        "LoginSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )



class Equipe(Base):
    __tablename__ = "equipes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    tentativas = relationship("Tentativa", back_populates="equipe")


class Regata(Base):
    __tablename__ = "regatas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False)
    ativa = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    questoes = relationship("Questao", back_populates="regata", cascade="all, delete-orphan")


class Questao(Base):
    __tablename__ = "questoes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    regata_id = Column(Integer, ForeignKey("regatas.id"), nullable=False)
    nivel = Column(String(10), nullable=False)  # "facil", "medio", "dificil"
    enunciado = Column(Text, nullable=False)
    imagem = Column(LargeBinary, nullable=True)
    imagem_filename = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    regata = relationship("Regata", back_populates="questoes")
    tentativas = relationship("Tentativa", back_populates="questao")
    tags = relationship("Tag", secondary=questao_tags, back_populates="questoes")


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        Index("uq_tags_categoria_nome", "categoria", "nome", unique=True),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(50), nullable=False)
    categoria = Column(String(20), nullable=False)

    questoes = relationship("Questao", secondary=questao_tags, back_populates="tags")


class LoginSession(Base):
    __tablename__ = "login_sessions"
    __table_args__ = (
        Index("uq_login_sessions_token_hash", "token_hash", unique=True),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="login_sessions")


class Tentativa(Base):
    __tablename__ = "tentativas"
    __table_args__ = (
        Index(
            "uq_tentativas_equipe_questao_numero",
            "equipe_id",
            "questao_id",
            "numero",
            unique=True,
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    equipe_id = Column(Integer, ForeignKey("equipes.id"), nullable=False)
    questao_id = Column(Integer, ForeignKey("questoes.id"), nullable=False)
    numero = Column(Integer, nullable=False)  # 1, 2, or 3
    acertou = Column(Boolean, nullable=False)
    pontos = Column(Integer, nullable=False, default=0)
    juiz_id = Column(Integer, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    equipe = relationship("Equipe", back_populates="tentativas")
    questao = relationship("Questao", back_populates="tentativas")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ator_id = Column(Integer, nullable=False)
    ator_role = Column(String(10), nullable=False)
    equipe_id = Column(Integer, nullable=False)
    tentativa_id = Column(Integer, nullable=False)
    acao = Column(String(20), nullable=False)
    detalhes = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class QuestaoLock(Base):
    __tablename__ = "questao_locks"

    questao_id = Column(
        Integer,
        ForeignKey("questoes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    session_token = Column(String(64), nullable=False)
    ator_id = Column(Integer, nullable=False)
    nome_ator = Column(String(100), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
