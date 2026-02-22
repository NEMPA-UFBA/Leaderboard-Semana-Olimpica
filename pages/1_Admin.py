import streamlit as st
from database import get_db
from models import User, Equipe, Regata, Questao
from auth import login_form, require_auth, hash_password

db = get_db()

if not login_form(db, User):
    st.stop()

user = require_auth(["admin"])
if not user:
    st.error("Acesso restrito a administradores.")
    st.stop()

# Initialize form counters for clearing forms after submission
for key in ["form_juiz", "form_equipe", "form_regata", "form_questao"]:
    if key not in st.session_state:
        st.session_state[key] = 0

tab_juizes, tab_equipes, tab_regatas, tab_questoes = st.tabs(
    ["⚖️ Juizes", "👥 Equipes", "🏁 Regatas", "📝 Questoes"]
)

# --- JUIZES ---
with tab_juizes:
    col_form, col_list = st.columns([1, 1.5], gap="large")

    with col_form:
        st.markdown("#### Novo Juiz")
        with st.form(f"novo_juiz_{st.session_state.form_juiz}"):
            username = st.text_input("Username", placeholder="ex: juiz_maria")
            password = st.text_input("Senha", type="password", placeholder="Senha do juiz")
            submitted = st.form_submit_button("Criar Juiz", use_container_width=True, type="primary")
            if submitted:
                if not username or not password:
                    st.error("Preencha todos os campos.")
                elif db.query(User).filter_by(username=username).first():
                    st.error("Username ja existe.")
                else:
                    juiz = User(username=username, password_hash=hash_password(password), role="juiz")
                    db.add(juiz)
                    db.commit()
                    st.success(f"Juiz **{username}** criado!")
                    st.session_state.form_juiz += 1
                    st.rerun()

    with col_list:
        st.markdown("#### Juizes cadastrados")
        juizes = db.query(User).filter_by(role="juiz").all()
        if not juizes:
            st.caption("Nenhum juiz cadastrado ainda.")
        for j in juizes:
            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 1, 1])
                col1.markdown(f"**{j.username}**")
                if col2.button("🔑", key=f"edit_senha_{j.id}", help="Alterar senha"):
                    st.session_state[f"editing_senha_{j.id}"] = True
                if col3.button("🗑️", key=f"del_juiz_{j.id}", help="Remover juiz"):
                    db.delete(j)
                    db.commit()
                    st.rerun()
                if st.session_state.get(f"editing_senha_{j.id}"):
                    nova_senha = st.text_input("Nova senha", type="password", key=f"nova_senha_{j.id}")
                    c1, c2 = st.columns(2)
                    if c1.button("Confirmar", key=f"confirm_senha_{j.id}", type="primary"):
                        if nova_senha:
                            j.password_hash = hash_password(nova_senha)
                            db.commit()
                            st.success(f"Senha de **{j.username}** alterada!")
                            del st.session_state[f"editing_senha_{j.id}"]
                            st.rerun()
                        else:
                            st.error("Digite a nova senha.")
                    if c2.button("Cancelar", key=f"cancel_senha_{j.id}"):
                        del st.session_state[f"editing_senha_{j.id}"]
                        st.rerun()

# --- EQUIPES ---
with tab_equipes:
    col_form, col_list = st.columns([1, 1.5], gap="large")

    with col_form:
        st.markdown("#### Nova Equipe")
        with st.form(f"nova_equipe_{st.session_state.form_equipe}"):
            nome = st.text_input("Nome da Equipe", placeholder="ex: Equipe Alfa")
            submitted = st.form_submit_button("Criar Equipe", use_container_width=True, type="primary")
            if submitted:
                if not nome:
                    st.error("Digite o nome da equipe.")
                elif db.query(Equipe).filter_by(nome=nome).first():
                    st.error("Equipe ja existe.")
                else:
                    equipe = Equipe(nome=nome)
                    db.add(equipe)
                    db.commit()
                    st.success(f"Equipe **{nome}** criada!")
                    st.session_state.form_equipe += 1
                    st.rerun()

    with col_list:
        st.markdown("#### Equipes cadastradas")
        equipes = db.query(Equipe).all()
        if not equipes:
            st.caption("Nenhuma equipe cadastrada ainda.")
        for e in equipes:
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                col1.markdown(f"**{e.nome}**")
                if col2.button("🗑️", key=f"del_equipe_{e.id}", help="Remover equipe"):
                    db.delete(e)
                    db.commit()
                    st.rerun()

