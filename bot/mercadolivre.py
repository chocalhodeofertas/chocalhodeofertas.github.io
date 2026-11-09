"""Conversa com a API do Mercado Livre."""
import json
import os
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests

API = "https://api.mercadolibre.com"
_ATRIBUTOS = (
    "id,title,price,original_price,status,available_quantity,"
    "thumbnail,secure_thumbnail,permalink"
)


class AcessoNegado(Exception):
    """O Mercado Livre recusou o pedido (normalmente falta de token)."""


class ErroML(Exception):
    pass


@dataclass
class InfoProduto:
    id: str
    titulo: str
    preco: Optional[float]
    preco_original: Optional[float]
    imagem: Optional[str]
    disponivel: bool
    item_id: Optional[str] = None  # anúncio vencedor (para o Linkbuilder)


def extrair_id(link: str):
    """Descobre o código do produto a partir do link (ou do próprio código).

    Retorna (tipo, id): tipo "item" para anúncios (MLB-123...) e
    "catalogo" para páginas de produto de catálogo (/p/MLB123...).
    """
    link = (link or "").strip()
    url = urlparse(link)
    # Anúncio específico escolhido dentro de uma página de catálogo
    wid = parse_qs(url.query).get("wid")
    if wid and re.fullmatch(r"MLB\d+", wid[0], re.I):
        return "item", wid[0].upper()
    m = re.search(r"/p/(MLB\d+)", url.path, re.I)
    if m:
        return "catalogo", m.group(1).upper()
    m = re.search(r"\b(MLB)-?(\d{6,})", link, re.I)
    if m:
        return "item", "MLB" + m.group(2)
    raise ValueError(f"não achei o código MLB no link: {link}")


def _resumo(texto):
    """Tira HTML e espaços da resposta de erro, para o log ficar legível."""
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return " ".join(texto.split())[:150]


