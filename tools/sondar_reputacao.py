"""Sonda (só leitura, só pela API): reputação do vendedor de cada anúncio do lote do Linkbuilder.

Para cada produto do lote pendente (estado["lote"]): o anúncio que entrou no lote (o vencedor quando ele foi montado),
o vendedor e a cor da reputação (users/{id}: seller_reputation.level_id), e se há outro anúncio do mesmo
catálogo com vendedor verde e preço até 5% maior. Não abre nenhum link (nem de afiliado, nem de produto).

Uso (workflow inspecao): script=sondar_reputacao
"""
import json
import os
import re

from bot.mercadolivre import ErroML, MercadoLivre, token_do_app

ml = MercadoLivre(token_do_app(os.environ.get("ML_CLIENT_ID"), os.environ.get("ML_CLIENT_SECRET")))
estado = json.load(open("data/estado.json", encoding="utf-8"))
lote = estado.get("lote") or {}
cache = {}


def reputacao(seller_id):
    if seller_id not in cache:
        try:
            u = ml._get(f"/users/{seller_id}")
            r = u.get("seller_reputation") or {}
            cache[seller_id] = (r.get("level_id") or "sem cor", r.get("power_seller_status"), u.get("nickname"))
        except ErroML as e:
            cache[seller_id] = (f"erro {e}", None, None)
    return cache[seller_id]


linhas = []
for pid, url in zip(lote.get("ids", []), lote.get("urls", [])):
    m = re.search(r"MLB-(\d+)", url or "")
    item = f"MLB{m.group(1)}" if m else None
    try:
        dados = ml._get(f"/products/{pid}/items", {"limit": 20})
        nome = ml._get(f"/products/{pid}").get("name", "")[:60]
    except ErroML as e:
        print(pid, "erro", e)
        continue
    itens = dados.get("results") or []
    do_lote = next((i for i in itens if i.get("item_id") == item), None)
    if not do_lote:
        print(f"{pid} | {nome} | anúncio {item} não está mais entre os 20 primeiros ativos")
        continue
    cor, power, apelido = reputacao(do_lote["seller_id"])
    alt = ""
    if not str(cor).endswith(("green", "light_green")):
        for i in sorted(itens, key=lambda x: x.get("price") or 1e9):
            c, _, _ = reputacao(i["seller_id"])
            if str(c).endswith("green") and i.get("price") and i["price"] <= do_lote["price"] * 1.05:
                alt = f" | alternativa verde: {i['item_id']} R$ {i['price']:.2f} ({c})"
                break
    linhas.append(f"{pid} | {nome} | {item} R$ {do_lote['price']:.2f} | {apelido} | {cor} | {power or '-'}{alt}")
print("\n".join(linhas))
from collections import Counter  # noqa: E402

print("\nResumo das cores:", dict(Counter(x.split(" | ")[4] for x in linhas)))
