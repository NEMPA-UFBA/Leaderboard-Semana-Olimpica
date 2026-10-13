from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_FUSO_EVENTO = ZoneInfo("America/Sao_Paulo")


def agora_no_fuso_do_evento() -> datetime:
    return datetime.now(_FUSO_EVENTO)


def formatar_horario_do_evento(data_hora: datetime) -> str:
    if data_hora.tzinfo is None:
        data_hora = data_hora.replace(tzinfo=timezone.utc)
    else:
        data_hora = data_hora.astimezone(timezone.utc)

    return data_hora.astimezone(_FUSO_EVENTO).strftime("%d/%m/%Y %H:%M:%S")
