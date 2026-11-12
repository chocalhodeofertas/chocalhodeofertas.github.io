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


def enfileirar(texto, imagem=None, agora=None, loja="ml", png=None):
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
    nome = p / f"{base}.json"
    tmp = nome.with_suffix(".tmp")
    tmp.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    tmp.rename(nome)
    return True


def enfileirar_oferta(oferta, texto, agora=None, loja="ml"):
    """Oferta para o grupo com a arte do Chocalho (foto do produto + preço na identidade).

    Se a arte falhar (ex.: foto fora do ar), vai com a foto do anúncio mesmo.
    """
    if not os.environ.get("WA_FILA"):
        return False
    png = None
    try:
        from . import arte

        png = arte.gerar(oferta, cta="Link abaixo")
    except Exception as e:  # noqa: BLE001
        print(f"Aviso: arte do WhatsApp falhou ({type(e).__name__}); vai a foto do anúncio.")
    return enfileirar(texto, getattr(oferta, "imagem", None), agora, loja, png=png)
