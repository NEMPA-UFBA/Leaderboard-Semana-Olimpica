from datetime import datetime, timezone

from time_utils import formatar_horario_do_evento


def test_formatar_horario_converte_utc_para_horario_de_sao_paulo():
    instante_utc = datetime(2026, 10, 12, 23, 4, tzinfo=timezone.utc)

    assert formatar_horario_do_evento(instante_utc) == "12/10/2026 20:04:00"


def test_formatar_horario_trata_data_sem_fuso_como_utc():
    instante_sem_fuso = datetime(2026, 10, 12, 23, 4)

    assert formatar_horario_do_evento(instante_sem_fuso) == "12/10/2026 20:04:00"
