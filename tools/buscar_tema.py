"""Busca produtos para um carrossel temático. Uso: "termo 1; termo 2; ..."
Mostra os melhores resultados de cada termo e baixa a foto dos 3 primeiros para saida/."""
import os
import re
import sys
from pathlib import Path

import requests

from bot import busca
from bot.mercadolivre import MercadoLivre, link_produto, token_do_app

ml = MercadoLivre(token_do_app(os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"]))
saida = Path("saida")
saida.mkdir(exist_ok=True)
for termo in [t.strip() for t in " ".join(sys.argv[1:]).split(";") if t.strip()]:
    print("TERMO", termo)
    for k, r in enumerate(busca.pesquisar(ml, termo, log=lambda *_: None)[:5]):
        info = ml.catalogo(r["id"])
        print(f"  {k+1}. {r['titulo'][:80]} | R$ {r['preco']:.2f} | de {r['de']} | rank {r['rank']} | {link_produto('catalogo', r['id'])}")
        if k < 3 and info.imagem:
            nome = re.sub(r"\W+", "_", termo)[:30] + f"_{k+1}.jpg"
            try:
                (saida / nome).write_bytes(requests.get(info.imagem, timeout=30).content)
            except requests.RequestException:
                pass
