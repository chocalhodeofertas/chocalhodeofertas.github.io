"""Diagnóstico da API da Shopee: testa consultas mínimas e mostra o que a API responde."""
import os
from bot.shopee import Shopee, ShopeeErro

shp = Shopee(os.environ.get("SHOPEE_APP_ID"), os.environ.get("SHOPEE_SECRET"))
testes = {
    "oferta_shopee": "{shopeeOfferV2(page:1,limit:2){nodes{offerName commissionRate} pageInfo{hasNextPage}}}",
    "produto_min": "{productOfferV2(page:1,limit:2){nodes{itemId productName} pageInfo{hasNextPage}}}",
    "produto_kw_ascii": '{productOfferV2(keyword:"bebe",page:1,limit:2){nodes{itemId productName priceMin} pageInfo{hasNextPage}}}',
    "produto_kw_acento": '{productOfferV2(keyword:"bebê",page:1,limit:2){nodes{itemId productName} pageInfo{hasNextPage}}}',
    "produto_sort2": '{productOfferV2(keyword:"bebe",sortType:2,page:1,limit:2){nodes{itemId productName} pageInfo{hasNextPage}}}',
}
campos = ["priceMax", "priceDiscountRate", "commissionRate", "sales", "ratingStar", "imageUrl", "offerLink",
          "productLink", "shopName", "shopType", "periodEndTime"]
for c in campos:
    testes["campo_" + c] = '{productOfferV2(keyword:"bebe",page:1,limit:1){nodes{itemId %s} pageInfo{hasNextPage}}}' % c
for nome, q in testes.items():
    try:
        r = shp._chamar(q)
        print("OK ", nome, str(r)[:300])
    except ShopeeErro as e:
        print("ERR", nome, e)
