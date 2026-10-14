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