# --- REGATAS ---
with tab_regatas:
    col_form, col_list = st.columns([1, 1.5], gap="large")

    with col_form:
        st.markdown("#### Nova Regata")
        with st.form(f"nova_regata_{st.session_state.form_regata}"):
            nome = st.text_input("Nome da Regata", placeholder="ex: Regata 1")
            submitted = st.form_submit_button("Criar Regata", use_container_width=True, type="primary")
            if submitted:
                if not nome:
                    st.error("Digite o nome da regata.")
                else:
                    regata = Regata(nome=nome, ativa=False)
                    db.add(regata)
                    db.commit()
                    st.success(f"Regata **{nome}** criada!")
                    st.session_state.form_regata += 1
                    st.rerun()

    with col_list:
        st.markdown("#### Regatas cadastradas")
        regatas = db.query(Regata).all()
        if not regatas:
            st.caption("Nenhuma regata cadastrada ainda.")
        for r in regatas:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
                if r.ativa:
                    col1.markdown(f"**{r.nome}** &nbsp; 🟢 **ATIVA**")
                else:
                    col1.markdown(f"**{r.nome}** &nbsp; ⚪ Inativa")

                if not r.ativa:
                    if col2.button("Ativar", key=f"ativar_{r.id}", type="primary"):
                        for other in db.query(Regata).filter(Regata.id != r.id).all():
                            other.ativa = False
                        r.ativa = True
                        db.commit()
                        st.rerun()
                else:
                    if col2.button("Parar", key=f"desativar_{r.id}"):
                        r.ativa = False
                        db.commit()
                        st.rerun()

                if col3.button("✏️", key=f"edit_regata_{r.id}", help="Editar regata"):
                    st.session_state[f"editing_regata_{r.id}"] = True
                if col4.button("🗑️", key=f"del_regata_{r.id}", help="Remover regata"):
                    db.delete(r)
                    db.commit()
                    st.rerun()
                if st.session_state.get(f"editing_regata_{r.id}"):
                    novo_nome = st.text_input("Nome da regata", value=r.nome, key=f"novo_nome_regata_{r.id}")
                    c1, c2 = st.columns(2)
                    if c1.button("Salvar", key=f"save_regata_{r.id}", type="primary"):
                        if novo_nome and novo_nome.strip():
                            r.nome = novo_nome.strip()
                            db.commit()
                            st.success(f"Regata renomeada para **{r.nome}**!")
                            del st.session_state[f"editing_regata_{r.id}"]
                            st.rerun()
                        else:
                            st.error("Digite o nome da regata.")
                    if c2.button("Cancelar", key=f"cancel_regata_{r.id}"):
                        del st.session_state[f"editing_regata_{r.id}"]
                        st.rerun()

# --- QUESTOES ---
with tab_questoes:
    regatas = db.query(Regata).all()
    if not regatas:
        st.info("Crie uma regata primeiro na aba Regatas.")
    else:
        regata_selecionada = st.selectbox(
            "Selecionar Regata",
            regatas,
            format_func=lambda r: f"{'🟢 ' if r.ativa else ''}{r.nome}",
        )

        col_form, col_list = st.columns([1, 1.5], gap="large")

        with col_form:
            st.markdown(f"#### Nova Questao")
            niveis_display = {"facil": "🟢 Facil", "medio": "🟡 Medio", "dificil": "🔴 Dificil"}

            with st.form(f"nova_questao_{st.session_state.form_questao}"):
                nivel = st.selectbox("Nivel", ["facil", "medio", "dificil"],
                                     format_func=lambda n: niveis_display[n])
                enunciado = st.text_area("Enunciado", placeholder="Ex: Resolva $2x + 3 = 7$. Qual o valor de $x$?")
                imagem = st.file_uploader("Imagem da Questao", type=["png", "jpg", "jpeg"])
                submitted = st.form_submit_button("Adicionar Questao", use_container_width=True, type="primary")
                if submitted:
                    if not enunciado or not enunciado.strip():
                        st.error("Preencha o enunciado da questao.")
                    else:
                        questao = Questao(
                            regata_id=regata_selecionada.id,
                            nivel=nivel,
                            enunciado=enunciado.strip(),
                            imagem=imagem.read() if imagem else None,
                            imagem_filename=imagem.name if imagem else None,
                        )
                        db.add(questao)
                        db.commit()
                        st.success("Questao adicionada!")
                        st.session_state.form_questao += 1
                        st.rerun()

        with col_list:
            st.markdown("#### Questoes cadastradas")
            questoes = (
                db.query(Questao)
                .filter_by(regata_id=regata_selecionada.id)
                .all()
            )
            if not questoes:
                st.caption("Nenhuma questao nesta regata.")

            niveis_ordem = {"facil": 0, "medio": 1, "dificil": 2}
            questoes_sorted = sorted(questoes, key=lambda q: niveis_ordem.get(q.nivel, 99))

            for q in questoes_sorted:
                nivel_label = niveis_display.get(q.nivel, q.nivel)
                with st.container(border=True):
                    header_col, edit_col, del_col = st.columns([5, 0.5, 0.5])
                    header_col.markdown(f"**{nivel_label}**")
                    if edit_col.button("✏️", key=f"edit_questao_{q.id}", help="Editar questao"):
                        st.session_state[f"editing_questao_{q.id}"] = True
                    if del_col.button("🗑️", key=f"del_questao_{q.id}", help="Remover questao"):
                        db.delete(q)
                        db.commit()
                        st.rerun()
                    if st.session_state.get(f"editing_questao_{q.id}"):
                        niveis_keys = ["facil", "medio", "dificil"]
                        novo_nivel = st.selectbox(
                            "Nivel", niveis_keys,
                            index=niveis_keys.index(q.nivel) if q.nivel in niveis_keys else 0,
                            format_func=lambda n: niveis_display[n],
                            key=f"novo_nivel_{q.id}",
                        )
                        novo_enunciado = st.text_area("Enunciado", value=q.enunciado or "", key=f"novo_enunciado_{q.id}")
                        c1, c2 = st.columns(2)
                        if c1.button("Salvar", key=f"save_questao_{q.id}", type="primary"):
                            q.nivel = novo_nivel
                            q.enunciado = novo_enunciado.strip()
                            db.commit()
                            st.success("Questao atualizada!")
                            del st.session_state[f"editing_questao_{q.id}"]
                            st.rerun()
                        if c2.button("Cancelar", key=f"cancel_questao_{q.id}"):
                            del st.session_state[f"editing_questao_{q.id}"]
                            st.rerun()
                    else:
                        if q.enunciado:
                            st.markdown(q.enunciado)
                        if q.imagem:
                            st.image(q.imagem, width=300)

db.close()
