"""Sonda (só leitura, só API): de onde ainda dá para tirar o preço do catálogo depois do 403 em /products/{id}/items.

Mostra os campos de preço/vencedor de /products/{id} (buy_box_winner etc.) e testa /items/bulk e /items/{id}
com o anúncio vencedor. Não abre link de afiliado. Uso: script=sondar_preco_alternativo, args="MLB.. MLB.." (opcional)
"""
import json
import os
import sys

import requests

from bot.mercadolivre import token_do_app

API = "https://api.mercadolibre.com"
estado = json.load(open("data/estado.json", encoding="utf-8"))
pids = " ".join(sys.argv[1:]).split() or list((estado.get("postados") or {}).keys())[-4:]
H = {"Authorization": f"Bearer {token_do_app(os.environ.get('ML_CLIENT_ID'), os.environ.get('ML_CLIENT_SECRET'))}"}


def get(c):
    r = requests.get(API + c, headers=H, timeout=20)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, r.text[:200]


item = None
for pid in pids:
    st, p = get(f"/products/{pid}")
    if st != 200:
        print(pid, st, str(p)[:150])
        continue
    print(f"\n### {pid} {p.get('name', '')[:60]}  status={p.get('status')}")
    print("chaves:", sorted(p.keys()))
    for k in ("buy_box_winner", "buy_box_winner_price_range", "price", "prices", "settings"):
        if k in p:
            print(f"  {k}: {json.dumps(p[k], ensure_ascii=False)[:500]}")
    bw = p.get("buy_box_winner") or {}
    item = item or bw.get("item_id")
print()
if item:
    for c in (f"/items/{item}", f"/items/bulk?ids={item}", f"/items?ids={item}", f"/items/{item}/sale_price?context=channel_marketplace",
              f"/items/{item}/prices"):
        st, b = get(c)
        print(st, c, json.dumps(b, ensure_ascii=False)[:300] if st != 200 else "OK " + json.dumps(b, ensure_ascii=False)[:300])
st, h = get("/highlights/MLB/category/MLB1384")
print("\nhighlights", st, json.dumps(h, ensure_ascii=False)[:300])
