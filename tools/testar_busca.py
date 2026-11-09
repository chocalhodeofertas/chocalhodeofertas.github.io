"""Testa quais endpoints de busca do ML aceitam o token do app."""
import json, os
from bot.mercadolivre import MercadoLivre, token_do_app

ml = MercadoLivre(token_do_app(os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"]))
testes = [
    ("/sites/MLB/search", {"q": "cadeirinha isofix", "limit": 5}),
    ("/products/search", {"status": "active", "site_id": "MLB", "q": "cadeirinha isofix", "limit": 5}),
    ("/sites/MLB/domain_discovery/search", {"q": "cadeirinha isofix", "limit": 3}),
]
for caminho, params in testes:
    try:
        d = ml._get(caminho, params)
        txt = json.dumps(d, ensure_ascii=False)
        print("OK", caminho, len(txt), txt[:1500])
    except Exception as e:
        print("ERRO", caminho, type(e).__name__, str(e)[:300])
