import unicodedata

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Equipe, Tentativa

_NOMES_GREGOS = (
    "Alfa",
    "Beta",
    "Gama",
    "Delta",
    "Épsilon",
    "Zeta",
    "Eta",
    "Teta",
    "Iota",
    "Capa",
    "Lambda",
    "Mi",
    "Ni",
    "Xi",
    "Ômicron",
    "Pi",
    "Rho",
    "Sigma",
    "Tau",
    "Ípsilon",
    "Fi",
    "Qui",
    "Psi",
    "Ômega",
)

_NOMES_CIENTIFICOS = (
    "Órion",
    "Lira",
    "Fênix",
    "Andrômeda",
    "Cassiopeia",
    "Centauro",
    "Cruzeiro do Sul",
    "Cisne",
    "Águia",
    "Dragão",
    "Gêmeos",
    "Leão",
    "Hidra",
    "Pégaso",
    "Vela",
    "Carina",
    "Escorpião",
    "Sagitário",
    "Touro",
    "Ursa Maior",
    "Ursa Menor",
    "Aquário",
    "Cefeu",
    "Perseu",
)


def _chave_nome(nome: str) -> str:
    decomposed = unicodedata.normalize("NFKD", nome.casefold())
    return "".join(
        caractere
        for caractere in decomposed
        if unicodedata.category(caractere) != "Mn"
    )


_ORDEM_GREGA = {
    _chave_nome(nome): indice for indice, nome in enumerate(_NOMES_GREGOS)
}


def chave_ordenacao_equipe(nome: str) -> tuple[int, int, str]:
    nome_normalizado = _chave_nome(nome.strip())
    nome_grego = nome_normalizado
    for prefixo in ("time ", "equipe "):
        if nome_grego.startswith(prefixo):
            nome_grego = nome_grego[len(prefixo):]
            break

    partes = nome_grego.rsplit(" ", 1)
    if len(partes) == 2 and partes[1].isdigit():
        nome_grego = partes[0]

    indice_grego = _ORDEM_GREGA.get(nome_grego)
    if indice_grego is not None:
        return (0, indice_grego, nome_normalizado)
    return (1, 0, nome_normalizado)


def ordenar_equipes(equipes: list[Equipe]) -> list[Equipe]:
    return sorted(equipes, key=lambda equipe: _chave_nome(equipe.nome))


def ordenar_equipes_gregas(equipes: list[Equipe]) -> list[Equipe]:
    return sorted(equipes, key=lambda equipe: chave_ordenacao_equipe(equipe.nome))


def gerar_nomes_equipes(quantidade: int, nomes_existentes=()) -> list[str]:
    if isinstance(quantidade, bool) or not isinstance(quantidade, int) or quantidade < 1:
        raise ValueError("A quantidade de equipes deve ser um inteiro maior que zero.")

    existentes = {_chave_nome(nome.strip()) for nome in nomes_existentes}
    nomes_base = _NOMES_GREGOS + _NOMES_CIENTIFICOS
    nomes = []
    sequencia = 0

    while len(nomes) < quantidade:
        ciclo, indice = divmod(sequencia, len(nomes_base))
        nome_base = nomes_base[indice]
        sufixo = f" {ciclo + 1}" if ciclo else ""
        nome = f"Time {nome_base}{sufixo}"
        sequencia += 1

        if _chave_nome(nome) in existentes:
            continue

        existentes.add(_chave_nome(nome))
        nomes.append(nome)

    return nomes


def criar_equipes_automaticamente(db: Session, quantidade: int) -> list[str]:
    nomes_existentes = [nome for (nome,) in db.query(Equipe.nome).all()]
    nomes = gerar_nomes_equipes(quantidade, nomes_existentes)
    db.add_all(Equipe(nome=nome) for nome in nomes)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise RuntimeError(
            "As equipes nao foram criadas porque os nomes mudaram "
            "durante a operacao. Atualize a lista e tente novamente."
        ) from error
    return nomes


def excluir_equipes(db: Session, equipe_ids: list[int]) -> list[str]:
    ids = list(dict.fromkeys(equipe_ids))
    if not ids:
        raise ValueError("Selecione pelo menos uma equipe.")

    equipes = (
        db.query(Equipe)
        .filter(Equipe.id.in_(ids))
        .order_by(Equipe.id)
        .all()
    )
    if len(equipes) != len(ids):
        raise LookupError("Uma ou mais equipes selecionadas nao foram encontradas.")

    com_tentativas = {
        equipe_id
        for equipe_id, in (
            db.query(Tentativa.equipe_id)
            .filter(Tentativa.equipe_id.in_(ids))
            .group_by(Tentativa.equipe_id)
            .all()
        )
    }
    if com_tentativas:
        nomes = [
            equipe.nome for equipe in equipes if equipe.id in com_tentativas
        ]
        raise ValueError(
            "Nao e possivel excluir equipes que ja possuem tentativas: "
            + ", ".join(nomes)
            + "."
        )

    nomes = [equipe.nome for equipe in equipes]
    try:
        for equipe in equipes:
            db.delete(equipe)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise RuntimeError(
            "A exclusao foi cancelada porque uma equipe ja possui tentativas. "
            "Nenhuma equipe selecionada foi removida."
        ) from error
    return nomes
