import unicodedata

from sqlalchemy.orm import Session

from models import Questao

NIVEIS_TAG = {
    "facil": "Fácil",
    "medio": "Médio",
    "dificil": "Difícil",
}

TAGS_PADRAO = (
    ("Fácil", "dificuldade"),
    ("Médio", "dificuldade"),
    ("Difícil", "dificuldade"),
    ("Matemática", "disciplina"),
    ("Estatística", "disciplina"),
    ("Álgebra", "área"),
    ("Combinatória", "área"),
    ("Teoria dos Números", "área"),
    ("Geometria", "área"),
    ("Lógica/Raciocínio Lógico", "área"),
)


def _chave_tag(nome: str) -> str:
    normalizado = unicodedata.normalize("NFKD", nome.casefold().strip())
    return "".join(
        caractere
        for caractere in normalizado
        if unicodedata.category(caractere) != "Mn"
    )


def _modelo_tag(questao: Questao) -> type:
    return type(questao).__mapper__.relationships["tags"].mapper.class_


def garantir_tags_padrao(db: Session) -> None:
    modelo_tag = Questao.__mapper__.relationships["tags"].mapper.class_
    existentes = {
        (tag.categoria, _chave_tag(tag.nome)): tag
        for tag in db.query(modelo_tag).all()
    }

    for nome, categoria in TAGS_PADRAO:
        chave = (categoria, _chave_tag(nome))
        if chave not in existentes:
            tag = modelo_tag(nome=nome, categoria=categoria)
            db.add(tag)
            existentes[chave] = tag

    db.flush()
    tags_dificuldade = {
        _chave_tag(nome): existentes[("dificuldade", _chave_tag(nome))]
        for nome, categoria in TAGS_PADRAO
        if categoria == "dificuldade"
    }
    for questao in db.query(Questao).all():
        nome_nivel = NIVEIS_TAG.get(questao.nivel)
        tag = tags_dificuldade.get(_chave_tag(nome_nivel)) if nome_nivel else None
        if tag and all(existing.id != tag.id for existing in questao.tags):
            questao.tags.append(tag)

    db.commit()


def atualizar_tags_questao(
    db: Session,
    questao: Questao,
    nivel: str,
    tags_selecionadas: list[str],
    tags_personalizadas: list[str],
) -> None:
    modelo_tag = _modelo_tag(questao)
    nome_dificuldade = NIVEIS_TAG[nivel]
    nomes_selecionados = {_chave_tag(nome): nome.strip() for nome in tags_selecionadas}
    nomes_personalizados = {
        _chave_tag(nome): nome.strip()
        for nome in tags_personalizadas
        if nome.strip()
    }
    tags_existentes = db.query(modelo_tag).all()
    por_nome = {_chave_tag(tag.nome): tag for tag in tags_existentes}

    nomes_selecionados[_chave_tag(nome_dificuldade)] = nome_dificuldade
    for chave, nome in nomes_personalizados.items():
        nomes_selecionados.setdefault(chave, nome)

    selecionadas = []
    for chave, nome in nomes_selecionados.items():
        tag = por_nome.get(chave)
        if tag is None:
            tag = modelo_tag(nome=nome, categoria="personalizada")
            db.add(tag)
            db.flush()
            por_nome[chave] = tag
        selecionadas.append(tag)

    questao.nivel = nivel
    questao.tags = selecionadas
    db.commit()
