"""Confere os posts do dia: preço que saiu no post x preço de agora nas lojas, e para onde o link leva.

Só leitura: não posta nem grava nada no estado. Resultado em saida/conferir_precos.json e no log.
Uso (workflow inspecao): script=conferir_precos, args="[quantos]" (padrão: todos os do dia).
"""
import json
import os
import re
import sys
import time

import requests

from bot import estado as est
from bot.mercadolivre import API, MercadoLivre, token_do_app

quantos = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].strip().isdigit() else 999
estado = est.carregar("data/estado.json")
itens = ((estado.get("posts_dia") or {}).get("itens") or [])[:quantos]
ml = MercadoLivre(token_do_app(os.environ.get("ML_CLIENT_ID"), os.environ.get("ML_CLIENT_SECRET")))
shp = None
try:
    from bot.shopee import Shopee
    shp = Shopee(os.environ.get("SHOPEE_APP_ID"), os.environ.get("SHOPEE_SECRET"))
except Exception as e:  # noqa: BLE001
    print("Shopee indisponível:", type(e).__name__)

NAVEGADOR = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/124.0 Mobile Safari/537.36", "Accept-Language": "pt-BR,pt;q=0.9"}


def destino(link):
    """Para onde o link oficial leva (só segue os redirecionamentos; não lê a página)."""
    try:
        r = requests.get(link, headers=NAVEGADOR, timeout=20, allow_redirects=True, stream=True)
        url = r.url
        r.close()
        return re.sub(r"[?&](matt_\w+|ref|forceInApp|tracking_id)=[^&#]*", "", url)[:200]
    except requests.RequestException as e:
        return f"erro: {type(e).__name__}"


saida, bruto = [], None
for n, i in enumerate(itens):
    reg = {"id": i["id"], "loja": i["loja"], "titulo": i["titulo"][:60], "post": i["preco"], "de": i.get("de")}
    try:
        if i["loja"] == "shopee":
            p = shp.item(int(str(i["id"]).removeprefix("SHP"))) if shp else None
            reg["agora"] = p.preco if p else None
            reg["agora_max"] = getattr(p, "preco_max", None) if p else None
            reg["a_partir"] = i.get("a_partir")
        else:
            dados = ml._get(f"/products/{i['id']}/items", {"limit": 20})
            ofertas = [o for o in dados.get("results") or [] if o.get("price")]
            if bruto is None and ofertas:
                bruto = ofertas[0]  # um exemplo completo do que a API devolve (para ver se há preço no Pix etc.)
            item_link = (estado.get("links_item") or {}).get(i["id"])
            precos = sorted({o["price"] for o in ofertas})
            reg.update({"item_link": item_link, "lojas": len(ofertas), "menor": precos[0] if precos else None,
                        "maior": precos[-1] if precos else None,
                        "do_link": next((o["price"] for o in ofertas if o.get("item_id") == item_link), None),
                        "vencedor": ofertas[0].get("item_id") if ofertas else None,
                        "preco_vencedor": ofertas[0].get("price") if ofertas else None})
            if n < 25:
                reg["destino"] = destino(i["link"])
                time.sleep(0.5)
    except Exception as e:  # noqa: BLE001
        reg["erro"] = f"{type(e).__name__}: {str(e)[:80]}"
    saida.append(reg)
    print(json.dumps(reg, ensure_ascii=False))

print("EXEMPLO BRUTO:", json.dumps(bruto, ensure_ascii=False)[:3000])
os.makedirs("saida", exist_ok=True)
with open("saida/conferir_precos.json", "w", encoding="utf-8") as f:
    json.dump({"itens": saida, "bruto": bruto}, f, ensure_ascii=False, indent=1)
