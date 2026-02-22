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
    nav_cols = st.columns([1, 1, 1, 1])
    
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

st.divider()

# --- CARREGAR PÁGINA SELECIONADA ---
if st.session_state.current_page == "home":
    st.markdown(
        """
        <div style="text-align:center; padding:4rem 1rem;">
            <div style="font-family:'Outfit',sans-serif; color:#999; font-size:1.1rem; margin-top:0.5rem;
                        letter-spacing:2px; text-transform:uppercase;">Semana Olimpica 2026</div>
            <div style="margin-top:3rem; display:flex; justify-content:center; gap:2rem; flex-wrap:wrap;">
                <div onclick="document.querySelector('button:nth-child(2)').click();" style="background:linear-gradient(145deg,#1a1a2e,#16213e); border:1px solid #333;
                            border-radius:16px; padding:2rem 2.5rem; min-width:200px;
                            transition:border-color 0.2s, transform 0.2s; cursor:pointer;"
                     onmouseover="this.style.borderColor='#ffd200'; this.style.transform='translateY(-4px)';"
                     onmouseout="this.style.borderColor='#333'; this.style.transform='translateY(0)';">
                    <div style="font-family:'Bebas Neue',sans-serif; font-size:1.8rem; color:#ffd200;
                                letter-spacing:2px;">LEADERBOARD</div>
                    <div style="font-family:'Outfit',sans-serif; color:#888; font-size:0.85rem; margin-top:4px;">
                        Ranking em tempo real</div>
                </div>
                <div onclick="document.querySelector('button:nth-child(3)').click();" style="background:linear-gradient(145deg,#1a1a2e,#16213e); border:1px solid #333;
                            border-radius:16px; padding:2rem 2.5rem; min-width:200px;
                            transition:border-color 0.2s, transform 0.2s; cursor:pointer;"
                     onmouseover="this.style.borderColor='#ffd200'; this.style.transform='translateY(-4px)';"
                     onmouseout="this.style.borderColor='#333'; this.style.transform='translateY(0)';">
                    <div style="font-family:'Bebas Neue',sans-serif; font-size:1.8rem; color:#ffd200;
                                letter-spacing:2px;">QUESTOES</div>
                    <div style="font-family:'Outfit',sans-serif; color:#888; font-size:0.85rem; margin-top:4px;">
                        Desafios da regata ativa</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

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

with st.sidebar:
    st.image("assets/images/logo NEMPA.png", width="content")
    st.markdown("### 🏆 The Team (NEMPA)")
    
    # Project Lead
    st.markdown("**Project Lead**")
    st.markdown("👨‍🏫 *Prof. Dr. Roberto Sant'Anna*")
    
    st.write("") # Spacer
    
    # Core Dev (Technical Acknowledgment)
    st.markdown("**Core Developers**")
    st.markdown("🧠 *Gabriel Siron*")
    st.markdown("🧠 *Ikaro Vieira*")
    st.markdown("🧠 *Enzo Ribeiro*")
    
    st.write("")

    # Scientific Devs (Support Team)
    st.markdown("**Scientific Developers**")
    st.markdown("💻 *Felipe Brasileiro*")
    st.markdown("💻 *Iago Nunes*")

    st.divider()
    st.markdown("© 2026 NEMPA - UFBA")