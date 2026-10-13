from collections.abc import Iterable

from models import Questao

NIVEIS_ORDEM = {"facil": 0, "medio": 1, "dificil": 2}
NIVEIS_ROTULO = {
    "facil": "🟢 Fácil",
    "medio": "🟡 Médio",
    "dificil": "🔴 Difícil",
}


def ordenar_questoes(questoes: Iterable[Questao]) -> list[Questao]:
    return sorted(
        questoes,
        key=lambda questao: (NIVEIS_ORDEM.get(questao.nivel, 99), questao.id),
    )


def numerar_questoes(questoes: Iterable[Questao]) -> dict[int, int]:
    return {
        questao.id: numero
        for numero, questao in enumerate(ordenar_questoes(questoes), start=1)
    }


def rotulo_questao(questao: Questao, numero: int) -> str:
    nivel = NIVEIS_ROTULO.get(questao.nivel, questao.nivel)
    return f"Questão {numero} — {nivel}"
