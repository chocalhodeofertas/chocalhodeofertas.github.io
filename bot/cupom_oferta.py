"""Cupom que pode valer para uma oferta: escolhe, entre os cupons ativos no
canal, o que mais economiza para aquele produto e calcula o preço com ele.

O Mercado Livre não informa pela API se um produto é elegível a um cupom,
então o post sempre avisa "se o produto for elegível" (cláusula 5.4: não
afirmamos o que o anúncio não diz). Regras usadas:
- só cupom de categoria compatível com o produto (ex.: "Bebês", "Moda") ou
  marcado como válido para o site todo. Cupom "geral" sem categoria NÃO
  entra: quase sempre vale só para produtos selecionados;
- preço do produto >= compra mínima do cupom;
- desconto limitado ao "desconto máx." do cupom;
- cupons exclusivos Meli+ ficam de fora (nem todo mundo é assinante);
- só mostra quando economiza pelo menos R$ 2.
"""
import html
import json
import re
from datetime import datetime

# Palavras da categoria do CUPOM que combinam com a categoria do PRODUTO
COMPATIVEIS = {
    "fralda": ("beb", "fralda", "higiene", "infantil"),
    "higiene": ("beb", "higiene", "infantil", "saude", "beleza"),
    "quarto": ("beb", "movei", "casa", "infantil", "decora"),
    "passeio": ("beb", "infantil"),
    "alimentacao": ("beb", "infantil", "casa"),
    "gestante": ("beb", "saude"),
    "roupa": ("moda", "roupa", "infantil", "calcad"),
    "brinquedo": ("brinquedo", "infantil"),
    "jogo": ("brinquedo", "jogo", "infantil"),
    "game": ("game", "jogo", "tecnolog", "brinquedo"),
    "livro": ("livro", "papelaria"),
    "escola": ("escola", "escolar", "papelaria", "infantil"),
    "esporte": ("esporte",),
    "casa": ("casa", "movei", "decora"),
    "festa": ("festa", "casa", "decora"),
}
ECONOMIA_MIN = 2.0


def _valor(t):
    """'R$1.599' -> 1599.0 ; 'R$79,90' -> 79.9"""
    m = re.search(r"R\$\s*([\d.,]+)", t or "")
    if not m:
        return None
    n = m.group(1).rstrip(".,")
    if "," in n:
        n = n.replace(".", "").replace(",", ".")
    else:
        n = n.replace(".", "")
    try:
        return float(n)
    except ValueError:
        return None


def info_do_bloco(bloco_html):
    """Lê desconto, categoria, mínimo e máximo do bloco já postado no canal."""
    t = html.unescape(re.sub(r"<[^>]+>", "", bloco_html or ""))
    info = {"pct": None, "fixo": None, "categoria": None, "minimo": None, "maximo": None, "meli_mais": False}
    m = re.search(r"👉\s*(.+?OFF)", t)
    if m:
        d = m.group(1)
        pct = re.search(r"(\d+(?:[.,]\d+)?)\s*%", d)
        if pct:
            info["pct"] = float(pct.group(1).replace(",", ".")) / 100
        else:
            info["fixo"] = _valor(d)
    cat = re.search(r"📂\s*(.+)", t)
    if cat:
        info["categoria"] = cat.group(1).strip()
    mn = re.search(r"Compra m[ií]n\.?:?\s*(R\$\s*[\d.,]+)", t)
    mx = re.search(r"Desconto m[aá]x\.?:?\s*(R\$\s*[\d.,]+)", t)
    info["minimo"] = _valor(mn.group(1)) if mn else None
    info["maximo"] = _valor(mx.group(1)) if mx else None
    info["meli_mais"] = bool(re.search(r"meli\s*\+", t, re.I))
    codigo = re.search(r"🎟️\s*(\S+)", t)
    info["site_todo"] = bool(re.search(r"site todo|todo o site|todo site", t, re.I)) or bool(
        codigo and re.search(r"SITETODO|TODOSITE|TODO\d*SITE", codigo.group(1)))
    return info


def _compativel(cat_cupom, cat_produto):
    if not cat_cupom:
        return False  # sem categoria: costuma valer só para produtos selecionados
    from .filtros import normalizar

    alvo = normalizar(cat_cupom)
    return any(p in alvo for p in COMPATIVEIS.get(cat_produto, ()))


def economia(preco, info):
    if info["minimo"] and preco < info["minimo"]:
        return 0.0
    if info["pct"]:
        e = preco * info["pct"]
    elif info["fixo"]:
        e = info["fixo"]
    else:
        return 0.0
    if info["maximo"]:
        e = min(e, info["maximo"])
    return round(min(e, preco), 2)


