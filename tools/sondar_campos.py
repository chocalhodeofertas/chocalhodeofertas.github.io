"""Sonda (só leitura) TUDO o que as APIs do Mercado Livre e da Shopee entregam sobre um produto.

Serve para decidir o que dá para usar além de nome e preço (marca, modelo, código de barras, fotos,
descrição, categoria...), por exemplo para reconhecer o mesmo produto com títulos diferentes.
Não abre nenhum link de afiliado: só endereços da API (api.mercadolibre.com e a Open API da Shopee).

Uso (workflow inspecao): script=sondar_campos, args="MLB1 MLB2 ...; itemId itemId ..."
Grava saida/campos_ml.json e saida/campos_shopee.json e imprime um resumo.
"""
import json
import os
import re
import sys

from bot.mercadolivre import MercadoLivre, token_do_app
from bot.shopee import Shopee, _CAMPOS

args = sys.argv[1] if len(sys.argv) > 1 else ""
p_ml, _, p_shp = args.partition(";")
pids = [p for p in p_ml.split() if re.fullmatch(r"MLB\d+", p)][:6]
itens_shp = [int(i) for i in re.findall(r"\d{6,}", p_shp)][:4]
os.makedirs("saida", exist_ok=True)


def curto(v, n=300):
    t = json.dumps(v, ensure_ascii=False)
    return t if len(t) <= n else t[:n] + "…"


def tentar(f, *a, **k):
    try:
        return f(*a, **k), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:200]}"


# ---------------- Mercado Livre ----------------
ml = MercadoLivre(token_do_app(os.environ.get("ML_CLIENT_ID"), os.environ.get("ML_CLIENT_SECRET")))
saida_ml = {}
print("#" * 10, "MERCADO LIVRE")
for pid in pids:
    r = {}
    prod, erro = tentar(ml._get, f"/products/{pid}")
    if erro:
        print(pid, "products ERRO", erro)
        r["products_erro"] = erro
    else:
        r["products_chaves"] = sorted(prod.keys())
        r["products"] = {k: prod.get(k) for k in ("id", "name", "family_name", "domain_id", "parent_id", "status",
                                                  "short_description", "main_features", "buy_box_winner",
                                                  "permalink", "catalog_product_id", "children_ids", "settings",
                                                  "pickers", "description_pictures", "date_created")}
        r["atributos"] = [{"id": a.get("id"), "nome": a.get("name"), "valor": a.get("value_name")}
                          for a in prod.get("attributes") or []]
        r["fotos"] = [f.get("url") for f in (prod.get("pictures") or [])][:8]
        print("=" * 6, pid, prod.get("name"))
        print("  chaves:", ", ".join(r["products_chaves"]))
        print("  atributos:", "; ".join(f"{a['id']}={a['valor']}" for a in r["atributos"])[:900])
        print("  fotos:", len(prod.get("pictures") or []), "| short_description:",
              curto(prod.get("short_description"), 160))
    anuncios, erro = tentar(ml._get, f"/products/{pid}/items", {"limit": 3})
    if erro:
        r["items_erro"] = erro
    else:
        res = (anuncios or {}).get("results") or []
        r["anuncio_chaves"] = sorted(res[0].keys()) if res else []
        r["anuncios"] = res[:2]
        print("  anúncio (products/items) chaves:", ", ".join(r["anuncio_chaves"]))
        if res:
            item_id = res[0].get("item_id")
            for caminho in (f"/items/{item_id}", f"/items/{item_id}/description", f"/items?ids={item_id}"):
                d, erro = tentar(ml._get, caminho)
                r[caminho] = erro or (sorted(d.keys()) if isinstance(d, dict) else curto(d, 600))
                print(f"  {caminho}:", (erro or curto(r[caminho], 300)))
            cat = res[0].get("category_id")
            if cat:
                d, erro = tentar(ml._get, f"/categories/{cat}")
                r["categoria"] = erro or {"nome": (d or {}).get("name"),
                                          "caminho": [c.get("name") for c in (d or {}).get("path_from_root") or []]}
                print("  categoria:", curto(r["categoria"], 200))
    saida_ml[pid] = r

