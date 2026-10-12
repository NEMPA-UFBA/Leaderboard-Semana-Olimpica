import streamlit as st
from database import init_db
import importlib.util
import sys

# Ensure DB is ready (tables + default admin)
init_db()

st.set_page_config(
    page_title="Batalha Olimpica",
    page_icon="🏅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Desabilitar navegação automática do sidebar
st.markdown(
    """
    <style>
    [data-testid="stSidebarNav"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Inicializar página padrão
if "current_page" not in st.session_state:
    st.session_state.current_page = "home"

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Outfit:wght@300;400;600;700&display=swap');
    
    /* Header Navigation Styles */
    .nav-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 1rem 0 1.5rem;
        border-bottom: 2px solid #333;
        margin-bottom: 2rem;
    }
    
    .nav-title {
        font-family: 'Bebas Neue', sans-serif;
        font-size: 2rem;
        letter-spacing: 2px;
        background: linear-gradient(135deg, #f7971e, #ffd200);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    .nav-buttons {
        display: flex;
        gap: 1rem;
        flex-wrap: wrap;
    }
    
    </style>
    """,
    unsafe_allow_html=True,
)

# --- HEADER COM NAVEGAÇÃO ---
col_title, col_nav = st.columns([1, 2])

with col_title:
    st.markdown('<div class="nav-title">BATALHA OLIMPICA</div>', unsafe_allow_html=True)

with col_nav:
    nav_cols = st.columns([1, 1, 1, 1, 1])
    
    if nav_cols[0].button("🏠 HOME", use_container_width=True, 
                          help="Página inicial"):
        st.session_state.current_page = "home"
        st.rerun()
    
    if nav_cols[1].button("🏆 LEADERBOARD", use_container_width=True,
                          help="Ranking em tempo real"):
        st.session_state.current_page = "leaderboard"
        st.rerun()
    
    if nav_cols[2].button("📝 QUESTÕES", use_container_width=True,
                          help="Desafios da regata ativa"):
        st.session_state.current_page = "questoes"
        st.rerun()
    
    if nav_cols[3].button("⚙️ ADMIN", use_container_width=True,
                          help="Painel de administrador"):
        st.session_state.current_page = "admin"
        st.rerun()
        
    if nav_cols[4].button("🔒 JUIZ", use_container_width=True,
                          help="Área de acesso restrito"):
        st.session_state.current_page = "juiz"
        st.rerun()

st.divider()

# Render shared sidebar content before pages that may stop execution.
with st.sidebar:
    st.image("assets/images/logo NEMPA.png", width="content")
    st.markdown("### 🏆 The Team (NEMPA)")
    st.markdown("**Project Lead**")
    st.markdown("👨‍🏫 *Prof. Dr. Roberto Sant'Anna*")
    st.write("")
    st.markdown("**Core Developers**")
    st.markdown("🧠 *Enzo Ribeiro*")
    st.markdown("🧠 *Gabriel Siron*")
    st.markdown("🧠 *Ikaro Vieira*")
    st.write("")
    st.markdown("**Scientific Developers**")
    st.markdown("💻 *Iago Nunes*")
    st.divider()
    st.markdown("© 2026 NEMPA - UFBA")

# --- CARREGAR PÁGINA SELECIONADA ---
if st.session_state.current_page == "home":
    st.markdown(
        """
        <div style="text-align:center; padding:4rem 1rem;">
            <div style="font-family:'Outfit',sans-serif; color:#999; font-size:1.1rem; margin-top:0.5rem;
                        letter-spacing:2px; text-transform:uppercase;">Semana Olimpica 2026</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    home_leaderboard, home_questoes = st.columns(2, gap="large")
    with home_leaderboard:
        with st.container(border=True):
            st.markdown("### 🏆 LEADERBOARD")
            st.caption("Ranking em tempo real")
            if st.button("Abrir leaderboard", key="home_leaderboard", use_container_width=True):
                st.session_state.current_page = "leaderboard"
                st.rerun()
    with home_questoes:
        with st.container(border=True):
            st.markdown("### 📝 QUESTOES")
            st.caption("Desafios da regata ativa")
            if st.button("Abrir questoes", key="home_questoes", use_container_width=True):
                st.session_state.current_page = "questoes"
                st.rerun()

elif st.session_state.current_page == "leaderboard":
    spec = importlib.util.spec_from_file_location("leaderboard_page", "pages/3_Leaderboard.py")
    leaderboard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(leaderboard)

elif st.session_state.current_page == "questoes":
    spec = importlib.util.spec_from_file_location("questoes_page", "pages/4_Questoes.py")
    questoes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(questoes)

elif st.session_state.current_page == "admin":
    spec = importlib.util.spec_from_file_location("admin_page", "pages/1_Admin.py")
    admin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(admin)

elif st.session_state.current_page == "juiz":
    spec = importlib.util.spec_from_file_location("juiz_page", "pages/2_Juiz.py")
    juiz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(juiz)
