"""Página pública do Chocalho (GitHub Pages): ofertas do momento + link do canal.

O bot reescreve docs/index.html no máximo uma vez por hora, e só quando muda.
"""
import hashlib
import html
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from .estado import preco_tipico
from .mensagens import brl
# Pixel da Meta (dataset "Chocalho site"). O ID é público: aparece no código de qualquer site com Pixel.
PIXEL_META = "1161972522974367"
PIXEL_HTML = ("<script>!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?"
              "n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;"
              "n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];"
              "s.parentNode.insertBefore(t,s)}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');"
              f"fbq('init','{PIXEL_META}');fbq('track','PageView');</script>"
              f'<noscript><img height="1" width="1" style="display:none" alt="" '
              f'src="https://www.facebook.com/tr?id={PIXEL_META}&amp;ev=PageView&amp;noscript=1"></noscript>')
PAGINA = (Path(__file__).resolve().parent / "vitrine_pagina.html").read_text(encoding="utf-8")

ARQ = Path(__file__).resolve().parent.parent / "docs" / "index.html"
MAX_ITENS = 60

NOMES = {
    "fralda": "Fraldas", "higiene": "Higiene", "roupa": "Roupas", "brinquedo": "Brinquedos",
    "jogo": "Jogos", "quarto": "Quarto", "passeio": "Passeio", "alimentacao": "Alimentação",
    "gestante": "Gestante", "game": "Games", "livro": "Livros", "escola": "Escola", "esporte": "Esporte",
    "casa": "Casa e quarto", "festa": "Festa", "outros": "Outros",
}


def guardar(estado, ofertas, agora):
    """Guarda as ofertas atuais do Mercado Livre (só as que têm link oficial) para a página."""
    if not ofertas:
        return
    estado["vitrine"] = {
        "em": agora.isoformat(timespec="minutes"),
        "itens": [
            {"id": o.id, "titulo": o.titulo[:110], "preco": o.preco, "de": o.preco_de,
             "desconto": round(o.desconto, 3), "link": o.link, "imagem": o.imagem, "categoria": o.categoria,
             "loja": "ml"}
            for o in ofertas[:MAX_ITENS]
        ],
    }


MAX_SHOPEE = 30


def guardar_shopee(estado, oferta, link, agora):
    """Guarda uma oferta da Shopee recém-postada (link com etiqueta "site") para a página.
    Mantém só as das últimas 36 horas, até MAX_SHOPEE."""
    if not link:
        return
    lista = [i for i in estado.get("vitrine_shopee", []) if i.get("id") != oferta.id]
    lista.insert(0, {"id": oferta.id, "titulo": oferta.titulo[:110], "preco": oferta.preco, "de": oferta.preco_de,
                     "a_partir": bool(getattr(oferta, "a_partir", False)), "link": link, "imagem": oferta.imagem,
                     "categoria": oferta.categoria or "outros", "loja": "shopee",
                     "em": agora.isoformat(timespec="minutes")})
    corte = (agora - timedelta(hours=36)).isoformat(timespec="minutes")
    estado["vitrine_shopee"] = [i for i in lista if i.get("em", "") >= corte][:MAX_SHOPEE]


def link_canal(canal):
    canal = (canal or "").strip()
    if canal.startswith("@"):
        return "https://t.me/" + canal[1:]
    if canal.startswith("https://t.me/"):
        return canal
    return ""


def selo(estado, item, agora):
    """Selo de preço pelo histórico do próprio bot (nunca pelo "de" do anúncio).
    ("baixou", preço normal) quando está 10% ou mais abaixo do preço normal com 7+ dias de histórico;
    ("menor30", None) quando é o menor preço visto em 30 dias e o preço já esteve mais alto."""
    tipico, dias = preco_tipico(estado, item["id"], agora)
    if not tipico or dias < 7:
        return None, None
    preco = item["preco"]
    if preco <= tipico * 0.9:
        return "baixou", tipico
    hist = (estado.get("precos", {}).get(item["id"]) or {}).get("historico") or []
    corte = (agora.date() - timedelta(days=30)).isoformat()
    janela = [p for d, p in hist if d >= corte] or [p for _, p in hist[-1:]]
    if janela and preco <= min(janela) + 0.009 and max(p for _, p in hist) > preco * 1.02:
        return "menor30", None
    return None, None


