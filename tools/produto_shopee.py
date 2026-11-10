"""Mostra os dados de um produto da Shopee pela API (args: itemId) e baixa a foto para saida/."""
import json
import os
import sys
from pathlib import Path

import requests

from bot.shopee import _CAMPOS, Shopee

shp = Shopee(os.environ.get("SHOPEE_APP_ID"), os.environ.get("SHOPEE_SECRET"))
Path("saida").mkdir(exist_ok=True)
for item in (sys.argv[1] if len(sys.argv) > 1 else "").replace(",", " ").split():
    d = shp._chamar("{productOfferV2(itemId:%d,page:1,limit:1){nodes{%s productCatIds}}}" % (int(item), _CAMPOS))
    nos = (d.get("productOfferV2") or {}).get("nodes") or []
    print("PRODUTO", json.dumps(nos, ensure_ascii=False))
    for n in nos:
        if n.get("imageUrl"):
            Path(f"saida/shopee_{item}.jpg").write_bytes(requests.get(n["imageUrl"], timeout=30).content)
