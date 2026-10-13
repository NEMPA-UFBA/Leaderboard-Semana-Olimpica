import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Equipe, Questao, Regata, Tentativa, User
from team_utils import (
    criar_equipes_automaticamente,
    excluir_equipes,
    gerar_nomes_equipes,
    ordenar_equipes,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def test_gerar_nomes_comeca_com_letras_gregas():
    assert gerar_nomes_equipes(3) == ["Time Alfa", "Time Beta", "Time Gama"]


def test_gerar_nomes_usa_astronomia_depois_das_letras_gregas():
    nomes = gerar_nomes_equipes(25)

    assert nomes[23] == "Time Ômega"
    assert nomes[24] == "Time Órion"


def test_gerar_nomes_pula_nomes_existentes_sem_repetir():
    nomes = gerar_nomes_equipes(3, ["time alfa", "Time Beta"])

    assert nomes == ["Time Gama", "Time Delta", "Time Épsilon"]
    assert len({nome.casefold() for nome in nomes}) == 3


def test_gerar_nomes_considera_equivalentes_com_ou_sem_acento():
    nomes = gerar_nomes_equipes(5, ["Time Epsilon"])

    assert "Time Épsilon" not in nomes


def test_ordenar_equipes_ignora_acentos_e_considera_nomes_personalizados(db):
    db.add_all(
        [
            Equipe(nome="Time Gama"),
            Equipe(nome="Time Épsilon"),
            Equipe(nome="Astro Z"),
            Equipe(nome="Astro A"),
        ]
    )
    db.commit()

    nomes = [equipe.nome for equipe in ordenar_equipes(db.query(Equipe).all())]

    assert nomes == ["Astro A", "Astro Z", "Time Épsilon", "Time Gama"]


@pytest.mark.parametrize("quantidade", [0, -1, True, 1.5])
def test_gerar_nomes_rejeita_quantidade_invalida(quantidade):
    with pytest.raises(ValueError, match="inteiro maior que zero"):
        gerar_nomes_equipes(quantidade)


def test_criar_equipes_em_lote_insere_a_quantidade_solicitada(db):
    nomes = criar_equipes_automaticamente(db, 4)

    assert len(nomes) == 4
    assert db.query(Equipe).count() == 4
    assert [e.nome for e in db.query(Equipe).order_by(Equipe.id)] == nomes


def test_criar_equipes_em_lote_continua_sem_duplicar_nomes(db):
    primeira_lote = criar_equipes_automaticamente(db, 2)
    segundo_lote = criar_equipes_automaticamente(db, 2)

    assert primeira_lote == ["Time Alfa", "Time Beta"]
    assert segundo_lote == ["Time Gama", "Time Delta"]
    assert db.query(Equipe).count() == 4


def test_excluir_equipes_em_lote_remove_as_selecionadas(db):
    equipes = [Equipe(nome=f"Equipe {i}") for i in range(3)]
    db.add_all(equipes)
    db.commit()

    removidas = excluir_equipes(db, [equipes[0].id, equipes[2].id])

    assert removidas == ["Equipe 0", "Equipe 2"]
    assert [e.nome for e in db.query(Equipe).all()] == ["Equipe 1"]


def test_excluir_equipes_em_lote_preserva_equipes_com_tentativas(db):
    equipe = Equipe(nome="Equipe com resultado")
    regata = Regata(nome="Regata teste")
    juiz = User(username="juiz_teste", password_hash="hash", role="juiz")
    db.add_all([equipe, regata, juiz])
    db.flush()
    questao = Questao(
        regata_id=regata.id,
        nivel="facil",
        enunciado="Questao teste",
    )
    db.add(questao)
    db.flush()
    db.add(
        Tentativa(
            equipe_id=equipe.id,
            questao_id=questao.id,
            numero=1,
            acertou=False,
            pontos=0,
            juiz_id=juiz.id,
        )
    )
    db.commit()

    with pytest.raises(ValueError, match="ja possuem tentativas"):
        excluir_equipes(db, [equipe.id])

    assert db.query(Equipe).filter_by(id=equipe.id).one()