def _itens(estado, agora):
    ml = (estado.get("vitrine") or {}).get("itens") or []
    shp = estado.get("vitrine_shopee") or []
    itens = []
    for i in [dict(x, loja=x.get("loja", "ml")) for x in ml] + [dict(x) for x in shp]:
        tipo, tipico = selo(estado, i, agora)
        i["selo"], i["tipico"] = tipo, tipico
        itens.append(i)
    # intercala as duas lojas para a vitrine não ficar em blocos
    ml_i = [i for i in itens if i["loja"] == "ml"]
    sh_i = [i for i in itens if i["loja"] == "shopee"]
    mix = []
    while ml_i or sh_i:
        if ml_i:
            mix.append(ml_i.pop(0))
        if ml_i:
            mix.append(ml_i.pop(0))
        if sh_i:
            mix.append(sh_i.pop(0))
    return mix


LOJA = {"ml": "Mercado Livre", "shopee": "Shopee"}
SELO_TXT = {"baixou": "Baixou de verdade", "menor30": "Menor preço em 30 dias"}


def _foto(i, eager=False):
    e = html.escape
    nome = NOMES.get(i.get("categoria"), "Oferta")
    if not i.get("imagem"):
        return f'<span class="sem-foto">{e(nome)}</span>'
    carregar = "eager" if eager else "lazy"
    return (f'<img src="{e(i["imagem"], quote=True)}" alt="" loading="{carregar}" decoding="async" '
            f'onerror="this.replaceWith(Object.assign(document.createElement(\'span\'),'
            f'{{className:\'sem-foto\',textContent:\'{e(nome)}\'}}))">')


def _preco(i, com_de=True):
    e = html.escape
    rotulo = '<span class="apartir">a partir de</span>' if i.get("a_partir") else ""
    de = f'<s>{brl(i["de"])}</s>' if com_de and i.get("de") else ""
    return f'<span class="preco">{de}{rotulo}<b>{e(brl(i["preco"]))}</b></span>'


def _card(i):
    e = html.escape
    marca = (f'<span class="selo s-{i["selo"]}">{SELO_TXT[i["selo"]]}</span>' if i.get("selo") else "")
    return (
        f'<a class="card" data-cat="{e(i["categoria"])}" href="{e(i["link"], quote=True)}" '
        f'target="_blank" rel="noopener sponsored">'
        f'<span class="foto">{_foto(i)}</span>'
        f'<span class="info"><span class="loja">{LOJA[i["loja"]]}</span>{marca}'
        f'<span class="titulo">{e(i["titulo"])}</span>{_preco(i)}</span></a>'
    )


def _feed(i, n):
    e = html.escape
    marca = (f'<span class="f-selo">{SELO_TXT[i["selo"]]}</span>' if i.get("selo") else
             f'<span class="f-loja">{LOJA[i["loja"]]}</span>')
    return (f'<li class="msg"><span class="f-foto">{_foto(i, eager=n < 4)}</span>'
            f'<span class="f-txt">{marca}<span class="f-tit">{e(i["titulo"])}</span>'
            f'<b class="f-preco">{e(brl(i["preco"]))}</b></span></li>')


def _destaque(i):
    e = html.escape
    normal = (f'<span class="normal">Preço normal pelo histórico: {brl(i["tipico"])}</span>'
              if i.get("selo") == "baixou" and i.get("tipico") else
              '<span class="normal">O menor preço que o Chocalho viu em 30 dias</span>')
    return (f'<a class="dest" href="{e(i["link"], quote=True)}" target="_blank" rel="noopener sponsored">'
            f'<span class="foto">{_foto(i)}</span><span class="d-info">'
            f'<span class="selo s-{i["selo"]}">{SELO_TXT[i["selo"]]}</span>'
            f'<span class="titulo">{e(i["titulo"])}</span>{_preco(i, com_de=False)}{normal}'
            f'<span class="loja">{LOJA[i["loja"]]}</span></span></a>')


def _num(n):
    return f"{n:,}".replace(",", ".")


