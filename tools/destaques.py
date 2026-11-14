"""Produtos fortes por segmento: mais vendidos da categoria + desconto.
Uso: "segmento=termo; segmento=termo; ..." -> imprime e baixa a foto dos 3 melhores de cada um."""
import os
import re
import sys
from pathlib import Path

import requests

from bot import busca
from bot.mercadolivre import MercadoLivre, token_do_app

ml = MercadoLivre(token_do_app(os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"]))
saida = Path("saida")
saida.mkdir(exist_ok=True)
for par in [p.strip() for p in " ".join(sys.argv[1:]).split(";") if p.strip()]:
    seg, termo = par.split("=", 1)
    res = busca.pesquisar(ml, termo.strip(), log=lambda *_: None)
    # nota: top 20 mais vendidos pesa muito; desconto ajuda
    def nota(r):
        rk = r["rank"]
        return (2.0 if rk is not None and rk < 10 else 1.4 if rk is not None and rk < 20 else 1.0) * (0.3 + (r["desconto"] or 0))
    res.sort(key=nota, reverse=True)
    print("SEG", seg, "|", termo)
    for k, r in enumerate(res[:5]):
        rk = "-" if r["rank"] is None else r["rank"] + 1
        print(f"  {k+1}. top{rk} | {round((r['desconto'] or 0)*100)}% | R$ {r['preco']:.2f} | de {r['de']} | {r['id']} | {r['titulo'][:80]}")
        if k < 3:
            info = ml.catalogo(r["id"])
            if info.imagem:
                nome = re.sub(r"\W+", "_", seg)[:20] + f"_{k+1}_{r['id']}.jpg"
                try:
                    (saida / nome).write_bytes(requests.get(info.imagem, timeout=30).content)
                except requests.RequestException:
                    pass
