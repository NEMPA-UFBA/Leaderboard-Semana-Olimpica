import streamlit as st
from database import get_db
from models import User, Equipe, Regata, Questao, Tag, Tentativa
from auth import (
    change_password,
    hash_password,
    login_form,
    logout_user,
    password_validation_error,
    require_auth,
    verify_password,
)
from question_utils import numerar_questoes, ordenar_questoes, rotulo_questao
from team_utils import (
    criar_equipes_automaticamente,
    excluir_equipes,
    ordenar_equipes,
)
from question_tags import atualizar_tags_questao
from question_locking import liberar_reserva_ao_sair_da_tela

db = get_db()
liberar_reserva_ao_sair_da_tela(db, st.session_state)

if not login_form(db, User):
    st.stop()

user = require_auth(["admin"])
if not user:
    st.error("Acesso restrito a administradores.")
    st.stop()

# Initialize form counters for clearing forms after submission
for key in [
    "form_juiz",
    "form_equipe",
    "form_regata",
    "form_questao",
    "form_excluir_equipes",
]:
    if key not in st.session_state:
        st.session_state[key] = 0

tab_juizes, tab_equipes, tab_regatas, tab_questoes, tab_conta = st.tabs(
    ["⚖️ Juizes", "👥 Equipes", "🏁 Regatas", "📝 Questoes", "🔐 Minha conta"]
)

if st.sidebar.button("Sair", use_container_width=True):
    logout_user(db)
    st.rerun()

# --- JUIZES ---
with tab_juizes:
    col_form, col_list = st.columns([1, 1.5], gap="large")

    with col_form:
        st.markdown("#### Novo Juiz")
        with st.form(f"novo_juiz_{st.session_state.form_juiz}"):
            nome = st.text_input("Nome do juiz", placeholder="ex: Juliana Maria")
            username = st.text_input("Username", placeholder="ex: juiz_maria")
            password = st.text_input("Senha", type="password", placeholder="Senha do juiz")
            submitted = st.form_submit_button("Criar Juiz", use_container_width=True, type="primary")
            if submitted:
                if not nome or not username or not password:
                    st.error("Preencha todos os campos.")
                elif password_validation_error(password):
                    st.error(password_validation_error(password))
                elif db.query(User).filter_by(username=username).first():
                    st.error("Username ja existe.")
                else:
                    juiz = User(
                        nome=nome.strip(),
                        username=username,
                        password_hash=hash_password(password),
                        role="juiz",
                        must_change_password=True,
                    )
                    db.add(juiz)
                    db.commit()
                    st.success(
                        f"Juiz **{username}** criado. Ele devera trocar a senha no primeiro acesso."
                    )
                    st.session_state.form_juiz += 1
                    st.rerun()

    with col_list:
        st.markdown("#### Juizes cadastrados")
        juizes = db.query(User).filter_by(role="juiz").all()
        if not juizes:
            st.caption("Nenhum juiz cadastrado ainda.")
        for j in juizes:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
                col1.markdown(f"**{j.nome or j.username}**")
                col1.caption(f"Login: {j.username}")
                if col2.button("✏️", key=f"edit_nome_{j.id}", help="Alterar nome"):
                    st.session_state[f"editing_nome_{j.id}"] = True
                if col3.button("🔑", key=f"edit_senha_{j.id}", help="Alterar senha"):
                    st.session_state[f"editing_senha_{j.id}"] = True
                if col4.button("🗑️", key=f"del_juiz_{j.id}", help="Remover juiz"):
                    db.delete(j)
                    db.commit()
                    st.rerun()
                if st.session_state.get(f"editing_nome_{j.id}"):
                    novo_nome = st.text_input(
                        "Nome do juiz",
                        value=j.nome or j.username,
                        key=f"novo_nome_juiz_{j.id}",
                    )
                    c1, c2 = st.columns(2)
                    if c1.button(
                        "Salvar nome", key=f"save_nome_juiz_{j.id}", type="primary"
                    ):
                        if novo_nome.strip():
                            j.nome = novo_nome.strip()
                            db.commit()
                            st.session_state.pop(f"editing_nome_{j.id}", None)
                            st.rerun()
                        else:
                            st.error("Digite o nome do juiz.")
                    if c2.button("Cancelar", key=f"cancel_nome_juiz_{j.id}"):
                        st.session_state.pop(f"editing_nome_{j.id}", None)
                        st.rerun()
                if st.session_state.get(f"editing_senha_{j.id}"):
                    nova_senha = st.text_input("Nova senha", type="password", key=f"nova_senha_{j.id}")
                    c1, c2 = st.columns(2)
                    if c1.button("Confirmar", key=f"confirm_senha_{j.id}", type="primary"):
                        if nova_senha:
                            error = password_validation_error(nova_senha)
                            if error:
                                st.error(error)
                            elif verify_password(nova_senha, j.password_hash):
                                st.error("A nova senha deve ser diferente da senha atual.")
                            else:
                                change_password(j, nova_senha)
                                j.must_change_password = True
                                db.commit()
                                st.success(
                                    f"Senha de **{j.username}** redefinida. "
                                    "O juiz devera troca-la no proximo acesso."
                                )
                                del st.session_state[f"editing_senha_{j.id}"]
                                st.rerun()
                        else:
                            st.error("Digite a nova senha.")
                    if c2.button("Cancelar", key=f"cancel_senha_{j.id}"):
                        del st.session_state[f"editing_senha_{j.id}"]
                        st.rerun()

