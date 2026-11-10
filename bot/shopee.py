"""Cliente da API oficial de afiliados da Shopee (GraphQL).

Só usa a API oficial: nada de raspar o site. Os links que saem daqui são os
próprios links de afiliado da Shopee (offerLink / generateShortLink), sem
nenhuma alteração.
"""
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Optional

import requests

URL = "https://open-api.affiliate.shopee.com.br/graphql"

# Ordenação da busca de produtos (productOfferV2)
RELEVANCIA, MAIS_VENDIDOS, MAIOR_PRECO, MENOR_PRECO, MAIOR_COMISSAO = 1, 2, 3, 4, 5

_CAMPOS = ("itemId productName priceMin priceMax priceDiscountRate commissionRate sales ratingStar "
           "imageUrl offerLink productLink shopName shopType periodEndTime")


class ShopeeErro(Exception):
    pass


@dataclass
class ProdutoShopee:
    id: str
    titulo: str
    preco: float
    preco_de: Optional[float]
    desconto: float  # 0.30 = 30%
    comissao: float  # 0.08 = 8%
    vendas: int
    nota: float
    imagem: Optional[str]
    link: str  # link de afiliado da própria Shopee
    loja: str
    loja_oficial: bool


def assinatura(app_id, segredo, carga, ts):
    return hashlib.sha256(f"{app_id}{ts}{carga}{segredo}".encode()).hexdigest()


def _num(v, padrao=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return padrao


def converter(no):
    preco = _num(no.get("priceMin"))
    taxa = _num(no.get("priceDiscountRate")) / 100
    # A API só informa o preço atual e a taxa de desconto; o "de" sai da conta.
    preco_de = round(preco / (1 - taxa), 2) if 0 < taxa < 0.95 and preco else None
    tipos = no.get("shopType") or []
    return ProdutoShopee(
        id=f"SHP{no.get('itemId')}",
        titulo=(no.get("productName") or "").strip(),
        preco=preco,
        preco_de=preco_de,
        desconto=taxa if preco_de else 0.0,
        comissao=_num(no.get("commissionRate")),
        vendas=int(_num(no.get("sales"))),
        nota=_num(no.get("ratingStar")),
        imagem=no.get("imageUrl"),
        link=no.get("offerLink") or "",
        loja=no.get("shopName") or "",
        loja_oficial=1 in tipos or 2 in tipos,  # 1 = Shopee Mall, 2 = loja indicada
    )


class Shopee:
    def __init__(self, app_id, segredo, session=None, url=URL):
        if not app_id or not segredo:
            raise ShopeeErro("faltam SHOPEE_APP_ID / SHOPEE_SECRET")
        self.app_id, self.segredo, self.url = str(app_id), segredo, url
        self.s = session or requests.Session()

    def _chamar(self, consulta, tentativas=6, espera=2.0):
        """A API às vezes devolve "System Error" (10000) ou limite (10030) à toa: tenta de novo."""
        for k in range(tentativas):
            try:
                return self._chamar_uma(consulta)
            except ShopeeErro as e:
                if k == tentativas - 1 or not any(c in str(e) for c in ("(10000)", "(10030)", "conexão")):
                    raise
                time.sleep(espera * (k + 1))

    def _chamar_uma(self, consulta):
        carga = json.dumps({"query": consulta}, ensure_ascii=False)
        ts = int(time.time())
        cab = {
            "Content-Type": "application/json",
            "Authorization": f"SHA256 Credential={self.app_id}, Timestamp={ts}, "
                             f"Signature={assinatura(self.app_id, self.segredo, carga, ts)}",
        }
        try:
            r = self.s.post(self.url, data=carga.encode(), headers=cab, timeout=30)
            j = r.json()
        except (requests.RequestException, ValueError) as e:
            raise ShopeeErro(f"falha de conexão com a Shopee ({type(e).__name__})")
        if j.get("errors"):
            e = j["errors"][0]
            cod = (e.get("extensions") or {}).get("code")
            raise ShopeeErro(f"Shopee recusou ({cod}): {e.get('message')}")
        return j.get("data") or {}

    def buscar(self, termo="", ordem=MAIS_VENDIDOS, pagina=1, limite=50, categoria=None):
        args = [f"keyword:{json.dumps(termo, ensure_ascii=False)}", f"sortType:{ordem}",
                f"page:{pagina}", f"limit:{limite}"]
        if categoria:
            args.append(f"productCatId:{int(categoria)}")
        q = "{productOfferV2(%s){nodes{%s} pageInfo{hasNextPage}}}" % (",".join(args), _CAMPOS)
        dados = self._chamar(q).get("productOfferV2") or {}
        return [converter(n) for n in dados.get("nodes") or [] if n.get("offerLink")]

    def link_curto(self, url_original, sub_ids=None):
        subs = f",subIds:{json.dumps(sub_ids)}" if sub_ids else ""
        q = 'mutation{generateShortLink(input:{originUrl:%s%s}){shortLink}}' % (
            json.dumps(url_original), subs)
        return (self._chamar(q).get("generateShortLink") or {}).get("shortLink")