# Busca de catálogo por nome (para achar o mesmo produto com outro título) e por código de barras
for termo in ["pato dançante caranguejo fujão", "pelucia banguela furia da noite 100cm"]:
    d, erro = tentar(ml._get, "/products/search", {"status": "active", "site_id": "MLB", "q": termo, "limit": 5})
    saida_ml[f"busca:{termo}"] = erro or [(x.get("id"), x.get("name")) for x in (d or {}).get("results") or []]
    print("  busca catálogo", termo, "->", curto(saida_ml[f"busca:{termo}"], 400))
gtins = [a["valor"] for r in saida_ml.values() if isinstance(r, dict) for a in r.get("atributos") or []
         if a["id"] == "GTIN" and a["valor"]]
if gtins:
    g = gtins[0].split(",")[0].strip()
    d, erro = tentar(ml._get, "/products/search", {"status": "active", "site_id": "MLB", "product_identifier": g})
    saida_ml[f"gtin:{g}"] = erro or [(x.get("id"), x.get("name")) for x in (d or {}).get("results") or []]
    print("  busca por GTIN", g, "->", curto(saida_ml[f"gtin:{g}"], 400))
d, erro = tentar(ml._get, "/sites/MLB/search", {"q": "pato dançante", "limit": 2})
print("  /sites/MLB/search:", erro or "funciona")
json.dump(saida_ml, open("saida/campos_ml.json", "w"), ensure_ascii=False, indent=1)

# ---------------- Shopee ----------------
print("#" * 10, "SHOPEE")
shp = Shopee(os.environ["SHOPEE_APP_ID"], os.environ["SHOPEE_SECRET"])
saida_shp = {}
for nome in ("ProductOfferV2", "ProductOfferV2Node", "ProductOffer"):
    d, erro = tentar(shp._chamar, '{__type(name:"%s"){name fields{name type{name kind ofType{name}}}}}' % nome, 1)
    tipo = (d or {}).get("__type")
    saida_shp[f"tipo:{nome}"] = erro or tipo
    print(f"  tipo {nome}:", erro or (", ".join(f["name"] for f in (tipo or {}).get("fields") or []) or "não existe"))
d, erro = tentar(shp._chamar, "{__schema{queryType{fields{name args{name}}}}}", 1)
saida_shp["consultas"] = erro or d
print("  consultas da API:", erro or ", ".join(f["name"] for f in d["__schema"]["queryType"]["fields"]))

EXTRAS = ["productCatIds", "shopId", "priceDiscountRate", "sellerCommissionRate", "shopeeCommissionRate",
          "periodStartTime", "appExistRate", "appNewRate", "webExistRate", "webNewRate", "ratingCount",
          "itemRating", "price", "imageUrls", "productDescription", "description", "brand", "modelId",
          "stock", "likedCount", "shopRating", "originalPrice", "discount"]
for item in itens_shp:
    campos_ok, recusados = [], []
    for c in _CAMPOS.split() + EXTRAS:
        q = "{productOfferV2(itemId:%d,page:1,limit:1){nodes{%s}}}" % (item, c)
        d, erro = tentar(shp._chamar, q, 1)
        if erro:
            recusados.append(c)
        else:
            campos_ok.append(c)
    q = "{productOfferV2(itemId:%d,page:1,limit:1){nodes{%s}}}" % (item, " ".join(campos_ok))
    d, erro = tentar(shp._chamar, q, 2)
    nos = [{k: v for k, v in n.items() if k not in ("offerLink", "productLink")}  # sem links no repositório público
           for n in ((d or {}).get("productOfferV2") or {}).get("nodes") or []]
    saida_shp[str(item)] = {"campos_que_existem": campos_ok, "recusados": recusados, "dados": nos[:1]}
    print("=" * 6, item)
    print("  campos que existem:", ", ".join(campos_ok))
    print("  não existem:", ", ".join(recusados))
    if nos:
        print("  dados:", curto(nos[0], 900))
json.dump(saida_shp, open("saida/campos_shopee.json", "w"), ensure_ascii=False, indent=1)
print("Pronto: saida/campos_ml.json e saida/campos_shopee.json")
