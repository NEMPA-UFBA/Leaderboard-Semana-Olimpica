import streamlit as st
from database import get_db
from models import Regata, Questao
from question_utils import numerar_questoes, ordenar_questoes, rotulo_questao


@st.fragment(run_every=5)
def questoes_fragment():
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
        return

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

    questoes = ordenar_questoes(
        db.query(Questao).filter_by(regata_id=regata.id).all()
    )

    if not questoes:
        st.info("Nenhuma questao cadastrada para esta regata.")
    else:
        numeros_questoes = numerar_questoes(questoes)
        for questao in questoes:
            st.divider()
            st.subheader(
                rotulo_questao(questao, numeros_questoes[questao.id])
            )
            if questao.enunciado:
                st.markdown(questao.enunciado)
            if questao.imagem:
                st.image(questao.imagem, use_container_width=True)

    db.close()


questoes_fragment()
