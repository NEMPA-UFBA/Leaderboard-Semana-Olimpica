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
)
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(10), nullable=False)  # "admin" or "juiz"
    must_change_password = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))



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


class Tentativa(Base):
    __tablename__ = "tentativas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    equipe_id = Column(Integer, ForeignKey("equipes.id"), nullable=False)
    questao_id = Column(Integer, ForeignKey("questoes.id"), nullable=False)
    numero = Column(Integer, nullable=False)  # 1, 2, or 3
    acertou = Column(Boolean, nullable=False)
    pontos = Column(Integer, nullable=False, default=0)
    juiz_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    equipe = relationship("Equipe", back_populates="tentativas")
    questao = relationship("Questao", back_populates="tentativas")
