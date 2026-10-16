from html import escape
from uuid import uuid4

import streamlit as st

from auth import login_form, logout_user, require_auth
from database import get_db
from judge_panel import render_judge_workflow
from models import User
from question_locking import liberar_reserva_ao_sair_da_tela
from time_utils import agora_no_fuso_do_evento


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

# Garante que as chaves dos selectboxes nunca fiquem indefinidas,
# prevenindo reset silencioso para index 0 durante auto-refresh do fragmento.
for key in ("juiz_equipe_id", "juiz_questao_id"):
    if key not in st.session_state:
        st.session_state[key] = None

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

render_judge_workflow(session_token)
