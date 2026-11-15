"""Horário de postagem, com a janela extra da meia-noite em datas especiais.

No dia a dia o bot posta de HORA_INICIO a HORA_FIM (8h às 22h). Nas datas de DATAS_MEIA_NOITE
(Black Friday, 12.12...) ele também fica ligado na virada: das 23h30 da véspera à 1h do dia,
que é quando as lojas soltam os preços e os cupons da data.
"""
import os
from datetime import date, datetime, timedelta

DATAS_PADRAO = "2026-11-27,2026-12-12"  # Black Friday e 12.12
INICIO_VESPERA = (23, 30)  # começa às 23h30 da véspera
FIM_HORA = 1               # vai até 1h do dia


def datas_meia_noite():
    """Datas (date) em que a virada tem postagem. Vem de DATAS_MEIA_NOITE (AAAA-MM-DD separadas por vírgula)."""
    texto = os.environ.get("DATAS_MEIA_NOITE")
    texto = DATAS_PADRAO if texto is None else texto
    datas = set()
    for parte in texto.replace(";", ",").split(","):
        try:
            datas.add(date.fromisoformat(parte.strip()))
        except ValueError:
            pass
    return datas


def meia_noite(agora, datas=None):
    """True dentro da janela da virada (23h30 da véspera até 1h do dia especial)."""
    datas = datas_meia_noite() if datas is None else datas
    if not datas:
        return False
    hoje = agora.date()
    if hoje in datas and agora.hour < FIM_HORA:
        return True
    return hoje + timedelta(days=1) in datas and (agora.hour, agora.minute) >= INICIO_VESPERA


def ativo(agora, inicio, fim):
    """True no horário normal de postagem ou na janela da meia-noite."""
    return inicio <= agora.hour < fim or meia_noite(agora)


def proxima_janela(agora):
    """Início da próxima janela da meia-noite depois de 'agora' (ou None)."""
    inicios = []
    for d in datas_meia_noite():
        vespera = d - timedelta(days=1)
        ini = datetime(vespera.year, vespera.month, vespera.day, *INICIO_VESPERA, tzinfo=agora.tzinfo)
        if ini > agora:
            inicios.append(ini)
    return min(inicios) if inicios else None
