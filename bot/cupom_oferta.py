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
- cupom que o admin marcou com "geral CÓDIGO" (testou e vale para quase
  tudo) entra mesmo sem categoria; mínimo e teto continuam valendo;
- cupons exclusivos Meli+ ficam de fora (nem todo mundo é assinante);
- só mostra quando economiza pelo menos R$ 2.
"""
import html
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
        amplo = info["site_todo"] or c.get("geral")
        if info["meli_mais"] or not (amplo or _compativel(info["categoria"], oferta.categoria)):
            continue
        e = economia(oferta.preco, info)
        if e >= ECONOMIA_MIN and (melhor is None or e > melhor["economia"]):
            desc = re.search(r"👉\s*<b>([^<]*)</b>", bloco)
            melhor = {"codigo": codigo, "economia": e, "preco": round(oferta.preco - e, 2),
                      "desconto": html.unescape(desc.group(1)).strip() if desc else ""}
    return melhor
