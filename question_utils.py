from collections.abc import Iterable

from models import Questao

def ordenar_questoes(questoes: Iterable[Questao]) -> list[Questao]:
    return sorted(questoes, key=lambda questao: questao.id)


def numerar_questoes(questoes: Iterable[Questao]) -> dict[int, int]:
    return {
        questao.id: numero
        for numero, questao in enumerate(ordenar_questoes(questoes), start=1)
    }


def rotulo_questao(questao: Questao, numero: int) -> str:
    return f"Questão {numero}"
