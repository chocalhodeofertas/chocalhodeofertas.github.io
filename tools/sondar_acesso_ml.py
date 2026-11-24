"""Sonda (só leitura, só API): o que a API do ML responde hoje, com o token do app e sem token.

Diagnóstico do 403 PolicyAgent em /products/{id}/items (desde 23/11). Não abre link de afiliado nem página de produto.
Uso (workflow inspecao): script=sondar_acesso_ml, args="MLB.. MLB.." (opcional; padrão: 3 produtos do histórico)
"""
import json
import os
import sys

import requests

from bot.mercadolivre import token_do_app

API = "https://api.mercadolibre.com"
estado = json.load(open("data/estado.json", encoding="utf-8"))
pids = " ".join(sys.argv[1:]).split() or list((estado.get("postados") or {}).keys())[-3:]
try:
    tok = token_do_app(os.environ.get("ML_CLIENT_ID"), os.environ.get("ML_CLIENT_SECRET"))
    print("token do app: obtido")
except Exception as e:  # noqa: BLE001
    tok = None
    print("token do app: FALHOU", type(e).__name__, str(e)[:200])

pid = pids[0]
caminhos = [
    f"/products/{pid}",
    f"/products/{pid}/items?limit=5",
    "/products/search?status=active&site_id=MLB&q=fralda&limit=2",
    "/highlights/MLB/category/MLB1384",
    "/sites/MLB/search?q=fralda&limit=2",
    "/sites/MLB/categories",
    "/categories/MLB1384",
    "/users/me",
]
for c in caminhos:
    for nome, h in (("com token", {"Authorization": f"Bearer {tok}"} if tok else None), ("sem token", {})):
        if h is None:
            continue
        try:
            r = requests.get(API + c, headers=h, timeout=20)
            corpo = r.text[:160].replace("\n", " ")
            print(f"{r.status_code} {nome:9} {c}  {corpo if r.status_code != 200 else ''}")
        except Exception as e:  # noqa: BLE001
            print("ERRO", nome, c, type(e).__name__)
for p in pids[1:]:
    r = requests.get(f"{API}/products/{p}/items?limit=2", headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    print(r.status_code, "com token", f"/products/{p}/items")
