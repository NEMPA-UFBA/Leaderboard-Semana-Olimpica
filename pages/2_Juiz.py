from html import escape
from uuid import uuid4

import streamlit as st

from auth import login_form, logout_user, require_auth
from database import get_db
from judge_panel import render_judge_workflow
from models import User
from question_locking import liberar_reserva_ao_sair_da_tela, renovar_reserva_questao
from time_utils import agora_no_fuso_do_evento


@st.fragment(run_every="30s")
def _renovar_reserva_periodicamente() -> None:
    questao_id = st.session_state.get("question_lock_id")
    session_token = st.session_state.get("question_lock_session")
    if questao_id is None or not session_token:
        return
    if not st.session_state.get("question_lock_owned"):
        return

    heartbeat_db = get_db()
    try:
        renovada = renovar_reserva_questao(
            heartbeat_db, questao_id, session_token
        )
    finally:
        heartbeat_db.close()

    if not renovada:
        st.session_state["question_lock_owned"] = False
        st.session_state["question_lock_owner"] = None
        st.session_state["question_lock_lost"] = True
        st.rerun(scope="app")


db = get_db()
if not login_form(db, User):
    liberar_reserva_ao_sair_da_tela(db, st.session_state)
    db.close()
    st.stop()

user = require_auth(["juiz", "admin"])
if not user:
    st.error("Acesso restrito a juizes.")
    liberar_reserva_ao_sair_da_tela(db, st.session_state)
    db.close()
    st.stop()

conta = db.get(User, user["id"])
nome_exibicao = conta.nome if conta and conta.nome else user["username"]
db.close()

if "question_lock_session" not in st.session_state:
    st.session_state["question_lock_session"] = uuid4().hex
session_token = st.session_state["question_lock_session"]

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Outfit:wght@300;400;600;700&display=swap');
    .juiz-header { font-family:'Bebas Neue',sans-serif; font-size:2.2rem; letter-spacing:2px;
                   background:linear-gradient(135deg,#f7971e,#ffd200); -webkit-background-clip:text;
                   -webkit-text-fill-color:transparent; }
    .juiz-user { font-family:'Outfit',sans-serif; color:#888; font-size:0.9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="juiz-header">PAINEL DO JUIZ</div>', unsafe_allow_html=True
)
st.markdown(
    f'<div class="juiz-user">Bem-vindo(a), {escape(nome_exibicao)}!</div>',
    unsafe_allow_html=True,
)
st.caption(
    f"Data e hora: {agora_no_fuso_do_evento():%d/%m/%Y %H:%M:%S} "
    "(horario de Brasilia)"
)

if st.sidebar.button("Sair", use_container_width=True):
    logout_user(db)
    liberar_reserva_ao_sair_da_tela(db, st.session_state)
    st.session_state.pop("question_lock_session", None)
    db.close()
    st.rerun()

_renovar_reserva_periodicamente()
render_judge_workflow(session_token)
