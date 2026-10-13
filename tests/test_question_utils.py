from types import SimpleNamespace

from question_utils import numerar_questoes, ordenar_questoes, rotulo_questao


def test_numbers_questions_by_registration_order_not_difficulty():
    questions = [
        SimpleNamespace(id=14, nivel="facil"),
        SimpleNamespace(id=8, nivel="facil"),
        SimpleNamespace(id=3, nivel="dificil"),
        SimpleNamespace(id=2, nivel="medio"),
    ]

    ordered = ordenar_questoes(questions)

    assert [question.id for question in ordered] == [2, 3, 8, 14]
    assert numerar_questoes(questions) == {2: 1, 3: 2, 8: 3, 14: 4}


def test_numbering_restarts_for_each_regatta():
    first_regatta = [SimpleNamespace(id=5, nivel="facil")]
    second_regatta = [SimpleNamespace(id=19, nivel="dificil")]

    assert numerar_questoes(first_regatta) == {5: 1}
    assert numerar_questoes(second_regatta) == {19: 1}


def test_question_label_hides_level_and_enunciado():
    question = SimpleNamespace(
        id=10,
        nivel="medio",
        imagem_filename=None,
        enunciado="Resolva 2x + 3 = 7",
    )

    assert rotulo_questao(question, 2) == "Questão 2"
    assert "Médio" not in rotulo_questao(question, 2)
    assert "Resolva 2x + 3 = 7" not in rotulo_questao(question, 2)
