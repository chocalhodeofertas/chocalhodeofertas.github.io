"""Sonda (só leitura) o que a API oficial do ML devolve sobre preço: Pix, preço de venda, vencedor do catálogo.

Uso (workflow inspecao): script=sondar_precos_ml, args="MLBproduto:MLBanuncio ..."
"""
import json
import os
import sys

from bot.mercadolivre import MercadoLivre, token_do_app

ml = MercadoLivre(token_do_app(os.environ.get("ML_CLIENT_ID"), os.environ.get("ML_CLIENT_SECRET")))


def tenta(caminho, params=None):
    try:
        d = ml._get(caminho, params)
        return json.dumps(d, ensure_ascii=False)[:1500]
    except Exception as e:  # noqa: BLE001
        return f"ERRO {type(e).__name__}: {str(e)[:200]}"


for par in (sys.argv[1] if len(sys.argv) > 1 else "").split()[:4]:
    pid, item = par.split(":")
    print("=" * 20, pid, item)
    print("sale_price:", tenta(f"/items/{item}/sale_price", {"context": "channel_marketplace"}))
    print("prices:", tenta(f"/items/{item}/prices"))
    print("item:", tenta(f"/items/{item}", {"attributes": "id,price,base_price,original_price,sale_price,status,deal_ids,tags"}))
    try:
        d = ml._get(f"/products/{pid}")
        print("product keys:", sorted(d.keys()))
        print("buy_box_winner:", json.dumps(d.get("buy_box_winner"), ensure_ascii=False)[:1800])
        print("price_range:", json.dumps(d.get("buy_box_winner_price_range"), ensure_ascii=False)[:400])
    except Exception as e:  # noqa: BLE001
        print("product ERRO", type(e).__name__, str(e)[:200])
    try:
        d = ml._get(f"/products/{pid}/items", {"limit": 3})
        print("items keys:", sorted(d.keys()), "paging:", d.get("paging"))
        for o in d.get("results") or []:
            sid = o.get("seller_id")
            print("  anuncio", o.get("item_id"), o.get("price"), "loja oficial:", o.get("official_store_id"), "vendedor", sid)
            print("   users:", tenta(f"/users/{sid}")[:700])
    except Exception as e:  # noqa: BLE001
        print("items ERRO", type(e).__name__, str(e)[:200])
