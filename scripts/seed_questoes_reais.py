from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SEED_FILE = PROJECT_ROOT / ".local-seeds" / "questoes_reais.json"
LEVELS = {"facil", "medio", "dificil"}
TAG_CATEGORIES = {"disciplina", "área", "personalizada"}


def _normalizar(valor: str) -> str:
    decomposed = unicodedata.normalize("NFKD", valor.casefold().strip())
    return "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )


def _load_seed_data() -> dict[str, Any]:
    with SEED_FILE.open(encoding="utf-8") as seed_file:
        payload = json.load(seed_file)

    if not isinstance(payload, dict):
        raise ValueError("O arquivo privado precisa conter um objeto JSON.")
    judges = payload.get("juizes")
    regattas = payload.get("regatas")
    if not isinstance(judges, list) or not isinstance(regattas, list):
        raise ValueError("O arquivo privado precisa conter listas de juizes e regatas.")

    usernames: set[str] = set()
    for judge in judges:
        name = judge.get("nome")
        username = judge.get("username")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Todo juiz precisa ter um nome.")
        if not isinstance(username, str) or not re.fullmatch(r"[a-z0-9_]+", username):
            raise ValueError(f"Username invalido para {name!r}.")
        if username in usernames:
            raise ValueError(f"Username duplicado no arquivo privado: {username}.")
        usernames.add(username)

    regatta_names: set[str] = set()
    for regatta in regattas:
        name = regatta.get("nome")
        questions = regatta.get("questoes")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Toda regata precisa ter um nome.")
        if _normalizar(name) in regatta_names:
            raise ValueError(f"Nome de regata duplicado: {name}.")
        regatta_names.add(_normalizar(name))
        if not isinstance(questions, list) or not questions:
            raise ValueError(f"A regata {name!r} precisa ter questoes.")

        orders = []
        for question in questions:
            order = question.get("ordem")
            level = question.get("nivel")
            statement = question.get("enunciado")
            answer = question.get("gabarito")
            image = question.get("imagem")
            tags = question.get("tags", [])
            if not isinstance(order, int) or order < 1:
                raise ValueError(f"Ordem invalida na regata {name!r}.")
            orders.append(order)
            if level not in LEVELS:
                raise ValueError(f"Dificuldade invalida na regata {name!r}.")
            if not isinstance(statement, str) or not statement.strip():
                raise ValueError(f"Enunciado vazio na regata {name!r}.")
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError(
                    f"Gabarito ausente no arquivo privado da regata {name!r}."
                )
            if image is not None and not isinstance(image, str):
                raise ValueError(f"Caminho de imagem invalido na regata {name!r}.")
            if not isinstance(tags, list):
                raise ValueError(f"Tags invalidas na regata {name!r}.")
            for tag in tags:
                if (
                    not isinstance(tag, dict)
                    or not isinstance(tag.get("nome"), str)
                    or tag.get("categoria") not in TAG_CATEGORIES
                ):
                    raise ValueError(f"Tag invalida na regata {name!r}.")

        if sorted(orders) != list(range(1, len(questions) + 1)):
            raise ValueError(
                f"As questoes de {name!r} devem estar numeradas sem lacunas."
            )

    return payload


def _load_images(regattas: list[dict[str, Any]]) -> dict[str, bytes]:
    images: dict[str, bytes] = {}
    for regatta in regattas:
        for question in regatta["questoes"]:
            relative_path = question.get("imagem")
            if relative_path is None or relative_path in images:
                continue
            image_path = (PROJECT_ROOT / relative_path).resolve()
            try:
                image_path.relative_to(PROJECT_ROOT)
            except ValueError as error:
                raise ValueError(
                    f"A imagem precisa estar dentro do projeto: {relative_path}"
                ) from error
            if not image_path.is_file():
                raise FileNotFoundError(
                    f"Imagem nao encontrada: {image_path}. "
                    "Confira maiusculas, extensao e pasta."
                )
            contents = image_path.read_bytes()
            if not contents:
                raise ValueError(f"A imagem esta vazia: {image_path}")
            images[relative_path] = contents
    return images


def _database_url(target: str, confirm_production: bool) -> tuple[str, URL]:
    if target == "test":
        local_settings = dotenv_values(PROJECT_ROOT / ".env")
        raw_url = local_settings.get("DATABASE_URL")
        if not raw_url:
            raise RuntimeError(
                "DATABASE_URL nao encontrada no .env. "
                "O script nao usa SQLite como fallback."
            )
    else:
        if not confirm_production:
            raise RuntimeError(
                "Para producao, informe tambem --confirm-production."
            )
        raw_url = getpass.getpass(
            "Cole a URL do Neon production (entrada oculta): "
        )
        if not raw_url:
            raise RuntimeError("A URL do banco de producao nao pode ser vazia.")

    parsed_url = make_url(raw_url)
    if parsed_url.get_backend_name() != "postgresql":
        raise RuntimeError("O seed aceita somente uma conexao PostgreSQL.")
    return raw_url, parsed_url


