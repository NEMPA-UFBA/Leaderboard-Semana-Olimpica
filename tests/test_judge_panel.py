from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from streamlit.testing.v1 import AppTest

from models import Base, Equipe, Questao, Regata, User
from question_locking import liberar_reserva_questao, reservar_questao


def test_assuming_released_question_refreshes_owner_message(tmp_path):
    database_path = tmp_path / "judge-panel.sqlite"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    juiz1 = User(
        nome="Juiz Um",
        username="juiz1",
        password_hash="unused",
        role="juiz",
    )
    juiz2 = User(
        nome="Juiz Dois",
        username="juiz2",
        password_hash="unused",
        role="juiz",
    )
    regata = Regata(nome="Regata teste", ativa=True)
    equipe = Equipe(nome="Time Alfa")
    db.add_all([juiz1, juiz2, regata, equipe])
    db.flush()
    questao = Questao(
        regata_id=regata.id,
        nivel="facil",
        enunciado="Questao teste",
    )
    db.add(questao)
    db.commit()
    reservar_questao(db, questao.id, juiz2.id, juiz2.nome, "sessao-juiz-2")

    juiz1_id = juiz1.id
    questao_id = questao.id
    db.close()

    app = AppTest.from_string(
        f"""
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import judge_panel

@st.cache_resource
def get_session_factory():
    engine = create_engine(
        "sqlite:///{database_path}",
        connect_args={{"check_same_thread": False}},
    )
    return sessionmaker(bind=engine, expire_on_commit=False)

judge_panel.get_db = lambda: get_session_factory()()
st.session_state["user"] = {{
    "id": {juiz1_id},
    "username": "juiz1",
    "role": "juiz",
}}
judge_panel.render_judge_workflow("sessao-juiz-1")
"""
    ).run()

    assert any(
        warning.value.startswith("Questao reservada por Juiz Dois.")
        for warning in app.warning
    )

    db = session_factory()
    assert liberar_reserva_questao(db, questao_id, "sessao-juiz-2")
    db.close()

    app.button[0].click().run()

    assert any(
        message.value.startswith("Questao reservada para Juiz Um")
        for message in app.success
    ), (
        f"successes={[message.value for message in app.success]}, "
        f"warnings={[message.value for message in app.warning]}, "
        f"exceptions={[exception.message for exception in app.exception]}"
    )
    assert not any(
        warning.value.startswith("Questao reservada por Juiz Dois.")
        for warning in app.warning
    )
    assert not app.exception

    engine.dispose()


def test_switching_team_discards_feedback_from_previous_team(tmp_path):
    database_path = tmp_path / "judge-feedback.sqlite"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    juiz = User(
        nome="Juiz Um",
        username="juiz1",
        password_hash="unused",
        role="juiz",
    )
    regata = Regata(nome="Regata teste", ativa=True)
    equipe_alfa = Equipe(nome="Time Alfa")
    equipe_xi = Equipe(nome="Time Xi")
    db.add_all([juiz, regata, equipe_alfa, equipe_xi])
    db.flush()
    questao = Questao(
        regata_id=regata.id,
        nivel="facil",
        enunciado="Questao teste",
    )
    db.add(questao)
    db.commit()
    juiz_id = juiz.id
    equipe_alfa_id = equipe_alfa.id
    equipe_xi_id = equipe_xi.id
    questao_id = questao.id
    db.close()

    app = AppTest.from_string(
        f"""
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import judge_panel

@st.cache_resource
def get_session_factory():
    engine = create_engine(
        "sqlite:///{database_path}",
        connect_args={{"check_same_thread": False}},
    )
    return sessionmaker(bind=engine, expire_on_commit=False)

judge_panel.get_db = lambda: get_session_factory()()
st.session_state["user"] = {{
    "id": {juiz_id},
    "username": "juiz1",
    "role": "juiz",
}}
judge_panel.render_judge_workflow("sessao-juiz-1")
"""
    ).run()

    app.session_state["juiz_equipe_id"] = equipe_alfa_id
    app.session_state["judge_panel_context"] = (equipe_alfa_id, questao_id)
    app.session_state["judge_feedback"] = {
        "tipo": "sucesso",
        "mensagem": "**Time Alfa** — resultado antigo",
    }
    app.session_state["juiz_equipe_id"] = equipe_xi_id
    app.run()

    assert "judge_feedback" not in app.session_state
    assert not any(
        "resultado antigo" in message.value
        for message in [*app.success, *app.warning, *app.error, *app.info]
    )
    assert not app.exception
    engine.dispose()


def test_error_button_persists_each_attempt_and_refreshes_history(tmp_path):
    database_path = tmp_path / "judge-attempts.sqlite"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    juiz = User(
        nome="Juiz Um",
        username="juiz1",
        password_hash="unused",
        role="juiz",
    )
    regata = Regata(nome="Regata teste", ativa=True)
    equipe = Equipe(nome="Time Diagnostico")
    db.add_all([juiz, regata, equipe])
    db.flush()
    questao = Questao(
        regata_id=regata.id,
        nivel="facil",
        enunciado="Questao teste",
    )
    db.add(questao)
    db.commit()
    juiz_id = juiz.id
    equipe_id = equipe.id
    questao_id = questao.id
    db.close()

    app = AppTest.from_string(
        f"""
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import judge_panel

@st.cache_resource
def get_session_factory():
    engine = create_engine(
        "sqlite:///{database_path}",
        connect_args={{"check_same_thread": False}},
    )
    return sessionmaker(bind=engine, expire_on_commit=False)

judge_panel.get_db = lambda: get_session_factory()()
st.session_state["user"] = {{
    "id": {juiz_id},
    "username": "juiz1",
    "role": "juiz",
}}
judge_panel.render_judge_workflow("sessao-juiz-1")
"""
    ).run()

    for numero in range(1, 4):
        next(
            button for button in app.button if button.label == "❌ ERROU"
        ).click().run()
        assert any(
            f"Errou tentativa {numero}." in message.value
            for message in app.warning
        )
        with session_factory() as db:
            from models import Tentativa

            tentativas = (
                db.query(Tentativa)
                .filter_by(equipe_id=equipe_id, questao_id=questao_id)
                .order_by(Tentativa.numero)
                .all()
            )
            assert [tentativa.numero for tentativa in tentativas] == list(
                range(1, numero + 1)
            )
            assert all(not tentativa.acertou for tentativa in tentativas)

    assert any(
        "TENTATIVAS ESGOTADAS" in element.value
        for element in app.markdown
    )
    assert not app.exception
    engine.dispose()