# --- EQUIPES ---
with tab_equipes:
    feedback = st.session_state.pop("equipe_admin_feedback", None)
    if feedback:
        st.success(feedback)

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

        st.markdown("#### Criar equipes em lote")
        with st.form("criar_equipes_em_lote"):
            quantidade = st.number_input(
                "Quantas equipes deseja criar?",
                min_value=1,
                value=1,
                step=1,
            )
            submitted = st.form_submit_button(
                "Criar equipes automaticamente",
                use_container_width=True,
            )
            if submitted:
                try:
                    nomes_criados = criar_equipes_automaticamente(
                        db, int(quantidade)
                    )
                except RuntimeError as error:
                    st.error(str(error))
                else:
                    st.success(
                        f"{len(nomes_criados)} equipes criadas: "
                        + ", ".join(nomes_criados)
                    )

    with col_list:
        st.markdown("#### Equipes cadastradas")
        equipes = ordenar_equipes(db.query(Equipe).all())
        equipes_com_tentativas = {
            equipe_id
            for (equipe_id,) in (
                db.query(Tentativa.equipe_id)
                .distinct()
                .all()
            )
        }
        if not equipes:
            st.caption("Nenhuma equipe cadastrada ainda.")
        for e in equipes:
            with st.container(border=True):
                nome_coluna, status_coluna = st.columns([3, 2])
                nome_coluna.markdown(f"**{e.nome}**")
                status_coluna.caption(
                    "✓ Com tentativas"
                    if e.id in equipes_com_tentativas
                    else "— Sem tentativas"
                )

        if equipes:
            ids_disponiveis = [e.id for e in equipes]
            equipes_por_id = {e.id: e for e in equipes}
            chave_selecao = (
                f"equipes_para_excluir_{st.session_state.form_excluir_equipes}"
            )
            if st.button(
                "Selecionar todas as equipes",
                key=f"selecionar_todas_{st.session_state.form_excluir_equipes}",
            ):
                st.session_state[chave_selecao] = ids_disponiveis
                st.rerun()

            selecionadas = st.multiselect(
                "Equipes para exclusao",
                options=ids_disponiveis,
                format_func=lambda equipe_id: equipes_por_id[equipe_id].nome,
                key=chave_selecao,
            )
            confirmar_exclusao = st.checkbox(
                "Confirmo a exclusao das equipes selecionadas.",
                key=f"confirmar_exclusao_{st.session_state.form_excluir_equipes}",
            )
            st.caption(
                "Equipes com tentativas registradas nao podem ser excluidas."
            )
            if st.button(
                f"Excluir equipes selecionadas ({len(selecionadas)})",
                disabled=not selecionadas,
                type="primary",
            ):
                if not confirmar_exclusao:
                    st.error("Marque a confirmacao antes de excluir as equipes.")
                else:
                    try:
                        nomes_excluidos = excluir_equipes(db, selecionadas)
                    except (LookupError, RuntimeError, ValueError) as error:
                        st.error(str(error))
                    else:
                        st.session_state["equipe_admin_feedback"] = (
                            f"{len(nomes_excluidos)} equipes excluidas."
                        )
                        st.session_state.form_excluir_equipes += 1
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
    tags_disponiveis = (
        db.query(Tag)
        .filter(Tag.categoria != "dificuldade")
        .order_by(Tag.nome)
        .all()
    )
    opcoes_tags = [tag.nome for tag in tags_disponiveis]
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
            niveis_display = {
                "facil": "🟢 Fácil",
                "medio": "🟡 Médio",
                "dificil": "🔴 Difícil",
            }

            with st.form(f"nova_questao_{st.session_state.form_questao}"):
                nivel = st.selectbox(
                    "Dificuldade",
                    ["facil", "medio", "dificil"],
                    format_func=lambda n: niveis_display[n],
                    help=(
                        "A dificuldade é registrada como tag e não altera "
                        "a numeração da questão."
                    ),
                )
                tags_selecionadas = st.multiselect(
                    "Tags de disciplina e assunto",
                    options=opcoes_tags,
                )
                tags_personalizadas = st.text_input(
                    "Outras tags (separe por virgula)",
                    placeholder="Ex.: Aplicacoes, Invariantes",
                )
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
                        db.flush()
                        atualizar_tags_questao(
                            db,
                            questao,
                            nivel,
                            tags_selecionadas,
                            tags_personalizadas.split(","),
                        )
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

            questoes_sorted = ordenar_questoes(questoes)
            numeros_questoes = numerar_questoes(questoes_sorted)

            for q in questoes_sorted:
                with st.container(border=True):
                    header_col, edit_col, del_col = st.columns([5, 0.5, 0.5])
                    tags_questao = ", ".join(
                        sorted(tag.nome for tag in q.tags)
                    )
                    header_col.markdown(
                        f"**{rotulo_questao(q, numeros_questoes[q.id])}**"
                        + (f" · {tags_questao}" if tags_questao else "")
                    )
                    if edit_col.button("✏️", key=f"edit_questao_{q.id}", help="Editar questao"):
                        st.session_state[f"editing_questao_{q.id}"] = True
                    if del_col.button("🗑️", key=f"del_questao_{q.id}", help="Remover questao"):
                        db.delete(q)
                        db.commit()
                        st.rerun()
                    if st.session_state.get(f"editing_questao_{q.id}"):
                        niveis_keys = ["facil", "medio", "dificil"]
                        novo_nivel = st.selectbox(
                            "Dificuldade", niveis_keys,
                            index=niveis_keys.index(q.nivel) if q.nivel in niveis_keys else 0,
                            format_func=lambda n: niveis_display[n],
                            help=(
                                "A dificuldade é registrada como tag e não altera "
                                "a numeração da questão."
                            ),
                            key=f"novo_nivel_{q.id}",
                        )
                        tags_atribuidas = [
                            tag.nome
                            for tag in q.tags
                            if tag.categoria != "dificuldade"
                        ]
                        tags_selecionadas = st.multiselect(
                            "Tags de disciplina e assunto",
                            options=opcoes_tags,
                            default=[
                                nome
                                for nome in tags_atribuidas
                                if nome in opcoes_tags
                            ],
                            key=f"tags_questao_{q.id}",
                        )
                        tags_personalizadas = st.text_input(
                            "Outras tags (separe por virgula)",
                            key=f"tags_personalizadas_{q.id}",
                        )
                        novo_enunciado = st.text_area("Enunciado", value=q.enunciado or "", key=f"novo_enunciado_{q.id}")
                        c1, c2 = st.columns(2)
                        if c1.button("Salvar", key=f"save_questao_{q.id}", type="primary"):
                            q.enunciado = novo_enunciado.strip()
                            atualizar_tags_questao(
                                db,
                                q,
                                novo_nivel,
                                tags_selecionadas,
                                tags_personalizadas.split(","),
                            )
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

with tab_conta:
    st.markdown("#### Alterar senha de administrador")
    admin_account = db.get(User, user["id"])
    if admin_account is None:
        st.error("A conta de administrador nao foi encontrada.")
    else:
        with st.form("alterar_senha_admin"):
            current_password = st.text_input("Senha atual", type="password")
            new_password = st.text_input("Nova senha", type="password")
            confirmation = st.text_input("Confirme a nova senha", type="password")
            submitted = st.form_submit_button("Atualizar senha", type="primary")

        if submitted:
            if not verify_password(current_password, admin_account.password_hash):
                st.error("Senha atual incorreta.")
            else:
                error = password_validation_error(new_password, confirmation)
                if error:
                    st.error(error)
                elif verify_password(new_password, admin_account.password_hash):
                    st.error("A nova senha deve ser diferente da senha atual.")
                else:
                    change_password(admin_account, new_password)
                    db.commit()
                    st.success("Senha do administrador atualizada.")
                    st.rerun()

db.close()
