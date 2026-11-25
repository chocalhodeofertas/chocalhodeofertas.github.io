"""Sonda (25/11): o link de afiliado de OUTRO canal, quando aberto, mostra o preço do produto?

Pega links meli.la de alguns canais públicos de ofertas pela página pública t.me/s/<canal> (sem usar a sessão do
Telegram do bot), abre cada um como navegador (como o espelho já faz) e mostra: para onde foi, se caiu em verificação
de conta e o que o card do produto (JSON "polycards") traz de preço e cupom. Nunca abre link do Leonardo.
Uso: script=sondar_pagina_alheia, args="canal canal" (opcional)
"""
import json
import re
import sys

import requests

from bot.espelho import _UA

canais = " ".join(sys.argv[1:]).split() or ["babypromokids", "descontinhodemamae", "economiadasmamaes"]
proprios = re.compile(r"chocalho", re.I)
links = []
for c in canais:
    try:
        h = requests.get(f"https://t.me/s/{c}", headers=_UA, timeout=20).text
    except requests.RequestException as e:
        print("canal", c, "erro", e)
        continue
    achados = list(dict.fromkeys(re.findall(r"https?://meli\.la/[A-Za-z0-9]+", h)))
    print(f"canal {c}: {len(achados)} links meli.la")
    links += [(c, u) for u in achados[-3:]]

from bot import espelho  # noqa: E402

print("\n== com as funções do bot (espelho.ler_pagina / _pagina_util)")
for canal, url in links[:6]:
    final, cartao = espelho.ler_pagina(url)
    print(f"@{canal}: útil={espelho._pagina_util(cartao)} | {json.dumps(cartao, ensure_ascii=False)[:230]}")
print()
for canal, url in links[:0]:
    if proprios.search(canal):
        continue
    try:
        r = requests.get(url, headers={**_UA, "Accept-Language": "pt-BR,pt;q=0.9"}, timeout=25)
    except requests.RequestException as e:
        print("\nERRO", canal, type(e).__name__)
        continue
    final = r.url.split("?")[0]
    h = r.text or ""
    print(f"\n### @{canal} -> {r.status_code} {final[:90]}")
    print("   verificação de conta:", "account-verification" in r.url or "account-verification" in h[:5000])
    i = h.find('"polycards":')
    if i < 0:
        m = re.search(r'"price"\s*:\s*\{[^{}]*"amount"\s*:\s*([\d.]+)', h) or re.search(r'itemprop="price" content="([\d.]+)"', h)
        print("   sem polycards; preço na página:", m.group(1) if m else "não achei")
        continue
    cards, _ = json.JSONDecoder().raw_decode(h[i + 12:])
    c0 = cards[0] if cards else {}
    comps = {x.get("type"): x.get(x.get("type")) for x in c0.get("components", [])}
    pr = comps.get("price") or {}
    print("   produto:", (c0.get("metadata") or {}).get("product_id"), "anúncio:", (c0.get("metadata") or {}).get("id"),
          "|", (comps.get("title") or {}).get("text", "")[:50])
    print("   preço:", (pr.get("current_price") or {}).get("value"), "de:", (pr.get("previous_price") or {}).get("value"),
          "| selo:", (pr.get("discount_label") or {}).get("text"), "| cupom:",
          json.dumps(comps.get("promotions"), ensure_ascii=False)[:120])
