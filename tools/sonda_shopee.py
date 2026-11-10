"""Sonda: lista os catálogos (feeds) da Shopee e mostra as colunas de um deles."""
import json
import os
from bot.shopee import Shopee

shp = Shopee(os.environ.get("SHOPEE_APP_ID"), os.environ.get("SHOPEE_SECRET"))
feeds = shp._chamar("{listItemFeeds(feedMode:FULL){feeds{datafeedId datafeedName totalCount date feedMode}}}")
lista = (feeds.get("listItemFeeds") or {}).get("feeds") or []
print("FEEDS", len(lista))
for f in lista:
    print("FEED", f)
alvo = next((f for f in lista if any(p in f["datafeedName"].lower() for p in ("baby", "bebê", "bebe", "kid", "toy", "brinquedo", "mom"))), lista[0] if lista else None)
if alvo:
    d = shp._chamar('{getItemFeedData(datafeedId:%s,offset:0,limit:3){rows{columns} pageInfo{totalCount hasMore}}}' % json.dumps(alvo["datafeedId"]))
    for r in d["getItemFeedData"]["rows"]:
        print("LINHA", r["columns"][:3000])
