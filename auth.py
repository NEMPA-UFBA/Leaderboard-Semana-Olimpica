import bcrypt
import streamlit as st

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


def _render_required_password_change(db_session, user) -> None:
    st.warning("Por seguranca, defina uma nova senha antes de continuar.")
    with st.form("required_password_change"):
        password = st.text_input("Nova senha", type="password")
        confirmation = st.text_input("Confirme a nova senha", type="password")
        submitted = st.form_submit_button("Salvar nova senha", type="primary")

    if not submitted:
        return

    error = password_validation_error(password, confirmation)
    if error:
        st.error(error)
    elif verify_password(password, user.password_hash):
        st.error("A nova senha deve ser diferente da senha temporaria.")
    else:
        change_password(user, password)
        db_session.commit()
        st.session_state["user"] = {
            "id": user.id,
            "username": user.username,
            "role": user.role,
        }
        st.session_state.pop(_PENDING_PASSWORD_CHANGE, None)
        st.success("Senha atualizada.")
        st.rerun()


def login_form(db_session, User):
    """Display login form and authenticate user. Returns True if logged in."""
    session_user = st.session_state.get("user")
    if session_user:
        user = db_session.get(User, session_user["id"])
        if user is None:
            st.session_state.pop("user", None)
            st.warning("Sua conta nao esta mais disponivel. Entre novamente.")
        elif user.must_change_password:
            st.session_state.pop("user", None)
            st.session_state[_PENDING_PASSWORD_CHANGE] = user.id
        else:
            return True

    pending_user_id = st.session_state.get(_PENDING_PASSWORD_CHANGE)
    if pending_user_id is not None:
        user = db_session.get(User, pending_user_id)
        if user is None:
            st.session_state.pop(_PENDING_PASSWORD_CHANGE, None)
            st.warning("Sua conta nao esta mais disponivel. Entre novamente.")
        else:
            _render_required_password_change(db_session, user)
            return False

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
        username = st.text_input("Usuario", placeholder="Digite seu usuario")
        password = st.text_input("Senha", type="password", placeholder="Digite sua senha")

        if st.button("Entrar", use_container_width=True, type="primary"):
            if not username or not password:
                st.error("Preencha usuario e senha.")
            else:
                user = db_session.query(User).filter_by(username=username).first()
                if user and verify_password(password, user.password_hash):
                    if user.must_change_password:
                        st.session_state[_PENDING_PASSWORD_CHANGE] = user.id
                        st.rerun()
                    st.session_state["user"] = {
                        "id": user.id,
                        "username": user.username,
                        "role": user.role,
                    }
                    st.rerun()
                else:
                    st.error("Usuario ou senha incorretos.")
    return False
