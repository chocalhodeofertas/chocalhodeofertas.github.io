"""Baixa a foto principal de produtos do catálogo do ML. Uso: "MLB1 MLB2 ..." -> saida/<id>.jpg"""
import os
import sys
from pathlib import Path

import requests

from bot.mercadolivre import MercadoLivre, token_do_app

ml = MercadoLivre(token_do_app(os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"]))
saida = Path("saida")
saida.mkdir(exist_ok=True)
for pid in " ".join(sys.argv[1:]).split():
    info = ml.catalogo(pid)
    print(pid, info.titulo if hasattr(info, "titulo") else "", info.imagem)
    if info.imagem:
        url = info.imagem.replace("-I.jpg", "-O.jpg")
        try:
            (saida / f"{pid}.jpg").write_bytes(requests.get(url, timeout=30).content)
        except requests.RequestException as erro:
            print("  falhou", erro)
