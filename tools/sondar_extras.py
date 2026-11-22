"""Sonda (só leitura) para decidir três coisas, sem abrir nenhum link de afiliado:

1. O que a API do Mercado Livre informa por anúncio (frete grátis, Full, Pix, cupom, promoções).
2. Se a página PÚBLICA do produto (mercadolivre.com.br/p/MLB..., endereço comum, sem afiliado) abre a partir do
   servidor do GitHub e o que ela mostra de Pix e cupom.
3. Por que a busca "fralda g" não trouxe nada da Shopee (motivo de cada produto recusado).

Uso (workflow inspecao): script=sondar_extras, args="MLBprod MLBprod ...; termo da shopee"
"""
import json
import os
import re
import sys
import time

import requests

from bot.mercadolivre import MercadoLivre, token_do_app
from bot.shopee import MAIS_VENDIDOS, Shopee
from bot.shopee_ofertas import aprovado

args = sys.argv[1] if len(sys.argv) > 1 else ""
pids, _, termo = args.partition(";")
pids = [p for p in pids.split() if re.fullmatch(r"MLB\d+", p)][:4]
termo = termo.strip() or "fralda g"
os.makedirs("saida", exist_ok=True)

ml = MercadoLivre(token_do_app(os.environ.get("ML_CLIENT_ID"), os.environ.get("ML_CLIENT_SECRET")))
print("#" * 10, "1. API do Mercado Livre por anúncio")
for pid in pids:
    try:
        d = ml._get(f"/products/{pid}/items", {"limit": 2})
    except Exception as e:  # noqa: BLE001
        print(pid, "ERRO", type(e).__name__, str(e)[:150])
        continue
    for o in (d.get("results") or [])[:2]:
        print("=" * 8, pid, o.get("item_id"), "chaves:", sorted(o.keys()))
        print("  shipping:", json.dumps(o.get("shipping"), ensure_ascii=False)[:300])
        for k in ("price", "original_price", "sale_price", "tags", "deal_ids", "sale_terms", "promotions",
                  "installments", "official_store_id", "condition", "warranty"):
            if k in o:
                print(f"  {k}:", json.dumps(o.get(k), ensure_ascii=False)[:300])

print("#" * 10, "2. Página pública do produto (sem afiliado)")
NAV = {"User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/124.0 Mobile Safari/537.36", "Accept-Language": "pt-BR,pt;q=0.9"}
for pid in pids[:2]:
    url = f"https://www.mercadolivre.com.br/p/{pid}"
    try:
        r = requests.get(url, headers=NAV, timeout=25, allow_redirects=True)
    except requests.RequestException as e:
        print(url, "erro", type(e).__name__)
        continue
    h = r.text
    final = r.url.split("?")[0]
    print(url, "->", r.status_code, len(h), "final:", final[:120])
    if any(x in r.url for x in ("meli.la", "matt_tool", "matt_word")):
        print("  ATENÇÃO: redirecionou para endereço de afiliado; parei.")
        continue
    print("  titulo:", (re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1][:120])
    print("  pix:", [re.sub(r"<[^>]+>|\s+", " ", x)[:120] for x in re.findall(r".{120}no Pix.{40}", h)[:3]])
    print("  cupom:", [re.sub(r"<[^>]+>|\s+", " ", x)[:140] for x in re.findall(r".{80}[Cc]upom.{80}", h)[:3]])
    print("  bloqueio?:", bool(re.search(r"captcha|account-verification|negative_traffic", h, re.I)))
    time.sleep(3)

shp = Shopee(os.environ.get("SHOPEE_APP_ID"), os.environ.get("SHOPEE_SECRET"))
for t in [x.strip() for x in termo.split("|") if x.strip()][:4]:
    print("#" * 10, f"3. Shopee: '{t}'")
    try:
        achados = shp.buscar(t, ordem=MAIS_VENDIDOS, limite=30)
    except Exception as e:  # noqa: BLE001
        print("  ERRO", type(e).__name__, str(e)[:150])
        continue
    print("vieram", len(achados))
    for p in achados:
        print(f"  {aprovado(p) or 'OK':14} {p.id} nota {p.nota} vendas {p.vendas} comissão {p.comissao:.3f} R$ {p.preco} | {p.titulo[:70]}")
