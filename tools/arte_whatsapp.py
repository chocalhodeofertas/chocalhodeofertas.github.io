"""Exemplos da arte que vai para o grupo do WhatsApp (1 do ML da vitrine + 1 da Shopee) em saida/."""
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bot import arte, shopee_ofertas
from bot.ofertas import Oferta
from bot.shopee import _CAMPOS, Shopee, converter

Path("saida").mkdir(exist_ok=True)
e = json.load(open("data/estado.json"))
v = e["vitrine"]["itens"][0]
ml = Oferta(id=v["id"], titulo=v["titulo"], preco=v["preco"], preco_de=v.get("de"), desconto=v.get("desconto") or 0,
            abaixo_do_habitual=None, menor_preco_historico=False, link=v["link"], imagem=v["imagem"],
            categoria=v.get("categoria", ""))
Path("saida/arte_wa_ml.png").write_bytes(arte.gerar(ml, cta="Link abaixo"))
shp = Shopee(os.environ.get("SHOPEE_APP_ID"), os.environ.get("SHOPEE_SECRET"))
item = sorted((e.get("shopee") or {}).get("postados", {}).items(), key=lambda x: x[1])[-1][0][3:]
d = shp._chamar("{productOfferV2(itemId:%s,page:1,limit:1){nodes{%s}}}" % (item, _CAMPOS))
p = converter(d["productOfferV2"]["nodes"][0])
o = shopee_ofertas.para_oferta(p, e, datetime.now(ZoneInfo("America/Sao_Paulo")))
Path("saida/arte_wa_shopee.png").write_bytes(arte.gerar(o, cta="Link abaixo"))
print("OK", ml.titulo, "|", o.titulo)
