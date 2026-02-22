import time
import streamlit as st
from database import get_db
from models import Regata, Questao

db = get_db()

regata = db.query(Regata).filter_by(ativa=True).first()

if not regata:
    st.markdown(
        """
        <div style="text-align:center; padding:6rem 1rem;">
            <div style="font-family:'Bebas Neue',sans-serif; font-size:3rem; letter-spacing:3px;
                        background:linear-gradient(135deg,#f7971e,#ffd200); -webkit-background-clip:text;
                        -webkit-text-fill-color:transparent;">BATALHA OLIMPICA</div>
            <div style="font-family:'Outfit',sans-serif; color:#888; font-size:1.1rem; margin-top:1rem;">
                Nenhuma regata ativa no momento. Aguarde...</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    db.close()
    time.sleep(5)
    st.rerun()

# Header
st.markdown(
    f"""
    <div style="text-align:center; padding:1rem 0 2rem;">
        <div style="font-family:'Bebas Neue',sans-serif; font-size:2.5rem; letter-spacing:3px;
                    background:linear-gradient(135deg,#f7971e,#ffd200); -webkit-background-clip:text;
                    -webkit-text-fill-color:transparent;">QUESTOES</div>
        <div style="font-family:'Outfit',sans-serif; color:#888; font-size:1rem; margin-top:4px;">
            {regata.nome}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

questoes = db.query(Questao).filter_by(regata_id=regata.id).all()

if not questoes:
    st.info("Nenhuma questao cadastrada para esta regata.")
else:
    for q in questoes:
        st.divider()
        if q.enunciado:
            st.markdown(q.enunciado)
        if q.imagem:
            st.image(q.imagem, use_container_width=True)

db.close()
