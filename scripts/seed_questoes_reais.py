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
            label = question.get("rotulo")
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
            if label is not None and (
                not isinstance(label, str) or not label.strip()
            ):
                raise ValueError(f"Rotulo invalido na regata {name!r}.")
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


def _catalogo_questoes(regattas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for regatta_index, regatta in enumerate(regattas, start=1):
        for question in sorted(regatta["questoes"], key=lambda item: item["ordem"]):
            catalog.append(
                {
                    "codigo": f"R{regatta_index}Q{question['ordem']}",
                    "regata_origem": regatta["nome"],
                    "questao": question,
                }
            )
    return catalog


def _rotulo_questao_catalogo(item: dict[str, Any]) -> str:
    question = item["questao"]
    difficulty = {
        "facil": "Fácil",
        "medio": "Médio",
        "dificil": "Difícil",
    }[question["nivel"]]
    tags = ", ".join(
        f"{tag['nome']} ({tag['categoria']})"
        for tag in question.get("tags", [])
    ) or "sem tags"
    image = Path(question["imagem"]).name if question.get("imagem") else "sem imagem"
    label = f"{question['rotulo']} | " if question.get("rotulo") else ""
    return (
        f"{item['codigo']} | {label}{item['regata_origem']} | {difficulty} | "
        f"{tags} | imagem: {image}"
    )


def _selecionar_questoes_catalogo(
    catalog: list[dict[str, Any]], codes: list[str]
) -> list[dict[str, Any]]:
    by_code = {item["codigo"]: item for item in catalog}
    if len(codes) != len(set(codes)):
        raise ValueError("Cada questao deve aparecer uma unica vez na selecao.")

    unknown_codes = [code for code in codes if code not in by_code]
    if unknown_codes:
        raise ValueError(
            "Codigo(s) de questao desconhecido(s): " + ", ".join(unknown_codes)
        )

    selected = []
    for order, code in enumerate(codes, start=1):
        source_question = by_code[code]["questao"]
        question = {
            **source_question,
            "ordem": order,
            "_codigo_catalogo": code,
            "tags": [
                dict(tag) for tag in source_question.get("tags", [])
            ],
        }
        selected.append(question)
    return selected


def _plano_interativo(
    payload: dict[str, Any],
) -> dict[str, Any]:
    raw_components = input(
        "O que incluir? J=juizes, R=regata, Q=questoes "
        "(combine, por exemplo JRQ): "
    )
    components = set(raw_components.upper().replace(",", "").replace(" ", ""))
    if not components or not components <= {"J", "R", "Q"}:
        raise ValueError("Escolha uma ou mais opcoes entre J, R e Q.")

    include_judges = "J" in components
    include_regatta = "R" in components
    include_questions = "Q" in components

    if include_regatta:
        regatta_name = input("Nome da nova regata (sera criada inativa): ").strip()
        if not regatta_name:
            raise ValueError("O nome da nova regata nao pode ficar vazio.")
    elif include_questions:
        regatta_name = input(
            "Nome exato da regata existente que recebera as questoes: "
        ).strip()
        if not regatta_name:
            raise ValueError("Informe o nome da regata de destino.")
    else:
        regatta_name = None

    selected_questions: list[dict[str, Any]] = []
    if include_questions:
        catalog = _catalogo_questoes(payload["regatas"])
        print("\nQuestoes disponiveis (enunciados e gabaritos nao sao exibidos):")
        for item in catalog:
            print("  " + _rotulo_questao_catalogo(item))

        try:
            count = int(input(f"Quantas questoes deseja selecionar? (1-{len(catalog)}): "))
        except ValueError as error:
            raise ValueError("Informe a quantidade como um numero inteiro.") from error
        if count < 1 or count > len(catalog):
            raise ValueError(
                f"A quantidade deve estar entre 1 e {len(catalog)}."
            )

        raw_codes = input(
            "Informe os codigos na ordem desejada, separados por virgula: "
        )
        codes = [code.strip().upper() for code in raw_codes.split(",") if code.strip()]
        if len(codes) != count:
            raise ValueError(
                f"Voce informou {len(codes)} codigo(s), mas selecionou {count} questoes."
            )
        selected_questions = _selecionar_questoes_catalogo(catalog, codes)

    return {
        "juizes": include_judges,
        "criar_regata": include_regatta,
        "questoes": include_questions,
        "nome_regata": regatta_name,
        "questoes_selecionadas": selected_questions,
    }


def _seed_regatta_only(db: Session, regatta_model: type, name: str) -> tuple[int, int]:
    matches = db.query(regatta_model).filter_by(nome=name).all()
    if len(matches) > 1:
        raise RuntimeError(f"Ha mais de uma regata chamada {name!r}.")
    if matches:
        if matches[0].ativa:
            raise RuntimeError(
                f"A regata {name!r} ja existe e esta ativa; nada foi alterado."
            )
        return 0, 1

    db.add(regatta_model(nome=name, ativa=False))
    db.flush()
    return 1, 0


def _validar_regata_destino(
    db: Session,
    regatta_model: type,
    name: str,
    *,
    required: bool,
) -> None:
    matches = (
        db.query(regatta_model)
        .filter_by(nome=name)
        .with_for_update()
        .all()
    )
    if len(matches) > 1:
        raise LookupError(f"Ha mais de uma regata chamada {name!r}.")
    if not matches:
        if required:
            raise LookupError(f"A regata de destino {name!r} nao foi encontrada.")
        return
    if matches[0].ativa:
        raise RuntimeError(
            f"A regata {name!r} esta ativa; desative-a antes de inserir questoes."
        )


def _aplicar_plano_interativo(
    plan: dict[str, Any],
    payload: dict[str, Any],
    images: dict[str, bytes],
) -> None:
    from auth import hash_password
    from database import SessionLocal, init_db
    from models import Questao, Regata, Tag, User
    from question_tags import NIVEIS_TAG

    init_db()

    with SessionLocal() as db:
        missing_judges = (
            [
                judge
                for judge in payload["juizes"]
                if _find_existing_judge(db, User, judge) is None
            ]
            if plan["juizes"]
            else []
        )

    password_hash = None
    if missing_judges:
        password_hash = hash_password(_password_for_new_judges())

    regattas_created = 0
    regattas_existing = 0
    questions_created = 0
    judges_created = 0
    judges_existing = 0

    with SessionLocal.begin() as db:
        if plan["questoes"]:
            _validar_regata_destino(
                db,
                Regata,
                plan["nome_regata"],
                required=not plan["criar_regata"],
            )
            regattas_created, questions_created = _seed_questions(
                db,
                Regata,
                Questao,
                Tag,
                {
                    "regatas": [
                        {
                            "nome": plan["nome_regata"],
                            "questoes": plan["questoes_selecionadas"],
                        }
                    ]
                },
                images,
                NIVEIS_TAG,
            )
        elif plan["criar_regata"]:
            regattas_created, regattas_existing = _seed_regatta_only(
                db, Regata, plan["nome_regata"]
            )

        if plan["juizes"]:
            judges_created, judges_existing = _seed_judges(
                db, User, payload["juizes"], password_hash
            )

    print(
        f"Concluido. Regatas novas: {regattas_created}; "
        f"regatas ja existentes: {regattas_existing}; "
        f"questoes novas: {questions_created}; "
        f"juizes novos: {judges_created}; juizes ja existentes: {judges_existing}."
    )


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
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Escolhe juizes, regatas e questoes do catalogo privado.",
    )
    args = parser.parse_args()

    if args.target == "production" and not args.confirm_production:
        parser.error("production exige a opcao --confirm-production.")

    payload = _load_seed_data()
    plan = _plano_interativo(payload) if args.interactive else None
    if plan and plan["questoes"]:
        image_payload = [
            {
                "nome": plan["nome_regata"],
                "questoes": plan["questoes_selecionadas"],
            }
        ]
        images = _load_images(image_payload)
    elif args.interactive:
        images = {}
    else:
        images = _load_images(payload["regatas"])
    raw_url, parsed_url = _database_url(args.target, args.confirm_production)
    print(
        f"Alvo: {args.target}; PostgreSQL em "
        f"{parsed_url.host}/{parsed_url.database}."
    )
    print(
        f"Imagens locais verificadas: {', '.join(sorted(images)) or 'nenhuma'}."
    )
    print("Gabaritos permanecem no arquivo privado e nao sao gravados no banco.")

    if plan is not None:
        components = [
            label
            for included, label in (
                (plan["juizes"], "juizes"),
                (plan["criar_regata"], "regata nova"),
                (plan["questoes"], "questoes"),
            )
            if included
        ]
        print("Plano: " + ", ".join(components) + ".")
        if plan["nome_regata"]:
            target_description = (
                "nova e inativa"
                if plan["criar_regata"]
                else "existente"
            )
            print(
                f"Regata {target_description}: {plan['nome_regata']}."
            )
        catalog_by_code = {
            item["codigo"]: item
            for item in _catalogo_questoes(payload["regatas"])
        }
        for order, question in enumerate(plan["questoes_selecionadas"], start=1):
            source = catalog_by_code[question["_codigo_catalogo"]]
            print(
                f"  {order}. {_rotulo_questao_catalogo(source)}"
            )
    else:
        print(
            f"Plano: {len(payload['regatas'])} regatas, "
            f"{sum(len(item['questoes']) for item in payload['regatas'])} "
            f"questoes, {len(payload['juizes'])} contas de juiz."
        )

    if not args.apply:
        print("Previa concluida; nenhum banco foi conectado ou alterado.")
        print("Acrescente --apply para confirmar e gravar.")
        return 0

    _confirm_target(args.target)
    os.environ["DATABASE_URL"] = raw_url

    if plan is not None:
        _aplicar_plano_interativo(plan, payload, images)
        return 0

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