def _imagem_grande(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = url.replace("http://", "https://")
    # Miniaturas do ML terminam em -I.jpg; -O.jpg é a versão maior
    return re.sub(r"-I\.(jpg|webp|png)$", r"-O.\1", url)


class MercadoLivre:
    def __init__(self, access_token: Optional[str] = None, session=None):
        self.token = access_token
        self.s = session or requests.Session()

    def _get(self, caminho, params=None):
        headers = {"Accept": "application/json", "User-Agent": "chocalho-de-ofertas/1.0"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            r = self.s.get(API + caminho, params=params, headers=headers, timeout=25)
        except requests.RequestException as e:
            raise ErroML(f"falha de conexão com o Mercado Livre ({type(e).__name__})")
        if r.status_code in (401, 403):
            raise AcessoNegado(f"HTTP {r.status_code} em {caminho}: {_resumo(r.text)}")
        if r.status_code >= 400:
            raise ErroML(f"HTTP {r.status_code} em {caminho}: {_resumo(r.text)}")
        return r.json()

    def itens(self, ids):
        """Busca vários anúncios de uma vez (até 20 por pedido)."""
        resultado = {}
        ids = list(dict.fromkeys(ids))
        for i in range(0, len(ids), 20):
            lote = ids[i : i + 20]
            dados = self._get("/items", {"ids": ",".join(lote), "attributes": _ATRIBUTOS})
            for entrada in dados:
                corpo = entrada.get("body") or {}
                codigo = entrada.get("code")
                if codigo in (401, 403):
                    raise AcessoNegado(f"HTTP {codigo} em /items: {json.dumps(corpo)[:200]}")
                if codigo != 200 or "id" not in corpo:
                    continue
                qtd = corpo.get("available_quantity")
                resultado[corpo["id"]] = InfoProduto(
                    id=corpo["id"],
                    titulo=corpo.get("title") or "",
                    preco=corpo.get("price"),
                    preco_original=corpo.get("original_price"),
                    imagem=_imagem_grande(corpo.get("secure_thumbnail") or corpo.get("thumbnail")),
                    disponivel=corpo.get("status") == "active" and (qtd is None or qtd > 0),
                    item_id=corpo["id"],
                )
        return resultado

    def catalogo(self, pid, titulo=None, imagem=None):
        """Produto de catálogo: pega o menor preço entre as lojas que vendem.

        Nome e foto só são buscados se não vierem prontos (economiza pedidos).
        """
        if not titulo:
            dados = self._get(f"/products/{pid}")
            titulo = dados.get("name") or ""
            fotos = dados.get("pictures") or []
            imagem = _imagem_grande(fotos[0].get("url")) if fotos else None
        try:
            ofertas = self._get(f"/products/{pid}/items", {"limit": 5}).get("results") or []
        except ErroML:
            ofertas = []  # 404 = nenhuma loja vendendo agora
        ofertas = [o for o in ofertas if o.get("price")]
        melhor = min(ofertas, key=lambda o: o["price"]) if ofertas else {}
        return InfoProduto(
            id=pid,
            titulo=titulo,
            preco=melhor.get("price"),
            preco_original=melhor.get("original_price"),
            imagem=imagem,
            disponivel=bool(melhor),
            item_id=melhor.get("item_id"),
        )

    def mais_vendidos(self, categoria):
        """Lista (tipo, id) dos mais vendidos de uma categoria, em ordem."""
        dados = self._get(f"/highlights/MLB/category/{categoria}")
        tipos = {"PRODUCT": "catalogo", "ITEM": "item"}
        return [
            (tipos[c["type"]], c["id"])
            for c in sorted(dados.get("content") or [], key=lambda c: c.get("position", 999))
            if c.get("type") in tipos
        ]

    def buscar_produtos(self, termo, limite=10):
        """Busca no catálogo do ML (a busca de anúncios é bloqueada para o token do app)."""
        dados = self._get("/products/search", {"status": "active", "site_id": "MLB", "q": termo, "limit": limite})
        return [(r["id"], r.get("name") or "") for r in dados.get("results") or [] if r.get("id")]

    def categoria_da_busca(self, termo):
        """Categoria do ML que mais combina com o termo (ex.: 'cadeirinha' → Cadeiras de Bebê para Carro)."""
        dados = self._get("/sites/MLB/domain_discovery/search", {"q": termo, "limit": 1})
        return (dados[0].get("category_id"), dados[0].get("category_name")) if dados else (None, None)

    def categorias_raiz(self):
        dados = self._get("/sites/MLB/categories")
        return [(c["id"], c["name"]) for c in dados or []]

    def subcategorias(self, categoria):
        dados = self._get(f"/categories/{categoria}")
        return [(c["id"], c["name"]) for c in dados.get("children_categories") or []]


def link_produto(tipo, pid):
    """Endereço público do produto no Mercado Livre."""
    if tipo == "catalogo":
        return f"https://www.mercadolivre.com.br/p/{pid}"
    return f"https://produto.mercadolivre.com.br/MLB-{pid[3:]}"


# ---------- Autenticação (token) ----------

def _pedir_token(dados):
    try:
        r = requests.post(
            API + "/oauth/token",
            data=dados,
            headers={"Accept": "application/json"},
            timeout=25,
        )
    except requests.RequestException as e:
        raise ErroML(f"falha de conexão ao pedir token ({type(e).__name__})")
    j = r.json() if r.content else {}
    if r.status_code >= 400 or "access_token" not in j:
        raise AcessoNegado(f"token recusado: {j.get('message') or j.get('error') or r.status_code}")
    _mascarar(j["access_token"])
    if j.get("refresh_token"):
        _mascarar(j["refresh_token"])
    return j


def token_do_app(client_id, client_secret):
    """Token só do aplicativo (Client Credentials), sem autorização do usuário."""
    j = _pedir_token(
        {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    )
    return j["access_token"]


def renovar_token(client_id, client_secret, refresh_token):
    """Gera um token novo. O ML troca o refresh_token a cada uso."""
    j = _pedir_token(
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }
    )
    return j["access_token"], j.get("refresh_token") or refresh_token


def trocar_codigo(client_id, client_secret, codigo, redirect_uri):
    """Primeira autorização: troca o código da URL por um refresh_token."""
    j = _pedir_token(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": codigo,
            "redirect_uri": redirect_uri,
        }
    )
    return j["access_token"], j["refresh_token"]


def _mascarar(valor):
    """No GitHub Actions, esconde o valor caso apareça em algum log."""
    if os.environ.get("GITHUB_ACTIONS") == "true" and valor:
        print(f"::add-mask::{valor}")
