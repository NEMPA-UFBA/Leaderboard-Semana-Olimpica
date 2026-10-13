import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, make_url
from sqlalchemy.orm import sessionmaker

from database import _normalize_database_url
from models import Equipe, Questao, QuestaoLock, Regata, Tentativa, User
from question_locking import renovar_reserva_questao, reservar_questao
from scoring import _lock_equipe_questao, registrar_tentativa

TEST_DATABASE_URL = os.environ.get("POSTGRES_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Configure POSTGRES_TEST_DATABASE_URL para testar concorrencia em PostgreSQL.",
)


def test_dois_juizes_recebem_numeros_sequenciais_sem_colisao():
    url = make_url(TEST_DATABASE_URL)
    if not url.drivername.startswith("postgresql"):
        pytest.fail("POSTGRES_TEST_DATABASE_URL deve apontar para PostgreSQL.")
    database_name_identifies_test = "test" in (url.database or "").casefold()
    branch_explicitly_confirmed = (
        os.environ.get("POSTGRES_TEST_BRANCH_CONFIRMED") == "1"
    )
    if not database_name_identifies_test and not branch_explicitly_confirmed:
        pytest.fail(
            "Por seguranca, confirme a branch de teste definindo "
            "POSTGRES_TEST_BRANCH_CONFIRMED=1."
        )

    engine = create_engine(
        _normalize_database_url(TEST_DATABASE_URL),
        pool_size=3,
    )
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    token = uuid4().hex
    ids = None

    try:
        with TestSession() as db:
            juiz_1 = User(
                username=f"test_judge_1_{token}",
                password_hash="test",
                role="juiz",
            )
            juiz_2 = User(
                username=f"test_judge_2_{token}",
                password_hash="test",
                role="juiz",
            )
            equipe = Equipe(nome=f"test_team_{token}")
            regata = Regata(nome=f"test_regatta_{token}")
            db.add_all([juiz_1, juiz_2, equipe, regata])
            db.flush()
            questao = Questao(
                regata_id=regata.id,
                nivel="facil",
                enunciado="PostgreSQL concurrency test",
            )
            outra_questao = Questao(
                regata_id=regata.id,
                nivel="medio",
                enunciado="Independent question concurrency test",
            )
            db.add_all([questao, outra_questao])
            db.commit()
            ids = (
                juiz_1.id,
                juiz_2.id,
                equipe.id,
                questao.id,
                regata.id,
                outra_questao.id,
            )

        start = Barrier(2)

        def submit(juiz_id):
            with TestSession() as db:
                start.wait()
                return registrar_tentativa(
                    db, ids[2], ids[3], False, juiz_id
                )

        def submit_other_question(test_ids):
            with TestSession() as db:
                return registrar_tentativa(
                    db, test_ids[2], test_ids[5], False, test_ids[0]
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, ids[:2]))

        assert all("erro" not in result for result in results), results
        assert sorted(result["numero"] for result in results) == [1, 2]

        with TestSession() as db:
            attempts = (
                db.query(Tentativa)
                .filter_by(equipe_id=ids[2], questao_id=ids[3])
                .order_by(Tentativa.numero)
                .all()
            )
            assert [attempt.numero for attempt in attempts] == [1, 2]

        with TestSession() as holder:
            assert _lock_equipe_questao(holder, ids[2], ids[3])
            pool = ThreadPoolExecutor(max_workers=1)
            future = pool.submit(submit_other_question, ids)
            try:
                result = future.result(timeout=5)
                assert result["numero"] == 1
            finally:
                holder.rollback()
                pool.shutdown(wait=True)

        reservation_start = Barrier(2)

        def reserve(juiz_id):
            session_token = uuid4().hex
            with TestSession() as db:
                reservation_start.wait()
                result = reservar_questao(
                    db,
                    ids[3],
                    juiz_id,
                    f"test_judge_{juiz_id}",
                    session_token,
                )
                return result, session_token

        with ThreadPoolExecutor(max_workers=2) as pool:
            reservations = list(pool.map(reserve, ids[:2]))

        assert sum(result["reservada"] for result, _ in reservations) == 1
        winner_index = next(
            index
            for index, (result, _) in enumerate(reservations)
            if result["reservada"]
        )
        winner_id = ids[winner_index]
        old_session_token = reservations[winner_index][1]
        new_session_token = uuid4().hex
        with TestSession() as db:
            retaken = reservar_questao(
                db,
                ids[3],
                winner_id,
                f"test_judge_{winner_id}",
                new_session_token,
            )
            assert retaken["reservada"] is True
            assert (
                renovar_reserva_questao(db, ids[3], old_session_token)
                is False
            )
            assert (
                renovar_reserva_questao(db, ids[3], new_session_token)
                is True
            )
    finally:
        if ids is not None:
            with TestSession() as db:
                db.query(QuestaoLock).filter(
                    QuestaoLock.questao_id.in_([ids[3], ids[5]])
                ).delete(synchronize_session=False)
                db.query(Tentativa).filter_by(equipe_id=ids[2]).delete(
                    synchronize_session=False
                )
                db.query(Questao).filter_by(regata_id=ids[4]).delete(
                    synchronize_session=False
                )
                db.query(Regata).filter_by(id=ids[4]).delete(
                    synchronize_session=False
                )
                db.query(Equipe).filter_by(id=ids[2]).delete(
                    synchronize_session=False
                )
                db.query(User).filter(User.id.in_(ids[:2])).delete(
                    synchronize_session=False
                )
                db.commit()
        engine.dispose()
