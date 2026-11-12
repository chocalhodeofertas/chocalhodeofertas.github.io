"""Fila de posts para o grupo do WhatsApp.

O bot (Python) só deixa um arquivo na pasta WA_FILA; quem posta é o serviço
em wa/servico.mjs, que roda junto com o ciclo e controla o ritmo. Sem WA_FILA
(ex.: rodando local ou nos testes), não faz nada.
"""
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path


def enfileirar(texto, imagem=None, agora=None, loja="ml", png=None, preview=None):
    """png: bytes de uma arte pronta (vai junto na fila e tem prioridade sobre a URL da foto)."""
    pasta = os.environ.get("WA_FILA")
    if not pasta or not texto:
        return False
    p = Path(pasta)
    p.mkdir(parents=True, exist_ok=True)
    quando = agora or datetime.now().astimezone()
    base = time.time_ns()
    if png:
        arq = (p / f"{base}.png").resolve()
        arq.write_bytes(png)
        imagem = str(arq)
    item = {"texto": texto, "imagem": imagem or None, "criado": quando.isoformat(), "loja": loja}
    if preview:
        item["preview"] = preview
    nome = p / f"{base}.json"
    tmp = nome.with_suffix(".tmp")
    tmp.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    tmp.rename(nome)
    return True


def enfileirar_oferta(oferta, texto, agora=None, loja="ml"):
    """Oferta para o grupo como texto com a prévia grande do link (foto + nome do produto),
    igual aos grupos de ofertas grandes. O serviço monta a prévia com a foto do anúncio;
    se não conseguir, manda a foto com o texto na legenda."""
    m = re.search(r"https?://\S+", texto or "")
    preview = None
    if m and getattr(oferta, "imagem", None):
        preview = {"link": m.group(0), "titulo": oferta.titulo, "imagem": oferta.imagem}
    return enfileirar(texto, getattr(oferta, "imagem", None), agora, loja, preview=preview)