def _confirm_target(target: str) -> None:
    expected = "TESTE" if target == "test" else "PRODUCAO"
    confirmation = input(
        f"Para gravar no alvo {target}, digite {expected}: "
    ).strip()
    if confirmation != expected:
        raise RuntimeError("Confirmacao incorreta; nenhum dado foi gravado.")


def _password_for_new_judges() -> str:
    from auth import password_validation_error

    password = getpass.getpass(
        "Senha temporaria comum para os novos juizes (entrada oculta): "
    )
    confirmation = getpass.getpass("Repita a senha temporaria: ")
    if password != confirmation:
        raise ValueError("As senhas digitadas nao coincidem.")
    error = password_validation_error(password)
    if error:
        raise ValueError(error)
    return password


def _find_existing_judge(
    db: Session,
    user_model: type,
    judge_spec: dict[str, str],
) -> Any | None:
    name = judge_spec["nome"]
    username = judge_spec["username"]
    by_username = (
        db.query(user_model).filter_by(username=username).one_or_none()
    )
    matching_names = [
        user
        for user in db.query(user_model).filter_by(role="juiz").all()
        if _normalizar(user.nome or "") == _normalizar(name)
    ]
    if len(matching_names) > 1:
        raise RuntimeError(
            f"Ha mais de uma conta de juiz com o nome {name!r}; "
            "resolva a duplicidade antes de continuar."
        )
    by_name = matching_names[0] if matching_names else None
    if by_username is not None and by_name is not None and by_username.id != by_name.id:
        raise RuntimeError(
            f"O username {username!r} e o nome {name!r} pertencem a contas "
            "diferentes; nenhuma conta foi alterada."
        )
    if by_name is not None and by_name.username != username:
        raise RuntimeError(
            f"{name!r} ja tem uma conta com username {by_name.username!r}. "
            "Atualize o arquivo privado para evitar criar uma conta duplicada."
        )
    existing = by_username or by_name
    if existing is None:
        return None
    if existing.role != "juiz" or _normalizar(existing.nome or "") != _normalizar(name):
        raise RuntimeError(
            f"A conta {username!r} ja existe com outra identidade; "
            "nenhuma conta foi alterada."
        )
    return existing


def _ensure_tag(
    db: Session,
    tag_model: type,
    tag_cache: dict[tuple[str, str], Any],
    name: str,
    category: str,
) -> Any:
    key = (_normalizar(name), category)
    tag = tag_cache.get(key)
    if tag is None:
        tag = tag_model(nome=name, categoria=category)
        db.add(tag)
        db.flush()
        tag_cache[key] = tag
    return tag


def _question_tags(
    db: Session,
    tag_model: type,
    tag_cache: dict[tuple[str, str], Any],
    question_spec: dict[str, Any],
    difficulty_tags: dict[str, str],
) -> list[Any]:
    selected = [
        _ensure_tag(
            db,
            tag_model,
            tag_cache,
            difficulty_tags[question_spec["nivel"]],
            "dificuldade",
        )
    ]
    selected.extend(
        _ensure_tag(db, tag_model, tag_cache, tag["nome"], tag["categoria"])
        for tag in question_spec.get("tags", [])
    )
    return selected