ICONE_WA = ('<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2a10 10 0 0 0-8.6 '
            '15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm0 18.2c-1.5 0-3-.4-4.3-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2Zm4.5-6.1'
            'c-.2-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1l-.8 1c-.1.2-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.2-.4.2-.4.7-1.3.1-.2 0-.3 0-.4'
            'l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.2 5.2 0 0 0 1.1 2.7 11.8 11.8 0 0 0 4.5 4c1.7.7 '
            '2.3.8 3.2.6.5-.1 1.5-.6 1.7-1.2.2-.6.2-1.1.2-1.2-.1-.2-.3-.2-.5-.3Z"/></svg>')


def gerar_html(estado, canal, grupo_wa=None, agora=None):
    v = estado.get("vitrine") or {}
    em = v.get("em", "")
    if agora is None:
        agora = datetime.fromisoformat(em) if em else datetime.now()
    itens = _itens(estado, agora)
    cats = sorted({i["categoria"] for i in itens}, key=lambda c: NOMES.get(c, c))
    chips = '<button class="chip ativo" data-f="" aria-pressed="true">Tudo</button>' + "".join(
        f'<button class="chip" data-f="{c}" aria-pressed="false">{NOMES.get(c, c.title())}</button>' for c in cats)
    url_canal = link_canal(canal)
    m_wa = re.search(r"chat\.whatsapp\.com/([A-Za-z0-9]+)", grupo_wa or "")
    wa_codigo = m_wa.group(1) if m_wa else ""
    wa_href = html.escape(f"https://chat.whatsapp.com/{wa_codigo}" if wa_codigo else (grupo_wa or ""), quote=True)
    hora = f"{em[11:16]}" if len(em) >= 16 else ""
    dia = f"{em[8:10]}/{em[5:7]}" if len(em) >= 10 else ""
    acompanhados = len(estado.get("precos") or {})
    hoje = (estado.get("hist_dia") or {}).get(agora.date().isoformat(), {}).get("posts", 0)
    destaques = sorted([i for i in itens if i.get("selo")],
                       key=lambda i: (i["selo"] != "baixou", -(1 - i["preco"] / i["tipico"]) if i.get("tipico") else 0))[:8]
    feed_itens = [i for i in itens if i.get("imagem")][:12]
    feed = "".join(_feed(i, n) for n, i in enumerate(feed_itens))
    cards = "".join(_card(i) for i in itens) or '<p class="vazio">As próximas ofertas aparecem aqui em breve.</p>'
    botao = (f'<a class="cta" data-wa="{wa_codigo}" href="{wa_href}" target="_blank" rel="noopener">{ICONE_WA}<span>Entrar no grupo do WhatsApp</span></a>'
             if wa_href else "")
    telegram = (f'<a class="tg" href="{html.escape(url_canal, quote=True)}" target="_blank" rel="noopener">'
                f'Prefere Telegram? Entre no canal</a>' if url_canal else "")
    stats = []
    if acompanhados:
        stats.append(f"<li><b>{_num(acompanhados)}</b> produtos com preço acompanhado</li>")
    if hoje:
        stats.append(f"<li><b>{_num(hoje)}</b> ofertas enviadas hoje</li>")
    sec_dest = ""
    if destaques:
        sec_dest = (
            '<section class="destaques" aria-labelledby="t-dest"><div class="miolo">'
            '<h2 id="t-dest">Destaques do histórico de preços</h2>'
            '<p class="lead">Preço que baixou de verdade, ou o menor dos últimos 30 dias, pelo histórico que o Chocalho guarda '
            'de cada produto. Não pelo desconto que o anúncio diz.</p>'
            f'<div class="trilho">{"".join(_destaque(i) for i in destaques)}</div></div></section>')
    campos = {
        "feed": feed, "cards": cards, "chips": chips, "botao": botao, "telegram": telegram, "sec_dest": sec_dest,
        "stats": "".join(stats), "pixel": PIXEL_HTML, "hora": hora, "dia": dia,
        "acompanhados": _num(acompanhados) if acompanhados else "milhares de",
    }
    pagina = PAGINA
    for k, val in campos.items():
        pagina = pagina.replace("[[" + k + "]]", val)
    return pagina

