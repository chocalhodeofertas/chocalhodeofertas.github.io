"""Uma tentativa em /products/{id}/items com o token do app, mostrando horário e cabeçalhos de identificação da
resposta (para o suporte do ML). Não mostra o token. Uso: script=tentativa_items, args="MLB82440483" (opcional)"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from bot.mercadolivre import _mascarar, token_do_app

pid = (" ".join(sys.argv[1:]).split() or ["MLB82440483"])[0]
tok = token_do_app(os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"])
_mascarar(tok)
url = f"https://api.mercadolibre.com/products/{pid}/items?limit=5"
antes = datetime.now(ZoneInfo("America/Sao_Paulo"))
r = requests.get(url, headers={"Authorization": f"Bearer {tok}"}, timeout=20)
print("TENTATIVA", antes.isoformat(timespec="seconds"), "(America/Sao_Paulo)")
print("GET", url)
print("HTTP", r.status_code)
print("CORPO", r.text[:300])
for k, v in r.headers.items():
    if any(x in k.lower() for x in ("request", "trace", "date", "x-")):
        print("CABECALHO", k, "=", v)
