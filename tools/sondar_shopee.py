"""Sonda a API de afiliados da Shopee: categorias dos produtos infantis e tipos de lista.

Só leitura; não posta nada. Uso: python -m tools.sondar_shopee
"""
import collections
import json
import os

from bot.shopee import MAIS_VENDIDOS, Shopee, ShopeeErro, _CAMPOS, converter
from bot.shopee_ofertas import aprovado


def consulta(shp, args, campos=_CAMPOS + " productCatIds"):
    q = "{productOfferV2(%s){nodes{%s} pageInfo{hasNextPage}}}" % (",".join(args), campos)
    return (shp._chamar(q, tentativas=3).get("productOfferV2") or {}).get("nodes") or []


def resumo(nos, n=4):
    ps = [converter(x) for x in nos if x.get("offerLink")]
    ok = [p for p in ps if not aprovado(p)]
    exemplos = " | ".join(p.titulo[:38] for p in (ok or ps)[:n])
    return f"{len(ps)} produtos, {len(ok)} aprovados pelas nossas regras. Ex.: {exemplos}"


def main():
    shp = Shopee(os.environ["SHOPEE_APP_ID"], os.environ["SHOPEE_SECRET"])
    print("## Categorias que aparecem nas buscas infantis")
    cont = collections.Counter()
    for termo in ["fralda", "brinquedo educativo", "body bebê", "mochila infantil", "roupa infantil", "banheira bebê",
                  "boneca", "livro infantil", "tênis infantil", "carrinho de bebê"]:
        try:
            nos = consulta(shp, [f"keyword:{json.dumps(termo, ensure_ascii=False)}", f"sortType:{MAIS_VENDIDOS}",
                                 "page:1", "limit:50"])
        except ShopeeErro as e:
            print(f"- {termo}: ERRO {e}")
            continue
        local = collections.Counter(tuple(x.get("productCatIds") or []) for x in nos)
        cont.update(local)
        print(f"- {termo}: {local.most_common(3)}")
    print("\nMais comuns no geral:", cont.most_common(15))

    print("\n## Busca só por categoria (sem palavra)")
    niveis = collections.Counter()
    for caminho, n in cont.items():
        for cid in caminho[:2]:
            niveis[cid] += n
    for cid, _ in niveis.most_common(10):
        for ordem in (2, 5):
            try:
                nos = consulta(shp, [f"productCatId:{int(cid)}", f"sortType:{ordem}", "page:1", "limit:50"])
                print(f"- cat {cid} ordem {ordem}: {resumo(nos)}")
            except ShopeeErro as e:
                print(f"- cat {cid} ordem {ordem}: ERRO {e}")

    print("\n## Tipos de lista (listType), sem palavra")
    for lt in range(0, 8):
        try:
            nos = consulta(shp, [f"listType:{lt}", "page:1", "limit:50"])
            print(f"- listType {lt}: {resumo(nos)}")
        except ShopeeErro as e:
            print(f"- listType {lt}: ERRO {e}")
    top = [cid for cid, _ in niveis.most_common(3)]
    for lt in (3, 4):
        for cid in top:
            try:
                nos = consulta(shp, [f"listType:{lt}", f"matchId:{int(cid)}", "page:1", "limit:50"])
                print(f"- listType {lt} matchId {cid}: {resumo(nos)}")
            except ShopeeErro as e:
                print(f"- listType {lt} matchId {cid}: ERRO {e}")

    print("\n## Outras consultas")
    for nome, q in [
        ("shopeeOfferV2", "{shopeeOfferV2(page:1,limit:10){nodes{offerName offerLink commissionRate offerType categoryId periodEndTime}}}"),
        ("shopOfferV2", "{shopOfferV2(page:1,limit:5){nodes{shopName commissionRate offerLink}}}"),
        ("isAMSOffer", "{productOfferV2(isAMSOffer:true,page:1,limit:5){nodes{productName commissionRate}}}"),
    ]:
        try:
            d = shp._chamar(q, tentativas=2)
            print(f"- {nome}: {json.dumps(d, ensure_ascii=False)[:600]}")
        except ShopeeErro as e:
            print(f"- {nome}: ERRO {e}")


if __name__ == "__main__":
    main()
