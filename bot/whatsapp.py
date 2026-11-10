"""Fila de posts para o grupo do WhatsApp.

O bot (Python) só deixa um arquivo na pasta WA_FILA; quem posta é o serviço
em wa/servico.mjs, que roda junto com o ciclo e controla o ritmo. Sem WA_FILA
(ex.: rodando local ou nos testes), não faz nada.
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path


def enfileirar(texto, imagem=None, agora=None, loja="ml"):
    pasta = os.environ.get("WA_FILA")
    if not pasta or not texto:
        return False
    p = Path(pasta)
    p.mkdir(parents=True, exist_ok=True)
    quando = agora or datetime.now().astimezone()
    item = {"texto": texto, "imagem": imagem or None, "criado": quando.isoformat(), "loja": loja}
    nome = p / f"{time.time_ns()}.json"
    tmp = nome.with_suffix(".tmp")
    tmp.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    tmp.rename(nome)
    return True
