import logging
import streamlit as st
from sqlalchemy.orm import load_only
from streamlit.errors import StreamlitInvalidLayoutContextError

from auth import require_auth
from database import get_db
from models import AuditLog, User, Equipe, Regata, Questao, Tentativa
from question_locking import (
    forcar_assuncao_lock,
    liberar_reserva_ao_sair_da_tela,
    liberar_reserva_ao_trocar_equipe,
    liberar_reserva_questao,
    limpar_locks_expirados,
    obter_ou_renovar_reserva_questao,
    reservar_questao,
)
from question_utils import numerar_questoes, ordenar_questoes, rotulo_questao
from scoring import corrigir_tentativa, excluir_tentativa, registrar_tentativa
from team_utils import ordenar_equipes
from time_utils import formatar_horario_do_evento

logger = logging.getLogger(__name__)


def _rerun_workflow_fragment() -> None:
    try:
        st.rerun(scope="fragment")
    except StreamlitInvalidLayoutContextError:
        st.rerun()


@st.fragment(run_every="60s")
def render_judge_workflow(
    session_token: str,
) -> None:
    with get_db() as db:
        limpar_locks_expirados(db)
        authenticated_user = require_auth(["juiz", "admin"])
        account = (
            db.get(User, authenticated_user["id"])
            if authenticated_user
            else None
        )
        if (
            account is None
            or account.role not in ("juiz", "admin")
            or account.must_change_password
        ):
            liberar_reserva_ao_sair_da_tela(db, st.session_state)
            st.session_state.pop("user", None)
            st.warning("Sua sessao nao esta mais autorizada. Entre novamente.")
            return
        user = {
            "id": account.id,
            "username": account.username,
            "role": account.role,
        }
        nome_exibicao = account.nome or account.username

        regata = db.query(Regata).filter_by(ativa=True).first()
        if not regata:
            st.warning(
                "Nenhuma regata ativa no momento. Aguarde o admin ativar uma regata."
            )
            liberar_reserva_ao_sair_da_tela(db, st.session_state)
            return

        st.markdown(f"**Regata:** {regata.nome}")
        st.divider()
        equipes = ordenar_equipes(
            db.query(Equipe)
            .options(load_only(Equipe.id, Equipe.nome))
            .all()
        )
        questoes = ordenar_questoes(
            db.query(Questao)
            .filter_by(regata_id=regata.id)
            .options(
                load_only(Questao.id, Questao.regata_id, Questao.nivel)
            )
            .all()
        )
        numeros_questoes = numerar_questoes(questoes)
        if not equipes:
            st.warning("Nenhuma equipe cadastrada.")
            liberar_reserva_ao_sair_da_tela(db, st.session_state)
            return
        if not questoes:
            st.warning("Nenhuma questao nesta regata.")
            liberar_reserva_ao_sair_da_tela(db, st.session_state)
            return

        processing_action = st.session_state.get("processing_action", False)

        ids_questoes = [questao.id for questao in questoes]
        equipes_por_id = {equipe.id: equipe for equipe in equipes}
        questoes_por_id = {questao.id: questao for questao in questoes}

        # ── blindagem definitiva contra state‑bleeding ──────────────────
        # O Streamlit, em edge‑cases com fragmentos, armazena a string do
        # format_func (ex: "Time Xi  ✓") em vez do ID inteiro.  O bloco
        # abaixo normaliza o valor SEMPRE para int antes de qualquer uso.
        _raw_equipe = st.session_state.get("juiz_equipe_id")
        if not isinstance(_raw_equipe, int) or _raw_equipe not in equipes_por_id:
            corrigido = False
            if isinstance(_raw_equipe, str):
                for eid, eq in equipes_por_id.items():
                    if eq.nome in _raw_equipe:
                        logger.warning(
                            "juiz_equipe_id continha string (%s) — "
                            "recuperado para int %d (%s).",
                            _raw_equipe, eid, eq.nome,
                        )
                        st.session_state["juiz_equipe_id"] = eid
                        corrigido = True
                        break
            if not corrigido:
                logger.warning(
                    "juiz_equipe_id invalido (%s), resetando para primeira equipe.",
                    _raw_equipe,
                )
                st.session_state["juiz_equipe_id"] = next(iter(equipes_por_id))

        _raw_questao = st.session_state.get("juiz_questao_id")
        if not isinstance(_raw_questao, int) or _raw_questao not in ids_questoes:
            logger.warning(
                "juiz_questao_id invalido (%s), resetando para primeira questao.",
                _raw_questao,
            )
            st.session_state["juiz_questao_id"] = ids_questoes[0]

        questao_preselecionada_id = st.session_state.get(
            "juiz_questao_id", ids_questoes[0]
        )
        equipes_com_tentativas = {
            equipe_id
            for (equipe_id,) in (
                db.query(Tentativa.equipe_id)
                .filter(Tentativa.questao_id == questao_preselecionada_id)
                .distinct()
                .all()
            )
        }

        col_eq, col_qt = st.columns(2, gap="large")
        with col_eq:
            equipe_id = st.selectbox(
                "Equipe",
                [equipe.id for equipe in equipes],
                format_func=lambda id_: (
                    f"{equipes_por_id[id_].nome}"
                    + ("  ✓" if id_ in equipes_com_tentativas else "")
                ),
                key="juiz_equipe_id",
            )
            st.caption(
                "✓ indica que a equipe ja tem tentativa nesta questao."
            )
        with col_qt:
            questao_id = st.selectbox(
                "Questao",
                ids_questoes,
                format_func=lambda id_: rotulo_questao(
                    questoes_por_id[id_], numeros_questoes[id_]
                ),
                key="juiz_questao_id",
            )
        # ── Blindagem pós‑selectbox ──────────────────────────────────
        # Força o valor armazenado a ser int.  Se o Streamlit vazou a
        # string do format_func ("Time Xi  ✓"), recupera o ID pelo nome.
        _equipe_val = st.session_state.get("juiz_equipe_id")
        if not isinstance(_equipe_val, int):
            for eid, eq in equipes_por_id.items():
                if isinstance(_equipe_val, str) and eq.nome in _equipe_val:
                    st.session_state["juiz_equipe_id"] = eid
                    break
            else:
                st.session_state["juiz_equipe_id"] = next(iter(equipes_por_id))

        _questao_val = st.session_state.get("juiz_questao_id")
        if not isinstance(_questao_val, int):
            if isinstance(_questao_val, str) and _questao_val.isdigit():
                st.session_state["juiz_questao_id"] = int(_questao_val)
            else:
                st.session_state["juiz_questao_id"] = ids_questoes[0]

        equipe_id = st.session_state["juiz_equipe_id"]
        questao_id = st.session_state["juiz_questao_id"]

        equipe_nome = equipes_por_id[equipe_id].nome
        questao_lock_atual = st.session_state.get("question_lock_id")
        contexto_anterior = st.session_state.get("judge_panel_context")
        if contexto_anterior != (equipe_id, questao_id):
            if (
                contexto_anterior is not None
                and contexto_anterior[0] != equipe_id
                and contexto_anterior[1] == questao_id
            ):
                liberar_reserva_ao_trocar_equipe(
                    db,
                    st.session_state,
                    contexto_anterior[0],
                    equipe_id,
                    questao_id,
                    session_token,
                )
            st.session_state["judge_panel_context"] = (equipe_id, questao_id)
            st.session_state.pop("judge_feedback", None)
            st.session_state.pop("editing_attempt_id", None)
            st.session_state["correction_form_revision"] = (
                st.session_state.get("correction_form_revision", 0) + 1
            )

        if questao_lock_atual != questao_id:
            if questao_lock_atual is not None:
                logger.info(
                    "UI | troca_questao | liberando questao=%d para assumir=%d",
                    questao_lock_atual, questao_id,
                )
                liberar_reserva_questao(db, questao_lock_atual, session_token)

        estado_lock = obter_ou_renovar_reserva_questao(
            db,
            questao_id,
            user["id"],
            nome_exibicao,
            session_token,
        )
        st.session_state["question_lock_id"] = questao_id
        st.session_state["question_lock_owned"] = estado_lock["lock_owned"]
        st.session_state["question_lock_owner"] = estado_lock["lock_owner"]
        st.session_state["question_lock_lost"] = estado_lock["lock_lost"]
        if estado_lock["lock_message"]:
            st.session_state["question_lock_message"] = estado_lock["lock_message"]
        else:
            st.session_state.pop("question_lock_message", None)

        lock_owned = st.session_state.get("question_lock_owned", False)
        if lock_owned:
            st.success(
                f"Questao reservada para {nome_exibicao}; a reserva e renovada "
                "automaticamente enquanto esta tela estiver aberta."
            )
            if st.button("Liberar esta questao", key=f"liberar_questao_{questao_id}"):
                logger.info(
                    "UI | btn_liberar | questao=%d juiz_id=%d",
                    questao_id, user["id"],
                )
                liberada = liberar_reserva_questao(
                    db, questao_id, session_token
                )
                st.session_state["question_lock_owned"] = False
                st.session_state["question_lock_owner"] = None
                st.session_state["question_lock_lost"] = False
                lock_owned = False
                if liberada:
                    st.info("Questao liberada.")
                else:
                    st.warning("A reserva ja nao estava ativa nesta sessao.")
        else:
            responsavel = st.session_state.get("question_lock_owner")
            if responsavel:
                st.warning(
                    f"Questao reservada por {responsavel}. "
                    "Os lancamentos e correcoes estao desabilitados. A reserva "
                    "expira apos 90 segundos sem renovacao."
                )
            elif st.session_state.get("question_lock_lost"):
                st.warning(
                    "Sua reserva expirou ou foi liberada. Assuma a questao "
                    "novamente antes de lancar ou corrigir resultados."
                )
            else:
                st.info("Esta questao esta sem responsavel. Assuma-a para iniciar.")

            if st.button("Assumir questao", key=f"assumir_questao_{questao_id}"):
                logger.info(
                    "UI | btn_assumir | questao=%d juiz_id=%d nome=%s",
                    questao_id, user["id"], nome_exibicao,
                )
                try:
                    reserva = forcar_assuncao_lock(
                        db,
                        questao_id,
                        user["id"],
                        nome_exibicao,
                        session_token,
                    )
                    st.session_state["question_lock_owned"] = reserva["reservada"]
                    st.session_state["question_lock_owner"] = (
                        nome_exibicao if reserva["reservada"] else reserva["nome_ator"]
                    )
                    st.session_state["question_lock_lost"] = False
                    if reserva["reservada"]:
                        st.session_state["judge_feedback"] = {
                            "tipo": "sucesso",
                            "mensagem": "Questao assumida com sucesso.",
                        }
                    else:
                        st.session_state["judge_feedback"] = {
                            "tipo": "erro",
                            "mensagem": (
                                f"A questao ainda esta reservada por "
                                f"{reserva['nome_ator']}. A reserva expira apos "
                                "90 segundos sem renovacao."
                            ),
                        }
                except Exception:
                    logger.exception(
                        "UI | btn_assumir | ERRO | questao=%d juiz_id=%d",
                        questao_id, user["id"],
                    )
                    st.session_state["judge_feedback"] = {
                        "tipo": "erro",
                        "mensagem": "Erro ao assumir a questao. Tente novamente.",
                    }
                _rerun_workflow_fragment()
            mensagem_reserva = st.session_state.get("question_lock_message")
            if mensagem_reserva:
                st.warning(mensagem_reserva)

        st.divider()
        numero_questao = numeros_questoes[questao_id]
        feedback = st.session_state.pop("judge_feedback", None)
        if feedback:
            if feedback["tipo"] == "erro":
                st.error(feedback["mensagem"])
            elif feedback["tipo"] == "aviso":
                st.warning(feedback["mensagem"])
            else:
                st.success(feedback["mensagem"])
                if feedback.get("celebrar"):
                    st.balloons()

        tentativas = (
            db.query(Tentativa)
            .filter_by(equipe_id=equipe_id, questao_id=questao_id)
            .options(
                load_only(
                    Tentativa.id, Tentativa.equipe_id, Tentativa.questao_id,
                    Tentativa.numero, Tentativa.acertou, Tentativa.pontos,
                    Tentativa.juiz_id, Tentativa.created_at,
                )
            )
            .order_by(Tentativa.numero)
            .all()
        )
        ja_acertou = any(tentativa.acertou for tentativa in tentativas)
        quantidade = len(tentativas)

        lock_owned = st.session_state.get("question_lock_owned", False)
        botoes_disabled = not lock_owned or processing_action

        if ja_acertou:
            acerto = next(tentativa for tentativa in tentativas if tentativa.acertou)
            st.markdown(
                f"""
                <div style="background:linear-gradient(135deg,#1b5e20,#2e7d32); border-radius:12px; padding:1.5rem;
                            text-align:center; margin-bottom:1rem;">
                    <div style="font-family:'Bebas Neue',sans-serif; font-size:1.8rem; color:#a5d6a7;
                                letter-spacing:2px;">JA ACERTOU!</div>
                    <div style="font-family:'Outfit',sans-serif; color:#e8f5e9; font-size:1rem; margin-top:4px;">
                        Tentativa {acerto.numero} — +{acerto.pontos} pontos</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif quantidade >= 3:
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
            proxima = quantidade + 1
            pontos_possiveis = {1: 100, 2: 80, 3: 50}
            pontos = ""
            for numero in range(1, 4):
                if numero <= quantidade:
                    pontos += '<span style="color:#888; font-size:1.5rem; margin:0 4px;">●</span>'
                elif numero == proxima:
                    pontos += '<span style="color:#ddd; font-size:1.5rem; margin:0 4px;">●</span>'
                else:
                    pontos += '<span style="color:#555; font-size:1.5rem; margin:0 4px;">○</span>'

            st.markdown(
                f"""
                <div style="background:linear-gradient(135deg,#1a1a2e,#16213e); border:1px solid #333;
                            border-radius:12px; padding:1.5rem; text-align:center; margin-bottom:1rem;">
                    <div style="margin-bottom:8px;">{pontos}</div>
                    <div style="font-family:'Outfit',sans-serif; color:#ccc; font-size:1rem;">
                        {proxima}a tentativa — vale <strong style="color:#ffd200;">{pontos_possiveis[proxima]} pontos</strong></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            col_acertou, col_errou = st.columns(2, gap="large")
            with col_acertou:
                if st.button(
                    "✅ ACERTOU",
                    key="btn_acertou",
                    use_container_width=True,
                    type="primary",
                    disabled=botoes_disabled,
                ):
                    st.session_state["processing_action"] = True
                    with st.spinner("Registrando acerto..."):
                        if equipe_id not in equipes_por_id or questao_id not in ids_questoes:
                            logger.error(
                                "State bleeding detectado no btn_acertou: "
                                "equipe_id=%s questao_id=%s",
                                equipe_id,
                                questao_id,
                            )
                            st.session_state["judge_feedback"] = {
                                "tipo": "erro",
                                "mensagem": (
                                    "A selecao de equipe ou questao foi perdida "
                                    "durante o refresh da tela. Selecione novamente."
                                ),
                            }
                        else:
                            try:
                                result = registrar_tentativa(
                                    db,
                                    equipe_id,
                                    questao_id,
                                    True,
                                    user["id"],
                                    session_token,
                                )
                                if "erro" in result:
                                    st.session_state["judge_feedback"] = {
                                        "tipo": "erro",
                                        "mensagem": result["erro"],
                                    }
                                else:
                                    st.session_state["judge_feedback"] = {
                                        "tipo": "sucesso",
                                        "mensagem": (
                                            f"**{equipe_nome}** — **Questão {numero_questao}** — "
                                            f"{result['numero']}a tentativa — "
                                            f"**+{result['pontos']} pontos!**"
                                        ),
                                        "celebrar": True,
                                    }
                                    st.session_state["leaderboard_dirty"] = True
                            except Exception:
                                logger.exception(
                                    "Erro ao registrar tentativa (acerto). "
                                    "equipe=%d questao=%d juiz=%d",
                                    equipe_id,
                                    questao_id,
                                    user["id"],
                                )
                                st.session_state["judge_feedback"] = {
                                    "tipo": "erro",
                                    "mensagem": (
                                        "Erro inesperado ao registrar a tentativa. "
                                        "Tente novamente ou recarregue a pagina."
                                    ),
                                }
                    st.session_state["processing_action"] = False
                    _rerun_workflow_fragment()

            with col_errou:
                if st.button(
                    "❌ ERROU",
                    key="btn_errou",
                    use_container_width=True,
                    disabled=botoes_disabled,
                ):
                    st.session_state["processing_action"] = True
                    with st.spinner("Registrando tentativa..."):
                        if equipe_id not in equipes_por_id or questao_id not in ids_questoes:
                            logger.error(
                                "State bleeding detectado no btn_errou: "
                                "equipe_id=%s questao_id=%s",
                                equipe_id,
                                questao_id,
                            )
                            st.session_state["judge_feedback"] = {
                                "tipo": "erro",
                                "mensagem": (
                                    "A selecao de equipe ou questao foi perdida "
                                    "durante o refresh da tela. Selecione novamente."
                                ),
                            }
                        else:
                            try:
                                result = registrar_tentativa(
                                    db,
                                    equipe_id,
                                    questao_id,
                                    False,
                                    user["id"],
                                    session_token,
                                )
                                if "erro" in result:
                                    st.session_state["judge_feedback"] = {
                                        "tipo": "erro",
                                        "mensagem": result["erro"],
                                    }
                                else:
                                    restantes = 3 - result["numero"]
                                    st.session_state["judge_feedback"] = {
                                        "tipo": "aviso",
                                        "mensagem": (
                                            f"**{equipe_nome}** — **Questão {numero_questao}** — "
                                            f"Errou tentativa {result['numero']}. "
                                            f"Restam {restantes} tentativa(s)."
                                        ),
                                    }
                                    st.session_state["leaderboard_dirty"] = True
                            except Exception:
                                logger.exception(
                                    "Erro ao registrar tentativa (erro). "
                                    "equipe=%d questao=%d juiz=%d",
                                    equipe_id,
                                    questao_id,
                                    user["id"],
                                )
                                st.session_state["judge_feedback"] = {
                                    "tipo": "erro",
                                    "mensagem": (
                                        "Erro inesperado ao registrar a tentativa. "
                                        "Tente novamente ou recarregue a pagina."
                                    ),
                                }
                    st.session_state["processing_action"] = False
                    _rerun_workflow_fragment()

        if not tentativas:
            return

        st.divider()
        st.markdown("#### Historico de tentativas")
        auditorias = (
            db.query(AuditLog)
            .filter(
                AuditLog.tentativa_id.in_([tentativa.id for tentativa in tentativas]),
                AuditLog.acao == "correcao",
            )
            .options(
                load_only(
                    AuditLog.id, AuditLog.tentativa_id, AuditLog.ator_id,
                    AuditLog.ator_role, AuditLog.created_at,
                )
            )
            .order_by(AuditLog.id)
            .all()
        )
        usuarios_referenciados = {
            tentativa.juiz_id for tentativa in tentativas
        } | {auditoria.ator_id for auditoria in auditorias}
        nomes_usuarios = {
            usuario.id: usuario.nome or usuario.username
            for usuario in db.query(User)
            .filter(User.id.in_(usuarios_referenciados))
            .options(load_only(User.id, User.nome, User.username))
            .all()
        }
        correcoes_por_tentativa = {}
        st.session_state.setdefault("correction_form_revision", 0)
        for auditoria in auditorias:
            correcoes_por_tentativa.setdefault(auditoria.tentativa_id, []).append(
                auditoria
            )

        for tentativa in tentativas:
            with st.container(border=True):
                status_icon = "✅" if tentativa.acertou else "❌"
                c1, c2, c3 = st.columns([5, 1, 1])
                c1.markdown(
                    f"**Tentativa {tentativa.numero}** — {status_icon} "
                    f"{'Acertou' if tentativa.acertou else 'Errou'} — "
                    f"**{tentativa.pontos} pts**"
                )
                nome_registrante = nomes_usuarios.get(
                    tentativa.juiz_id, "usuario removido"
                )
                c1.caption(f"Registrada por {nome_registrante}")
                if tentativa.created_at:
                    c1.caption(
                        "Registrada em "
                        f"{formatar_horario_do_evento(tentativa.created_at)} "
                        "(horario de Brasilia)"
                    )

                correcoes = correcoes_por_tentativa.get(tentativa.id, [])
                if correcoes:
                    ultima_correcao = correcoes[-1]
                    nome_corretor = nomes_usuarios.get(
                        ultima_correcao.ator_id, "usuario removido"
                    )
                    c1.caption(
                        f"Corrigida {len(correcoes)} vez(es); ultima correcao por "
                        f"{nome_corretor} ({ultima_correcao.ator_role}) em "
                        f"{formatar_horario_do_evento(ultima_correcao.created_at)} "
                        "(horario de Brasilia)"
                    )

                if c2.button(
                    "Corrigir",
                    key=f"corrigir_{tentativa.id}",
                    disabled=botoes_disabled,
                ):
                    st.session_state["processing_action"] = True
                    st.session_state["editing_attempt_id"] = tentativa.id

                if st.session_state.get("editing_attempt_id") == tentativa.id:
                    revision = st.session_state["correction_form_revision"]
                    with st.form(f"correcao_tentativa_{tentativa.id}_{revision}"):
                        novo_resultado = st.radio(
                            "Resultado correto",
                            options=[True, False],
                            index=0 if tentativa.acertou else 1,
                            format_func=lambda resultado: (
                                "Acertou" if resultado else "Errou"
                            ),
                            key=f"resultado_correcao_{tentativa.id}_{revision}",
                        )
                        salvar_coluna, cancelar_coluna = st.columns(2)
                        confirmar = salvar_coluna.form_submit_button(
                            "Salvar correção",
                            type="primary",
                            disabled=not lock_owned,
                        )
                        cancelar = cancelar_coluna.form_submit_button("Cancelar")

                    if cancelar:
                        st.session_state.pop("editing_attempt_id", None)
                        st.session_state["correction_form_revision"] += 1
                        _rerun_workflow_fragment()
                    if confirmar:
                        try:
                            result = corrigir_tentativa(
                                db,
                                tentativa.id,
                                user["id"],
                                user["role"],
                                novo_resultado,
                                session_token,
                            )
                            if "erro" in result:
                                st.session_state["judge_feedback"] = {
                                    "tipo": "erro",
                                    "mensagem": result["erro"],
                                }
                            else:
                                st.session_state["judge_feedback"] = {
                                    "tipo": "sucesso",
                                    "mensagem": (
                                        f"Resultado da tentativa {tentativa.numero} "
                                        "atualizado."
                                    ),
                                }
                                st.session_state.pop("editing_attempt_id", None)
                                st.session_state["correction_form_revision"] += 1
                                st.session_state["leaderboard_dirty"] = True
                        except LookupError as error:
                            st.session_state["judge_feedback"] = {
                                "tipo": "erro",
                                "mensagem": str(error),
                            }
                        except Exception:
                            logger.exception(
                                "Erro ao corrigir tentativa. "
                                "tentativa=%d juiz=%d",
                                tentativa.id,
                                user["id"],
                            )
                            st.session_state["judge_feedback"] = {
                                "tipo": "erro",
                                "mensagem": (
                                    "Erro inesperado ao corrigir a tentativa. "
                                    "Tente novamente ou recarregue a pagina."
                                ),
                            }
                        st.session_state["processing_action"] = False
                        _rerun_workflow_fragment()

                if c3.button(
                    "Excluir",
                    key=f"excluir_{tentativa.id}",
                    type="primary",
                    disabled=botoes_disabled,
                ):
                    st.session_state["processing_action"] = True
                    try:
                        result = excluir_tentativa(
                            db,
                            tentativa.id,
                            user["id"],
                            user["role"],
                            session_token,
                        )
                        if result and "erro" in result:
                            st.session_state["judge_feedback"] = {
                                "tipo": "erro",
                                "mensagem": result["erro"],
                            }
                        else:
                            st.session_state["judge_feedback"] = {
                                "tipo": "sucesso",
                                "mensagem": "Tentativa excluida.",
                            }
                            st.session_state["leaderboard_dirty"] = True
                    except LookupError as error:
                        st.session_state["judge_feedback"] = {
                            "tipo": "erro",
                            "mensagem": str(error),
                        }
                    except Exception:
                        logger.exception(
                            "Erro ao excluir tentativa. "
                            "tentativa=%d juiz=%d",
                            tentativa.id,
                            user["id"],
                        )
                        st.session_state["judge_feedback"] = {
                            "tipo": "erro",
                            "mensagem": (
                                "Erro inesperado ao excluir a tentativa. "
                                "Tente novamente ou recarregue a pagina."
                            ),
                        }
                    st.session_state["processing_action"] = False
                    _rerun_workflow_fragment()