def melhor_cupom(estado, oferta, agora):
    """{'codigo', 'preco', 'economia', 'desconto'} do cupom que mais economiza, ou None."""
    melhor = None
    posts = estado.get("posts_cupom") or {}
    for codigo, c in (estado.get("cupons") or {}).items():
        if c.get("status") != "ativo" or codigo.startswith("#"):
            continue
        if c.get("validade") and datetime.fromisoformat(c["validade"]) < agora:
            continue
        post = posts.get(str(c.get("post"))) or {}
        bloco = next((b["html"] for b in post.get("blocos", []) if b.get("codigo") == codigo), None)
        if not bloco:
            continue
        info = info_do_bloco(bloco)
        if info["meli_mais"] or not (info["site_todo"] or _compativel(info["categoria"], oferta.categoria)):
            continue
        e = economia(oferta.preco, info)
        if e >= ECONOMIA_MIN and (melhor is None or e > melhor["economia"]):
            desc = re.search(r"👉\s*<b>([^<]*)</b>", bloco)
            melhor = {"codigo": codigo, "economia": e, "preco": round(oferta.preco - e, 2),
                      "desconto": html.unescape(desc.group(1)).strip() if desc else ""}
    return melhor


# ---------- cupom mostrado pelo próprio Mercado Livre no anúncio ----------
# O link meli.la abre a página social do afiliado. O 1º bloco "polycards" é o
# produto compartilhado e, quando ele tem cupom, o card traz o selo "com Cupom":
#  - promotions [{type: coupon, text: "{1} com Cupom", values: [preço]}] → preço com cupom
#  - promotions [{type: coupon, text: "8% OFF com Cupom"}]              → só o percentual
#  - price.discount_label "44% OFF com Cupom" → o preço do card já é com cupom
# É o ML dizendo que AQUELE produto tem cupom, então não precisa de "se elegível".

def _cards_do_produto(texto):
    i = (texto or "").find('"polycards":')
    if i < 0:
        return []
    try:
        cards, _ = json.JSONDecoder().raw_decode(texto[i + len('"polycards":'):])
    except ValueError:
        return []
    return cards if isinstance(cards, list) else []


def ler_cupom_pagina(texto, oferta_id, preco):
    """{'origem': 'pagina', 'preco', 'economia', 'desconto'} ou None."""
    cards = _cards_do_produto(texto)
    if not cards:
        return None
    card = cards[0]
    md = card.get("metadata") or {}
    if oferta_id and oferta_id not in (md.get("id"), md.get("product_id")):
        return None  # o card não é o produto do link: melhor não arriscar
    comps = {c.get("type"): c.get(c.get("type")) for c in card.get("components") or []}
    price = comps.get("price") or {}
    atual = (price.get("current_price") or {}).get("value")
    rotulo = ((price.get("discount_label") or {}).get("text") or "")
    for p in comps.get("promotions") or []:
        if p.get("type") != "coupon":
            continue
        valores = [v["price"]["value"] for v in p.get("values") or [] if v.get("type") == "price"]
        if valores:
            novo = float(valores[0])
            if preco - novo >= ECONOMIA_MIN:
                return {"origem": "pagina", "preco": round(novo, 2), "economia": round(preco - novo, 2),
                        "desconto": ""}
        pct = re.search(r"(\d+(?:[.,]\d+)?)\s*%\s*OFF", p.get("text") or "", re.I)
        if pct:
            return {"origem": "pagina", "preco": None, "economia": 0.0,
                    "desconto": f"{pct.group(1).replace('.', ',')}% OFF"}
    if "cupom" in rotulo.lower() and atual and preco - float(atual) >= ECONOMIA_MIN:
        return {"origem": "pagina", "preco": round(float(atual), 2),
                "economia": round(preco - float(atual), 2), "desconto": ""}
    return None


def cupom_da_pagina(oferta, session=None, log=print):
    """Abre o meli.la da oferta e lê o cupom do anúncio. Qualquer falha → None."""
    link = getattr(oferta, "link", "") or ""
    if "meli.la/" not in link:
        return None
    import requests

    from .comandos import UA

    try:
        r = (session or requests).get(link, headers=UA, timeout=25)
        return ler_cupom_pagina(r.text, getattr(oferta, "id", None), oferta.preco)
    except Exception as e:  # noqa: BLE001 - sem cupom não impede o post
        log(f"Aviso: não consegui ler o cupom da página de {getattr(oferta, 'id', '?')}: {e}")
        return None


def escolher_cupom(estado, oferta, agora, session=None, log=print):
    """Cupom do próprio anúncio (certo) ou o melhor cupom do canal (se elegível).
    Fica com o que deixa o produto mais barato; empate ou sem preço fica com o do anúncio."""
    do_anuncio = cupom_da_pagina(oferta, session, log)
    do_canal = melhor_cupom(estado, oferta, agora)
    if do_anuncio and do_canal and do_canal["economia"] > do_anuncio["economia"] and do_anuncio["preco"]:
        return do_canal
    return do_anuncio or do_canal
