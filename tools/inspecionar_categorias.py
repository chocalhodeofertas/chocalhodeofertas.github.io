"""Imprime a árvore de categorias do ML (2 níveis) das raízes que interessam, com 3 exemplos de mais vendidos."""
import re
from bot.mercadolivre import MercadoLivre, token_do_app
from bot.filtros import normalizar
import os

ml = MercadoLivre(token_do_app(os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"]))
raizes = ml.categorias_raiz()
print("RAIZES:", raizes)
alvo = re.compile(r"calcados|roupas|games|livros|papelaria|esportes|casa|festas|brinquedos|bebes|eletronicos|beleza")
for rid, rn in raizes:
    if not alvo.search(normalizar(rn)):
        continue
    print(f"\n=== {rid} {rn}")
    for c, n in ml.subcategorias(rid):
        print(f"  {c} {n}")
        try:
            for c2, n2 in ml.subcategorias(c):
                print(f"      {c2} {n2}")
        except Exception as e:
            print("      erro", e)
