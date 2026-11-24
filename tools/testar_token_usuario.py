"""Teste único (diagnóstico do 403 desde 23/11): troca o código de autorização por um token de USUÁRIO e testa,
com ele, os recursos do ML que o token do app perdeu. NÃO salva o token (o bot não muda). Não abre link de afiliado.

Uso (workflow inspecao): script=testar_token_usuario, args="<endereço com ?code=... ou só o código> <redirect_uri> [MLB...]"
"""
import json
import os
import sys

import requests

from bot.mercadolivre import _mascarar, token_do_app, trocar_codigo

API = "https://api.mercadolibre.com"
args = " ".join(sys.argv[1:]).split()
codigo, redirect, pids = args[0], args[1], args[2:]
if "code=" in codigo:
    codigo = codigo.split("code=", 1)[1].split("&", 1)[0]
if not pids:
    estado = json.load(open("data/estado.json", encoding="utf-8"))
    pids = list((estado.get("postados") or {}).keys())[-3:]
access, refresh = trocar_codigo(os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"], codigo, redirect)
_mascarar(access)
_mascarar(refresh)
app = token_do_app(os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"])
_mascarar(app)
for nome, tok in (("USUARIO", access), ("APP", app)):
    H = {"Authorization": f"Bearer {tok}"}
    print(f"\n===== token do {nome}")
    for pid in pids:
        r = requests.get(f"{API}/products/{pid}/items", params={"limit": 3}, headers=H, timeout=20)
        corpo = r.text[:220].replace("\n", " ")
        print(f"{r.status_code} /products/{pid}/items  {corpo if r.status_code != 200 else 'OK: ' + corpo}")
        r = requests.get(f"{API}/products/{pid}", headers=H, timeout=20)
        bw = r.json().get("buy_box_winner") if r.status_code == 200 else r.text[:120]
        print(f"{r.status_code} /products/{pid} buy_box_winner = {json.dumps(bw, ensure_ascii=False)[:220]}")
print("\n(tokens descartados; nada foi salvo)")