def gerar_grupo_html(grupo_wa):
    """Página-ponte: abre o app do WhatsApp direto (inclusive de dentro do Instagram/Facebook)."""
    m = re.search(r"chat\.whatsapp\.com/([A-Za-z0-9]+)", grupo_wa or "")
    codigo = m.group(1) if m else ""
    web = f"https://chat.whatsapp.com/{codigo}" if codigo else (grupo_wa or "")
    e = html.escape
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chocalho de Ofertas</title>
<meta name="description" content="Entre no grupo de ofertas de produtos para bebês e crianças.">\n<meta name="theme-color" content="#1E0524">
<link rel="icon" type="image/png" href="icone-96.png">\n<link rel="preload" href="fonts/schibsted.woff2" as="font" type="font/woff2" crossorigin>
<style>
@font-face {{ font-family:"Schibsted Grotesk"; src:url(fonts/schibsted.woff2) format("woff2"); font-weight:400 900; font-display:swap; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center; text-align:center;
  background:#1E0524; color:#fff; font:400 17px/1.5 "Schibsted Grotesk", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; padding:24px 20px; }}
.logo {{ width:72px; height:72px; border-radius:18px; background:#F1E1FB; margin:0 auto 14px; display:block; }}
h1 {{ font-size:26px; font-weight:800; letter-spacing:-.03em; margin:0 0 6px; }}
p {{ color:#E4CDF5; margin:0 0 24px; }}
a.botao {{ display:block; max-width:360px; margin:0 auto 14px; padding:17px 22px; border-radius:14px;
  background:#DC1173; color:#fff; font-weight:700; font-size:18px; text-decoration:none; box-shadow:0 2px 0 rgba(0,0,0,.18), 0 12px 24px -12px rgba(0,0,0,.55); }}
a.botao:focus-visible {{ outline:3px solid #F1E1FB; outline-offset:3px; }}
small {{ color:#D9C3E6; display:block; max-width:340px; margin:0 auto; font-size:13.5px; }}
</style>
{PIXEL_HTML}
</head>
<body>
<main>
  <img class="logo" src="icone-192.png" alt="">
  <h1>Chocalho de Ofertas</h1>
  <p>Abrindo o grupo no WhatsApp…</p>
  <a class="botao" id="entrar" href="{e(web, quote=True)}">Entrar no grupo do WhatsApp</a>
  <small>Se o WhatsApp não abrir sozinho, toque no botão. #publi · os links do grupo são de afiliado.</small>
</main>
<script>
(function () {{
  var codigo = {json.dumps(codigo)}, web = {json.dumps(web)}, ua = navigator.userAgent || "";
  function abrir() {{
    if (window.fbq) {{ try {{ fbq('track', 'Lead'); }} catch (e) {{}} }}
    if (!codigo) {{ location.href = web; return; }}
    if (/android/i.test(ua)) {{
      location.href = "intent://chat/?code=" + codigo + "#Intent;scheme=whatsapp;package=com.whatsapp;" +
        "S.browser_fallback_url=" + encodeURIComponent(web) + ";end";
    }} else if (/iphone|ipad|ipod/i.test(ua)) {{
      location.href = "whatsapp://chat?code=" + codigo;
      setTimeout(function () {{ location.href = web; }}, 1600);
    }} else {{
      location.href = web;
    }}
  }}
  document.getElementById("entrar").addEventListener("click", function (ev) {{ ev.preventDefault(); abrir(); }});
  setTimeout(abrir, 900);
}})();
</script>
</body>
</html>
"""


def talvez_publicar(estado, canal, agora, arquivo=ARQ, log=print, grupo_wa=None):
    """Reescreve a página se mudou e se já passou 1 hora desde a última vez."""
    ultima = estado.get("vitrine_publicada_em")
    if ultima and ultima[:13] == agora.isoformat()[:13]:
        return False
    conteudo = gerar_html(estado, canal, grupo_wa, agora)
    assinatura = hashlib.sha1(json.dumps([(estado.get("vitrine") or {}).get("itens"), estado.get("vitrine_shopee"), canal, grupo_wa],
                                         sort_keys=True)
                              .encode()).hexdigest()
    if assinatura == estado.get("vitrine_assinatura") and Path(arquivo).exists():
        return False
    Path(arquivo).parent.mkdir(parents=True, exist_ok=True)
    Path(arquivo).write_text(conteudo, encoding="utf-8")
    if grupo_wa:
        (Path(arquivo).parent / "grupo.html").write_text(gerar_grupo_html(grupo_wa), encoding="utf-8")
    estado["vitrine_assinatura"] = assinatura
    estado["vitrine_publicada_em"] = agora.isoformat(timespec="minutes")
    log("Página de ofertas atualizada.")
    return True
