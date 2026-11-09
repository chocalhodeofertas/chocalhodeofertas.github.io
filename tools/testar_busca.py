"""Testa a busca do bot com termos reais."""
import os
from bot.mercadolivre import MercadoLivre, token_do_app
from bot import busca

ml = MercadoLivre(token_do_app(os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"]))
for termo in ["cadeirinha isofix", "fralda pampers g", "cartas pokemon"]:
    print("TERMO", termo)
    for r in busca.pesquisar(ml, termo):
        print("  RES", r["titulo"][:60], r["preco"], r["de"], round(r["desconto"] * 100), r["rank"])
