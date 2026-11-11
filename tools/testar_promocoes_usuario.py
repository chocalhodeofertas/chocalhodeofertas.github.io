"""Teste único: troca o código de autorização por um token de USUÁRIO e testa a API
de promoções em anúncios de outros vendedores. NÃO salva o token (o bot não muda).
Uso: <endereço inteiro ou código> <redirect_uri> [MLB...]"""
import os
import sys

import requests

from bot.mercadolivre import _mascarar, trocar_codigo

args = " ".join(sys.argv[1:]).split()
codigo, redirect, itens = args[0], args[1], args[2:] or [
    "MLB6159946188", "MLB5274011035", "MLB5250275675", "MLB7052332238"]
if "code=" in codigo:
    codigo = codigo.split("code=", 1)[1].split("&", 1)[0]
access, refresh = trocar_codigo(os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"], codigo, redirect)
_mascarar(access)
_mascarar(refresh)
H = {"Authorization": f"Bearer {access}"}
me = requests.get("https://api.mercadolibre.com/users/me", headers=H, timeout=30).json()
print("Conta autorizada:", me.get("nickname"), "| escopos do token:",
      requests.get("https://api.mercadolibre.com/users/me", headers=H, timeout=30).headers.get("x-scopes", "?"))
for item in itens:
    for url in (f"/seller-promotions/items/{item}?app_version=v2",
                f"/items/{item}/sale_price?context=channel_marketplace"):
        r = requests.get("https://api.mercadolibre.com" + url, headers=H, timeout=30)
        print(f"\n### {url} -> {r.status_code}\n{r.text[:900]}")
print("\n(token descartado; nada foi salvo)")
