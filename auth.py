import bcrypt
import extra_streamlit_components as stx
import streamlit as st
from urllib.parse import urlparse

from login_sessions import (
    COOKIE_NAME,
    buscar_sessao_login,
    criar_sessao_login,
    revogar_sessao_login,
)

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_BYTES = 72
_PENDING_PASSWORD_CHANGE = "pending_password_change_user_id"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def password_validation_error(password: str, confirmation: str | None = None) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"A senha deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres."
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        return f"A senha nao pode ultrapassar {MAX_PASSWORD_BYTES} bytes."
    if confirmation is not None and password != confirmation:
        return "As senhas nao coincidem."
    return None


def change_password(user, password: str) -> None:
    error = password_validation_error(password)
    if error:
        raise ValueError(error)
    if verify_password(password, user.password_hash):
        raise ValueError("A nova senha deve ser diferente da senha atual.")

    user.password_hash = hash_password(password)
    user.must_change_password = False


def require_auth(allowed_roles: list[str]) -> dict | None:
    """Check if user is logged in with correct role. Returns user dict or None."""
    user = st.session_state.get("user")
    if user and user.get("role") in allowed_roles:
        return user
    return None


def _cookie_manager(key: str = "batalha_auth_cookie_manager"):
    return stx.CookieManager(key=key)


def _write_session_cookie(cookie_manager, token: str, expires_at) -> None:
    scheme = urlparse(getattr(st.context, "url", "")).scheme
    cookie_manager.set(
        COOKIE_NAME,
        token,
        key="batalha_auth_cookie_set",
        path="/",
        expires_at=expires_at,
        secure=scheme == "https",
        same_site="lax",
    )


def _delete_session_cookie(cookie_manager) -> None:
    cookies = cookie_manager.cookies or {}
    if COOKIE_NAME in cookies:
        cookie_manager.delete(COOKIE_NAME, key="batalha_auth_cookie_delete")
    else:
        cookie_manager.cookie_manager(
            method="delete",
            cookie=COOKIE_NAME,
            key="batalha_auth_cookie_delete",
        )


def _establish_login(db_session, user, cookie_manager) -> None:
    token, expires_at = criar_sessao_login(db_session, user.id)
    _write_session_cookie(cookie_manager, token, expires_at)
    st.session_state["auth_session_token"] = token
    st.session_state["user"] = {
        "id": user.id,
        "username": user.username,
        "role": user.role,
    }
    st.session_state.pop(_PENDING_PASSWORD_CHANGE, None)


def logout_user(db_session) -> None:
    token = st.session_state.pop("auth_session_token", None)
    if token is None:
        token = st.context.cookies.get(COOKIE_NAME)
    revogar_sessao_login(db_session, token)
    st.session_state.pop("user", None)
    st.session_state.pop(_PENDING_PASSWORD_CHANGE, None)
    cookie_manager = _cookie_manager("batalha_logout_cookie_manager")
    _delete_session_cookie(cookie_manager)


def _render_required_password_change(db_session, user, cookie_manager) -> bool:
    st.warning("Por seguranca, defina uma nova senha antes de continuar.")
    with st.form("required_password_change"):
        password = st.text_input("Nova senha", type="password")
        confirmation = st.text_input("Confirme a nova senha", type="password")
        submitted = st.form_submit_button("Salvar nova senha", type="primary")

    if not submitted:
        return False

    error = password_validation_error(password, confirmation)
    if error:
        st.error(error)
    elif verify_password(password, user.password_hash):
        st.error("A nova senha deve ser diferente da senha temporaria.")
    else:
        change_password(user, password)
        db_session.commit()
        _establish_login(db_session, user, cookie_manager)
        st.rerun()

    return False


def login_form(db_session, User):
    """Restore a short-lived browser login or display the username/password form."""
    session_user = st.session_state.get("user")
    token = st.session_state.get("auth_session_token")
    token_from_cookie = False
    if not token:
        cookie_value = st.context.cookies.get(COOKIE_NAME)
        token = (
            cookie_value
            if isinstance(cookie_value, str) and cookie_value
            else None
        )
        token_from_cookie = token is not None

    cookie_manager = None
    if token:
        login_session = buscar_sessao_login(db_session, token)
        user = (
            db_session.get(User, login_session.user_id)
            if login_session is not None
            else None
        )
        if login_session is not None and user is not None:
            if user.must_change_password:
                revogar_sessao_login(db_session, token)
                st.session_state.pop("auth_session_token", None)
                st.session_state.pop("user", None)
                st.session_state[_PENDING_PASSWORD_CHANGE] = user.id
                cookie_manager = _cookie_manager()
                _delete_session_cookie(cookie_manager)
            else:
                st.session_state["auth_session_token"] = token
                st.session_state["user"] = {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role,
                }
                return True
        else:
            if login_session is not None:
                revogar_sessao_login(db_session, token)
            st.session_state.pop("auth_session_token", None)
            st.session_state.pop("user", None)
            if token_from_cookie:
                cookie_manager = _cookie_manager()
                _delete_session_cookie(cookie_manager)
            st.warning("Sua sessao expirou ou nao esta mais disponivel. Entre novamente.")
    elif session_user:
        st.session_state.pop("user", None)
        st.warning("Entre novamente para iniciar uma sessao segura.")

    pending_user_id = st.session_state.get(_PENDING_PASSWORD_CHANGE)
    if pending_user_id is not None:
        user = db_session.get(User, pending_user_id)
        if user is None:
            st.session_state.pop(_PENDING_PASSWORD_CHANGE, None)
            st.warning("Sua conta nao esta mais disponivel. Entre novamente.")
        else:
            if cookie_manager is None:
                cookie_manager = _cookie_manager()
            return _render_required_password_change(
                db_session, user, cookie_manager
            )

    if cookie_manager is None:
        cookie_manager = _cookie_manager()

    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Outfit:wght@300;400;600;700&display=swap');
        </style>
        <div style="text-align:center; padding:2rem 0 1rem;">
            <div style="font-family:'Bebas Neue',sans-serif; font-size:3rem; letter-spacing:3px;
                        background:linear-gradient(135deg,#f7971e,#ffd200); -webkit-background-clip:text;
                        -webkit-text-fill-color:transparent;">BATALHA OLIMPICA</div>
            <div style="font-family:'Outfit',sans-serif; color:#888; font-size:0.95rem; margin-top:4px;">
                Acesso restrito</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input(
                "Usuario",
                placeholder="Digite seu usuario",
                autocomplete="username",
            )
            password = st.text_input(
                "Senha",
                type="password",
                placeholder="Digite sua senha",
                autocomplete="current-password",
            )
            submitted = st.form_submit_button(
                "Entrar",
                use_container_width=True,
                type="primary",
            )

        if submitted:
            if not username or not password:
                st.error("Preencha usuario e senha.")
            else:
                user = db_session.query(User).filter_by(username=username).first()
                if user and verify_password(password, user.password_hash):
                    if user.must_change_password:
                        st.session_state[_PENDING_PASSWORD_CHANGE] = user.id
                        st.rerun()
                    _establish_login(db_session, user, cookie_manager)
                    return True
                st.error("Usuario ou senha incorretos.")
    return False
