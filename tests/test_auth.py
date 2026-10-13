from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from auth import (
    change_password,
    hash_password,
    password_validation_error,
    verify_password,
)


def test_hash_and_verify_password():
    password = "senha123"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("errada", hashed) is False


def test_password_validation_requires_minimum_length():
    assert password_validation_error("curta") is not None
    assert password_validation_error("senha-com-12+") is None


def test_password_validation_checks_confirmation_and_bcrypt_limit():
    assert password_validation_error("senha-forte-123", "senha-forte-321") == (
        "As senhas nao coincidem."
    )
    assert password_validation_error("a" * 73) == "A senha nao pode ultrapassar 72 bytes."


def test_change_password_clears_forced_change_flag():
    user = SimpleNamespace(
        password_hash=hash_password("temporary-password"),
        must_change_password=True,
    )
    new_password = "new-secure-password-123"

    change_password(user, new_password)

    assert verify_password(new_password, user.password_hash)
    assert user.must_change_password is False


def test_change_password_rejects_reusing_current_password():
    current_password = "current-secure-password"
    user = SimpleNamespace(
        password_hash=hash_password(current_password),
        must_change_password=True,
    )

    with pytest.raises(ValueError, match="diferente da senha atual"):
        change_password(user, current_password)


def test_forced_password_change_survives_streamlit_reruns(tmp_path):
    database_path = str(tmp_path / "auth-flow.sqlite")
    app = AppTest.from_string(
        f"""
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from auth import hash_password, login_form
from models import Base, User

@st.cache_resource
def get_session_factory():
    engine = create_engine("sqlite:///" + {database_path!r})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        if not db.query(User).filter_by(username="admin").first():
            db.add(User(
                username="admin",
                password_hash=hash_password("temporary-bootstrap-password"),
                role="admin",
                must_change_password=True,
            ))
    return factory

db = get_session_factory()()
if login_form(db, User):
    st.success("LOGIN_OK")
    if st.button("Sair"):
        st.session_state.pop("user", None)
        st.rerun()
db.close()
"""
    ).run()

    app.text_input[0].set_value("admin")
    app.text_input[1].set_value("temporary-bootstrap-password")
    app.button[0].click().run()
    assert app.warning[0].value.startswith("Por seguranca")

    new_password = "brand-new-test-password-456"
    app.text_input[0].set_value(new_password)
    app.text_input[1].set_value(new_password)
    app.button[0].click().run()
    assert app.success[0].value == "LOGIN_OK"
    assert not app.exception

    app.button[0].click().run()
    app.text_input[0].set_value("admin")
    app.text_input[1].set_value(new_password)
    app.button[0].click().run()
    assert app.success[0].value == "LOGIN_OK"
    assert not app.exception
