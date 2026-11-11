"""Teste: o que a API de promoções do ML devolve para anúncios de outros vendedores.
Usa só o token do app (client credentials): não mexe no refresh_token do bot.
Uso: MLBitem MLBitem ..."""
import os
import sys

import requests

from bot.mercadolivre import token_do_app

tok = token_do_app(os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"])
H = {"Authorization": f"Bearer {tok}"}
for item in " ".join(sys.argv[1:]).split():
    for url in (f"https://api.mercadolibre.com/seller-promotions/items/{item}?app_version=v2",
                f"https://api.mercadolibre.com/items/{item}/sale_price?context=channel_marketplace",
                f"https://api.mercadolibre.com/items/{item}/prices"):
        r = requests.get(url, headers=H, timeout=30)
        print(f"\n### {url.split('.com')[1]} -> {r.status_code}\n{r.text[:700]}")