def _seed_questions(
    db: Session,
    regatta_model: type,
    question_model: type,
    tag_model: type,
    payload: dict[str, Any],
    images: dict[str, bytes],
    difficulty_tags: dict[str, str],
) -> tuple[int, int]:
    tag_cache = {
        (_normalizar(tag.nome), tag.categoria): tag
        for tag in db.query(tag_model).all()
    }
    created_regattas = 0
    created_questions = 0

    for regatta_spec in payload["regatas"]:
        matches = (
            db.query(regatta_model)
            .filter_by(nome=regatta_spec["nome"])
            .all()
        )
        if len(matches) > 1:
            raise RuntimeError(
                f"Ha mais de uma regata chamada {regatta_spec['nome']!r}."
            )
        if matches:
            regatta = matches[0]
        else:
            regatta = regatta_model(nome=regatta_spec["nome"], ativa=False)
            db.add(regatta)
            db.flush()
            created_regattas += 1

        expected_questions = sorted(
            regatta_spec["questoes"], key=lambda question: question["ordem"]
        )
        existing_questions = (
            db.query(question_model)
            .filter_by(regata_id=regatta.id)
            .order_by(question_model.id)
            .all()
        )
        if len(existing_questions) > len(expected_questions):
            raise RuntimeError(
                f"A regata {regatta.nome!r} ja tem questoes fora deste seed; "
                "para evitar renumeracao, nenhum dado foi gravado."
            )

        for index, existing in enumerate(existing_questions):
            spec = expected_questions[index]
            image_path = spec.get("imagem")
            expected_image = images.get(image_path) if image_path else None
            expected_filename = Path(image_path).name if image_path else None
            if (
                existing.enunciado != spec["enunciado"]
                or existing.nivel != spec["nivel"]
                or existing.imagem_filename != expected_filename
                or existing.imagem != expected_image
            ):
                raise RuntimeError(
                    f"A questao {index + 1} da regata {regatta.nome!r} "
                    "nao corresponde ao seed; nenhum dado foi gravado."
                )
            expected_tags = _question_tags(
                db, tag_model, tag_cache, spec, difficulty_tags
            )
            current_tag_keys = {
                (_normalizar(tag.nome), tag.categoria) for tag in existing.tags
            }
            for tag in expected_tags:
                if (_normalizar(tag.nome), tag.categoria) not in current_tag_keys:
                    existing.tags.append(tag)

        for spec in expected_questions[len(existing_questions):]:
            image_path = spec.get("imagem")
            question = question_model(
                regata_id=regatta.id,
                nivel=spec["nivel"],
                enunciado=spec["enunciado"],
                imagem=images.get(image_path) if image_path else None,
                imagem_filename=Path(image_path).name if image_path else None,
            )
            question.tags = _question_tags(
                db, tag_model, tag_cache, spec, difficulty_tags
            )
            db.add(question)
            db.flush()
            created_questions += 1

    return created_regattas, created_questions


def _seed_judges(
    db: Session,
    user_model: type,
    judges: list[dict[str, str]],
    password_hash: str | None,
) -> tuple[int, int]:
    created = 0
    existing = 0
    for judge_spec in judges:
        found = _find_existing_judge(db, user_model, judge_spec)
        if found is not None:
            existing += 1
            continue
        if password_hash is None:
            raise RuntimeError("Senha ausente para novos juizes.")
        db.add(
            user_model(
                nome=judge_spec["nome"],
                username=judge_spec["username"],
                password_hash=password_hash,
                role="juiz",
                must_change_password=True,
            )
        )
        created += 1
    return created, existing


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Insere regatas, questoes e juizes a partir de dados locais."
    )
    parser.add_argument(
        "--target",
        choices=("test", "production"),
        default="test",
        help="Banco alvo. O padrao usa DATABASE_URL do .env.",
    )
    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="Permite selecionar production; ainda exige confirmacao digitada.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Grava os dados. Sem esta opcao, apenas valida os arquivos.",
    )
    args = parser.parse_args()

    if args.target == "production" and not args.confirm_production:
        parser.error("production exige a opcao --confirm-production.")

    payload = _load_seed_data()
    images = _load_images(payload["regatas"])
    raw_url, parsed_url = _database_url(args.target, args.confirm_production)
    print(
        f"Alvo: {args.target}; PostgreSQL em "
        f"{parsed_url.host}/{parsed_url.database}."
    )
    print(
        f"Plano: {len(payload['regatas'])} regatas, "
        f"{sum(len(item['questoes']) for item in payload['regatas'])} questoes, "
        f"{len(payload['juizes'])} contas de juiz."
    )
    print(
        f"Imagens locais verificadas: {', '.join(sorted(images)) or 'nenhuma'}."
    )
    print("Gabaritos permanecem no arquivo privado e nao sao gravados no banco.")

    if not args.apply:
        print("Previa concluida; nenhum banco foi conectado ou alterado.")
        print("Acrescente --apply para confirmar e gravar.")
        return 0

    _confirm_target(args.target)
    os.environ["DATABASE_URL"] = raw_url

    from auth import hash_password
    from database import SessionLocal, init_db
    from models import Questao, Regata, Tag, User
    from question_tags import NIVEIS_TAG

    init_db()
    with SessionLocal() as db:
        missing_judges = [
            judge
            for judge in payload["juizes"]
            if _find_existing_judge(db, User, judge) is None
        ]

    password_hash = None
    if missing_judges:
        temporary_password = _password_for_new_judges()
        password_hash = hash_password(temporary_password)

    with SessionLocal.begin() as db:
        regattas_created, questions_created = _seed_questions(
            db,
            Regata,
            Questao,
            Tag,
            payload,
            images,
            NIVEIS_TAG,
        )
        judges_created, judges_existing = _seed_judges(
            db, User, payload["juizes"], password_hash
        )

    print(
        f"Concluido. Regatas novas: {regattas_created}; "
        f"questoes novas: {questions_created}; "
        f"juizes novos: {judges_created}; juizes ja existentes: {judges_existing}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
