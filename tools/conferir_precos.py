"""Confere os posts do dia: preço que saiu no post x preço de agora nas lojas (tudo pela API oficial).

Só leitura: não posta nem grava nada no estado. NÃO abre os links de afiliado (regra do Leonardo, 16/11):
qual anúncio o link abre vem de estado.links_item, gravado quando o lote foi respondido. Resultado em saida/conferir_precos.json e no log.
Uso (workflow inspecao): script=conferir_precos, args="[quantos]" (padrão: todos os do dia).
"""
import json
import os
import sys

from bot import estado as est
from bot.mercadolivre import MercadoLivre, token_do_app

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

saida, bruto = [], None
for i in itens:
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
    except Exception as e:  # noqa: BLE001
        reg["erro"] = f"{type(e).__name__}: {str(e)[:80]}"
    saida.append(reg)
    print(json.dumps(reg, ensure_ascii=False))

print("EXEMPLO BRUTO:", json.dumps(bruto, ensure_ascii=False)[:3000])
os.makedirs("saida", exist_ok=True)
with open("saida/conferir_precos.json", "w", encoding="utf-8") as f:
    json.dump({"itens": saida, "bruto": bruto}, f, ensure_ascii=False, indent=1)
