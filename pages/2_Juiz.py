import streamlit as st
from database import get_db
from models import User, Equipe, Regata, Questao, Tentativa
from auth import login_form, require_auth
from scoring import excluir_tentativa, registrar_tentativa, PONTOS_POR_TENTATIVA
from question_utils import numerar_questoes, ordenar_questoes, rotulo_questao

db = get_db()

if not login_form(db, User):
    st.stop()

user = require_auth(["juiz", "admin"])
if not user:
    st.error("Acesso restrito a juizes.")
    st.stop()

# --- HEADER ---
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
st.markdown(f'<div class="juiz-header">PAINEL DO JUIZ</div>', unsafe_allow_html=True)
st.markdown(f'<div class="juiz-user">Logado como: {user["username"]}</div>', unsafe_allow_html=True)

if st.sidebar.button("Sair", use_container_width=True):
    del st.session_state["user"]
    st.rerun()

# Find active regata
regata = db.query(Regata).filter_by(ativa=True).first()

if not regata:
    st.warning("Nenhuma regata ativa no momento. Aguarde o admin ativar uma regata.")
    db.close()
    st.stop()

st.markdown(f"**Regata:** {regata.nome}")
st.divider()

equipes = db.query(Equipe).order_by(Equipe.nome).all()
questoes = ordenar_questoes(
    db.query(Questao).filter_by(regata_id=regata.id).all()
)
numeros_questoes = numerar_questoes(questoes)

if not equipes:
    st.warning("Nenhuma equipe cadastrada.")
    db.close()
    st.stop()

if not questoes:
    st.warning("Nenhuma questao nesta regata.")
    db.close()
    st.stop()

# --- Selection ---
col_eq, col_qt = st.columns(2, gap="large")

with col_eq:
    equipe_selecionada = st.selectbox(
        "Equipe", equipes, format_func=lambda e: e.nome
    )

with col_qt:
    questao_selecionada = st.selectbox(
        "Questao",
        questoes,
        format_func=lambda questao: rotulo_questao(
            questao, numeros_questoes[questao.id]
        ),
    )

st.divider()

# --- Attempt status ---
tentativas_anteriores = (
    db.query(Tentativa)
    .filter_by(equipe_id=equipe_selecionada.id, questao_id=questao_selecionada.id)
    .order_by(Tentativa.numero)
    .all()
)

ja_acertou = any(t.acertou for t in tentativas_anteriores)
num_tentativas = len(tentativas_anteriores)

# Status indicator
if ja_acertou:
    t_acerto = next(t for t in tentativas_anteriores if t.acertou)
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#1b5e20,#2e7d32); border-radius:12px; padding:1.5rem;
                    text-align:center; margin-bottom:1rem;">
            <div style="font-family:'Bebas Neue',sans-serif; font-size:1.8rem; color:#a5d6a7;
                        letter-spacing:2px;">JA ACERTOU!</div>
            <div style="font-family:'Outfit',sans-serif; color:#e8f5e9; font-size:1rem; margin-top:4px;">
                Tentativa {t_acerto.numero} — +{t_acerto.pontos} pontos</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
elif num_tentativas >= 3:
    st.markdown(
        """
        <div style="background:linear-gradient(135deg,#b71c1c,#c62828); border-radius:12px; padding:1.5rem;
                    text-align:center; margin-bottom:1rem;">
            <div style="font-family:'Bebas Neue',sans-serif; font-size:1.8rem; color:#ef9a9a;
                        letter-spacing:2px;">TENTATIVAS ESGOTADAS</div>
            <div style="font-family:'Outfit',sans-serif; color:#ffcdd2; font-size:1rem; margin-top:4px;">
                3/3 tentativas usadas — 0 pontos</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    proxima = num_tentativas + 1
    pontos_possiveis = {1: 100, 2: 80, 3: 50}

    # Attempt dots
    dots = ""
    for i in range(1, 4):
        if i <= num_tentativas:
            dots += '<span style="color:#ef5350; font-size:1.5rem; margin:0 4px;">●</span>'
        elif i == proxima:
            dots += '<span style="color:#ffd200; font-size:1.5rem; margin:0 4px;">●</span>'
        else:
            dots += '<span style="color:#555; font-size:1.5rem; margin:0 4px;">○</span>'

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#1a1a2e,#16213e); border:1px solid #333;
                    border-radius:12px; padding:1.5rem; text-align:center; margin-bottom:1rem;">
            <div style="margin-bottom:8px;">{dots}</div>
            <div style="font-family:'Outfit',sans-serif; color:#ccc; font-size:1rem;">
                {proxima}a tentativa — vale <strong style="color:#ffd200;">{pontos_possiveis[proxima]} pontos</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Action buttons
    col1, col2 = st.columns(2, gap="large")

    with col1:
        if st.button("✅ ACERTOU", use_container_width=True, type="primary"):
            result = registrar_tentativa(
                db, equipe_selecionada.id, questao_selecionada.id, True, user["id"]
            )
            if "erro" in result:
                st.error(result["erro"])
            else:
                st.success(
                    f"**{equipe_selecionada.nome}** — "
                    f"**{rotulo_questao(questao_selecionada, numeros_questoes[questao_selecionada.id])}** — "
                    f"{result['numero']}a tentativa — **+{result['pontos']} pontos!**"
                )
                st.balloons()

    with col2:
        if st.button("❌ ERROU", use_container_width=True):
            result = registrar_tentativa(
                db, equipe_selecionada.id, questao_selecionada.id, False, user["id"]
            )
            if "erro" in result:
                st.error(result["erro"])
            else:
                restantes = 3 - result["numero"]
                st.warning(
                    f"**{equipe_selecionada.nome}** — "
                    f"**{rotulo_questao(questao_selecionada, numeros_questoes[questao_selecionada.id])}** — "
                    f"Errou tentativa {result['numero']}. Restam {restantes} tentativa(s)."
                )

# --- Attempt history & correction ---
if tentativas_anteriores:
    st.divider()
    st.markdown("#### Historico de tentativas")
    for t in tentativas_anteriores:
        with st.container(border=True):
            status_icon = "✅" if t.acertou else "❌"
            c1, c2, c3 = st.columns([5, 1, 1])
            c1.markdown(
                f"**Tentativa {t.numero}** — {status_icon} {'Acertou' if t.acertou else 'Errou'} — **{t.pontos} pts**"
            )
            can_modify = (t.juiz_id == user["id"]) or (user["role"] == "admin")
            if can_modify:
                if c2.button("Corrigir", key=f"corrigir_{t.id}"):
                    t.acertou = not t.acertou
                    if t.acertou:
                        t.pontos = PONTOS_POR_TENTATIVA.get(t.numero, 0)
                    else:
                        t.pontos = 0
                    db.commit()
                    st.rerun()
                if c3.button("Excluir", key=f"excluir_{t.id}", type="primary"):
                    excluir_tentativa(db, t.id)
                    st.rerun()

db.close()
