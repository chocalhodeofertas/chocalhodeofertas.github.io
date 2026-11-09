"""Artes na identidade do Chocalho de Ofertas.

- gerar(oferta)            → post de produto 4:5 (feed, WhatsApp, Telegram)
- story(oferta)            → story 9:16 com espaço para o adesivo de link
- capa(foto, titulo, ...)  → capa de carrossel com foto e título (sem cara de anúncio)
- final()                  → último slide, chamando para o grupo
- carrossel(...) / reel(...)

Só usa informações do anúncio (nome, preço, desconto), como pede a
cláusula 5.4 dos termos de afiliado.
"""
import io
import math
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .mensagens import brl

RAIZ = Path(__file__).resolve().parent.parent
FONTES = RAIZ / "assets" / "fonts"
ICONE_ARQ = RAIZ / "assets" / "marca" / "icone.png"
CAPAS = RAIZ / "assets" / "capas"

# Paleta tirada do logo
LAVANDA = (241, 225, 251)
LAVANDA_2 = (228, 205, 245)
UVA = (58, 10, 64)
ROXO = (142, 43, 176)
PINK = (234, 19, 122)
BRANCO = (255, 255, 255)
SUAVE = (120, 90, 128)
CREME_TXT = (255, 248, 225)

RODAPE = "promoção temporária  ·  #publi"
ARROBA = "@chocalhodeofertas"

_cache = {}


def _fredoka(tam, peso=700):
    f = ImageFont.truetype(str(FONTES / "Fredoka.ttf"), tam)
    try:
        f.set_variation_by_axes([peso, 100])
    except Exception:  # noqa: BLE001
        pass
    return f


def _poppins(tam, peso="Medium"):
    return ImageFont.truetype(str(FONTES / f"Poppins-{peso}.ttf"), tam)


def _icone(alt):
    if "icone" not in _cache:
        im = Image.open(ICONE_ARQ).convert("RGBA")
        _cache["icone"] = im.crop(im.getbbox())
    i = _cache["icone"].copy()
    i.thumbnail((alt * 2, alt), Image.LANCZOS)
    return i


def _quebrar(d, texto, fonte, largura, max_linhas):
    # "R$ 50" nunca quebra no meio
    palavras, linhas, atual = [w for w in texto.replace("R$ ", "R$\u00a0").split(" ") if w], [], ""
    for p in palavras:
        t = f"{atual} {p}".strip()
        if d.textlength(t, font=fonte) <= largura:
            atual = t
        else:
            if atual:
                linhas.append(atual)
            atual = p
            if len(linhas) == max_linhas:
                break
    if len(linhas) < max_linhas and atual:
        linhas.append(atual)
    if linhas and sum(len(l.split(" ")) for l in linhas) < len(palavras):
        u = linhas[-1]
        while d.textlength(u + "…", font=fonte) > largura and " " in u:
            u = u.rsplit(" ", 1)[0]
        linhas[-1] = u + "…"
    return linhas


def baixar_foto(url, session=None):
    if not url:
        return None
    try:
        r = (session or requests).get(url, timeout=20)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:  # noqa: BLE001
        return None


def _png(img):
    saida = io.BytesIO()
    img.convert("RGB").save(saida, "PNG", optimize=True)
    return saida.getvalue()


# ---------- peças comuns ----------

def _fundo(l, a):
    img = Image.new("RGB", (l, a), LAVANDA)
    d = ImageDraw.Draw(img)
    r = random.Random(7)
    for _ in range(10):  # tracinhos só nas bordas, como no logo
        if r.random() < .5:
            x, y = r.choice([r.randint(10, 50), r.randint(l - 60, l - 20)]), r.randint(0, a)
        else:
            x, y = r.randint(0, l), r.choice([r.randint(5, 30), r.randint(a - 40, a - 10)])
        ang = r.uniform(0, math.pi)
        d.line([(x, y), (x + 34 * math.cos(ang), y + 34 * math.sin(ang))],
               fill=r.choice([LAVANDA_2, LAVANDA_2, (250, 200, 225)]), width=12)
    return img


def _cabecalho(img, y=48, x=60):
    d = ImageDraw.Draw(img)
    ic = _icone(96)
    img.paste(ic, (x, y), ic)
    tx = x + ic.width + 16
    f = _fredoka(50)
    d.text((tx, y + 8), "Chocalho", font=f, fill=UVA)
    d.text((tx + d.textlength("Chocalho ", font=f), y + 8), "de Ofertas", font=f, fill=PINK)
    d.text((tx + 2, y + 64), "para famílias que amam economizar", font=_poppins(22), fill=SUAVE)


def _cartao_foto(img, caixa, foto):
    x0, y0, x1, y1 = caixa
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0, y0 + 8, x1, y1 + 8], radius=40, fill=LAVANDA_2)
    d.rounded_rectangle([x0, y0, x1, y1], radius=40, fill=BRANCO)
    if foto is not None:
        f = foto.copy()
        f.thumbnail((x1 - x0 - 70, y1 - y0 - 70), Image.LANCZOS)
        img.paste(f, (x0 + (x1 - x0 - f.width) // 2, y0 + (y1 - y0 - f.height) // 2),
                  f if f.mode == "RGBA" else None)
    else:
        ic = _icone(260)
        img.paste(ic, ((x0 + x1 - ic.width) // 2, (y0 + y1 - ic.height) // 2), ic)


def _selo(d, x1, y0, oferta, tam=60):
    if not oferta.preco_de or not oferta.desconto:
        return
    pct = f"-{round(oferta.desconto * 100)}%"
    f = _fredoka(tam)
    w = d.textlength(pct, font=f) + 60
    d.rounded_rectangle([x1 - w, y0, x1, y0 + tam + 44], radius=(tam + 44) // 2, fill=PINK)
    d.text((x1 - w / 2, y0 + (tam + 44) / 2), pct, font=f, fill=BRANCO, anchor="mm")


def _preco(d, x, y, oferta, grande=104):
    if oferta.preco_de:
        de = f"de {brl(oferta.preco_de)}"
        f = _poppins(36, "Regular")
        d.text((x, y), de, font=f, fill=SUAVE)
        d.line([(x + d.textlength("de ", font=f), y + 25), (x + d.textlength(de, font=f), y + 25)],
               fill=SUAVE, width=3)
        y += 50
    fp = _poppins(36, "Medium")
    d.text((x, y + 30), "por", font=fp, fill=UVA)
    d.text((x + d.textlength("por ", font=fp), y - 18), brl(oferta.preco), font=_fredoka(grande), fill=UVA)


def _rodape(img, texto, base=None):
    l, a = img.size
    base = base or a
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([60, base - 128, l - 60, base - 48], radius=40, fill=UVA)
    d.text((l // 2, base - 88), texto, font=_poppins(28, "SemiBold"), fill=BRANCO, anchor="mm")


def _pilula(d, xy, texto, fonte, fundo, cor, pad=(28, 10)):
    x, y = xy
    w = d.textlength(texto, font=fonte)
    asc, desc = fonte.getmetrics()
    h = asc + desc + 2 * pad[1]
    d.rounded_rectangle([x, y, x + w + 2 * pad[0], y + h], radius=h // 2, fill=fundo)
    d.text((x + pad[0], y + pad[1]), texto, font=fonte, fill=cor)


# ---------- 1) post de produto (4:5) ----------

def post(oferta, foto=None, cta="Link no grupo", indice=None, session=None):
    """Imagem PIL. cta=None → rodapé só com 'promoção temporária · #publi'."""
    L, A = 1080, 1350
    img = _fundo(L, A)
    d = ImageDraw.Draw(img)
    _cabecalho(img)
    if indice:
        f = _fredoka(36)
        _pilula(d, (L - 60 - d.textlength(indice, font=f) - 56, 70), indice, f, BRANCO, UVA)
    foto = foto if foto is not None else baixar_foto(oferta.imagem, session)
    cx0, cy0, cx1, cy1 = 60, 200, L - 60, 840
    _cartao_foto(img, (cx0, cy0, cx1, cy1), foto)
    _selo(d, cx1 - 28, cy0 + 28, oferta)
    y = 880
    for ln in _quebrar(d, oferta.titulo, _poppins(40, "SemiBold"), L - 140, 2):
        d.text((70, y), ln, font=_poppins(40, "SemiBold"), fill=UVA)
        y += 54
    _preco(d, 70, max(y + 14, 1000), oferta)
    _rodape(img, f"{cta}  ·  {RODAPE}" if cta else RODAPE)
    return img


def gerar(oferta, foto=None, session=None, cta="Link no grupo"):
    """Bytes PNG do post de produto (compatível com o uso antigo)."""
    return _png(post(oferta, foto, cta=cta, session=session))


# ---------- 2) story (9:16) ----------

def story(oferta, foto=None, session=None, area_link=True):
    L, A = 1080, 1920
    img = _fundo(L, A)
    d = ImageDraw.Draw(img)
    _cabecalho(img, y=150)  # margem do topo do Stories
    foto = foto if foto is not None else baixar_foto(oferta.imagem, session)
    cx0, cy0, cx1, cy1 = 60, 330, L - 60, 1150
    _cartao_foto(img, (cx0, cy0, cx1, cy1), foto)
    _selo(d, cx1 - 30, cy0 + 30, oferta, tam=70)
    y = 1200
    for ln in _quebrar(d, oferta.titulo, _poppins(44, "SemiBold"), L - 140, 2):
        d.text((70, y), ln, font=_poppins(44, "SemiBold"), fill=UVA)
        y += 60
    _preco(d, 70, y + 20, oferta, grande=120)
    _rodape(img, RODAPE, base=1640)
    if area_link:  # espaço livre para o adesivo de link
        d.text((L // 2, 1700), "toque no link", font=_poppins(30, "SemiBold"), fill=ROXO, anchor="mm")
        d.polygon([(L // 2 - 18, 1730), (L // 2 + 18, 1730), (L // 2, 1752)], fill=ROXO)
    return img


# ---------- 3) capa com foto ----------

def _cobrir(foto, L, A):
    f = foto.convert("RGB")
    esc = max(L / f.width, A / f.height)
    f = f.resize((int(f.width * esc) + 1, int(f.height * esc) + 1), Image.LANCZOS)
    x, y = (f.width - L) // 2, (f.height - A) // 2
    return f.crop((x, y, x + L, y + A))


def _brilho(d, cx, cy, r, cor=(255, 236, 160)):
    pts = []
    for k in range(8):
        rr = r if k % 2 == 0 else r * 0.28
        pts.append((cx + rr * math.cos(k * math.pi / 4), cy + rr * math.sin(k * math.pi / 4)))
    d.polygon(pts, fill=cor)


def _sombra_texto(img, desenhar, raio=6):
    camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
    desenhar(ImageDraw.Draw(camada))
    camada = camada.filter(ImageFilter.GaussianBlur(raio))
    img.paste(camada, (0, 0), camada)


def _faixa_livre(img, altura, margem_topo=0.08, margem_base=0.12, proibidas=()):
    """Acha a faixa horizontal mais "calma" da foto (menos detalhes) para o texto
    não cobrir o que importa (o rosto, o brinquedo, o carrinho)."""
    L, A = img.size
    esc = 4
    g = img.convert("L").resize((L // esc, A // esc)).filter(ImageFilter.FIND_EDGES)
    px = g.load()
    w, h = g.size
    linhas = [sum(px[x, y] for x in range(w)) for y in range(h)]
    alt = max(1, altura // esc)
    ini, fim = int(h * margem_topo), int(h * (1 - margem_base)) - alt
    if fim <= ini:
        return (A - altura) // 2
    acum = sum(linhas[ini:ini + alt]) - linhas[ini + alt - 1] + linhas[ini - 1]
    melhor, y_melhor = float("inf"), ini
    for y in range(ini, fim + 1):
        acum += linhas[y + alt - 1] - linhas[y - 1]
        # leve preferência pelo centro, para não grudar na borda sem motivo
        peso = acum * (1 + 0.15 * abs((y + alt / 2) / h - 0.5))
        y_px, fim_px = y * esc, (y + alt) * esc
        for p0, p1 in proibidas:  # nunca em cima de um rosto
            sobra = min(fim_px, p1) - max(y_px, p0)
            if sobra > 0:
                peso += 1e9 * sobra
        if peso < melhor:
            melhor, y_melhor = peso, y
    return y_melhor * esc


def _rostos_na_capa(foto, L, A, folga=40):
    """Faixas verticais (y0, y1) ocupadas por rostos depois do recorte da capa."""
    rostos = getattr(foto, "rostos", None) or []
    if not rostos:
        return []
    esc = max(L / foto.width, A / foto.height)
    nw, nh = foto.width * esc, foto.height * esc
    ox, oy = (nw - L) / 2, (nh - A) / 2
    faixas = []
    for x0, y0, x1, y1 in rostos:
        if x1 * nw - ox < 0 or x0 * nw - ox > L:  # rosto fora do recorte
            continue
        faixas.append((y0 * nh - oy - folga, y1 * nh - oy + folga))
    return faixas


def _caber(d, texto, fontes, largura, max_linhas):
    """Usa a maior fonte em que o título cabe inteiro (sem reticências)."""
    for f in fontes:
        linhas = _quebrar(d, texto, f, largura, max_linhas)
        if not linhas[-1].endswith("…"):
            return f, linhas
    return f, linhas


def capa(foto, titulo, destaque=None, estilo="grande", L=1080, A=1350):
    """estilo 'grande': letras grandes claras; 'faixas': tarjas claras com texto escuro."""
    if foto is None:
        img = Image.new("RGB", (L, A), (200, 180, 205))
        proibidas = []
    else:
        img = _cobrir(foto, L, A)
        proibidas = _rostos_na_capa(foto, L, A)
    if estilo == "grande":
        d = ImageDraw.Draw(img)
        f, linhas = _caber(d, titulo.upper(), [_fredoka(t) for t in (112, 96, 84, 74)], L - 140, 4)
        cap = f.getbbox("H", anchor="ls")[3] - f.getbbox("H", anchor="ls")[1]  # altura da maiúscula
        passo = int(cap * 1.42)
        h = len(linhas) * passo + (80 if destaque else 0)
        y0 = _faixa_livre(img, h, proibidas=proibidas)
        mascara = Image.new("L", (L, A), 0)
        ImageDraw.Draw(mascara).rectangle([0, y0 - 60, L, y0 + h + 60], fill=110)
        mascara = mascara.filter(ImageFilter.GaussianBlur(90))
        img = Image.composite(Image.new("RGB", (L, A), (30, 10, 35)), img, mascara)
        d = ImageDraw.Draw(img)

        def sombra(dc):
            y = y0
            for ln in linhas:
                dc.text((L // 2, y + cap + 6), ln, font=f, fill=(0, 0, 0, 120), anchor="ms")
                y += passo
        _sombra_texto(img, sombra)
        d = ImageDraw.Draw(img)
        y = y0
        for ln in linhas:
            # pela linha de base: acento (Ç, Õ, Í) não empurra a linha para baixo
            d.text((L // 2, y + cap), ln, font=f, fill=CREME_TXT, anchor="ms")
            y += passo
        if destaque:
            fd = _poppins(40, "SemiBold")
            w = d.textlength(destaque, font=fd) + 60
            d.rounded_rectangle([(L - w) / 2, y + 10, (L + w) / 2, y + 80], radius=35, fill=PINK)
            d.text((L // 2, y + 45), destaque, font=fd, fill=BRANCO, anchor="mm")
        _brilho(d, 120, y0 - 50, 34)
        _brilho(d, L - 130, y0 + h + 30, 40)
        _brilho(d, L - 200, y0 - 90, 22)
    else:
        d = ImageDraw.Draw(img)
        f, linhas = _caber(d, titulo, [_poppins(t, "SemiBold") for t in (60, 52, 46)], L - 220, 3)
        y = _faixa_livre(img, len(linhas) * 104 + (130 if destaque else 0), proibidas=proibidas)
        for i, ln in enumerate(linhas):
            w = d.textlength(ln, font=f)
            d.rectangle([(L - w) / 2 - 26, y, (L + w) / 2 + 26, y + 92], fill=BRANCO if i % 2 == 0 else (236, 214, 248))
            d.text((L // 2, y + 46), ln, font=f, fill=UVA, anchor="mm")
            y += 104
        if destaque:
            fd = _fredoka(96)
            _sombra_texto(img, lambda dc: dc.text((L // 2, y + 70), destaque, font=fd, fill=(0, 0, 0, 110), anchor="mm"), 5)
            d = ImageDraw.Draw(img)
            d.text((L // 2, y + 64), destaque, font=fd, fill=BRANCO, anchor="mm", stroke_width=4, stroke_fill=PINK)
    d.text((L // 2, A - 70), ARROBA, font=_poppins(28, "SemiBold"), fill=BRANCO, anchor="mm",
           stroke_width=2, stroke_fill=(0, 0, 0))
    return img


def foto_de_capa(temas, rng=random):
    """Sorteia uma foto entre as pastas assets/capas/<tema> indicadas.
    A foto volta com `.rostos` (caixas relativas, de assets/capas/rostos.json)."""
    fotos = [f for t in temas for f in sorted((CAPAS / t).glob("*.jpg"))]
    if not fotos:
        return None
    escolhida = rng.choice(fotos)
    img = Image.open(escolhida).convert("RGB")
    try:
        import json
        img.rostos = json.loads((CAPAS / "rostos.json").read_text()).get(f"{escolhida.parent.name}/{escolhida.name}", [])
    except (OSError, ValueError):
        img.rostos = []
    return img


# ---------- 4) slide final ----------

def final(chamada="Comenta GRUPO que eu te mando o link", L=1080, A=1350, y0=0):
    img = Image.new("RGB", (L, A), UVA)
    d = ImageDraw.Draw(img)
    ic = _icone(520)
    img.paste(ic, ((L - ic.width) // 2, y0 + 120), ic)
    y = y0 + 720
    for ln in ["Quer receber as", "ofertas do dia?"]:
        d.text((L // 2, y + 62), ln, font=_fredoka(84), fill=BRANCO, anchor="ms")
        y += 96
    for i, ln in enumerate(["Postamos promoções o dia todo no nosso", "grupo de WhatsApp e no Telegram."]):
        d.text((L // 2, y + 46 + 46 * i), ln, font=_poppins(34, "Regular"), fill=LAVANDA_2, anchor="ms")
    if chamada:
        f = _fredoka(46)
        w = d.textlength(chamada, font=f) + 90
        d.rounded_rectangle([(L - w) / 2, y0 + 1100, (L + w) / 2, y0 + 1196], radius=48, fill=PINK)
        d.text((L // 2, y0 + 1148), chamada, font=f, fill=BRANCO, anchor="mm")
    d.text((L // 2, y0 + 1250), f"grupo gratuito  ·  {RODAPE}", font=_poppins(26), fill=LAVANDA_2, anchor="mm")
    return img


# ---------- posts institucionais (fixados no perfil) ----------

def _linha_justificada(d, x, y, linha, fonte, largura, cor, ultima=False):
    """Desenha a linha justificada (espaços distribuídos). A última linha do parágrafo fica à esquerda."""
    palavras = linha.split(" ")
    if ultima or len(palavras) < 2:
        d.text((x, y), linha, font=fonte, fill=cor, anchor="ls")
        return
    ocupado = sum(d.textlength(p, font=fonte) for p in palavras)
    espaco = (largura - ocupado) / (len(palavras) - 1)
    cx = x
    for p in palavras:
        d.text((cx, y), p, font=fonte, fill=cor, anchor="ls")
        cx += d.textlength(p, font=fonte) + espaco


def slide_texto(numero, titulo, texto, indice=None, L=1080, A=1350):
    """Slide explicativo: número grande, título e texto curto."""
    img = _fundo(L, A)
    d = ImageDraw.Draw(img)
    _cabecalho(img)
    if indice:
        f = _fredoka(36)
        _pilula(d, (L - 60 - d.textlength(indice, font=f) - 56, 70), indice, f, BRANCO, UVA)
    ft, linhas = _caber(d, titulo, [_fredoka(t) for t in (92, 80, 70)], L - 150, 3)
    cap = ft.getbbox("H", anchor="ls")[3] - ft.getbbox("H", anchor="ls")[1]
    fb = _poppins(46, "Regular")
    corpo = [_quebrar(d, par, fb, L - 150, 6) for par in texto.split("\n")]
    # mede o bloco inteiro para centralizar na área livre
    h = (200 if numero else 0) + len(linhas) * int(cap * 1.45) + 50 \
        + sum(len(c) * 64 + 30 for c in corpo)
    y = 170 + max(0, (1300 - 170 - h) // 2)
    if numero:
        d.ellipse([70, y, 230, y + 160], fill=PINK)
        d.text((150, y + 80), str(numero), font=_fredoka(100), fill=BRANCO, anchor="mm")
        y += 200
    for ln in linhas:
        d.text((72, y + cap), ln, font=ft, fill=UVA, anchor="ls")
        y += int(cap * 1.45)
    y += 50
    for c in corpo:
        for k, ln in enumerate(c):
            _linha_justificada(d, 72, y + 46, ln, fb, L - 150, SUAVE, ultima=(k == len(c) - 1))
            y += 64
        y += 30
    return img


def final_grupo(L=1080, A=1350):
    """Último slide dos posts fixados: como entrar no grupo."""
    img = Image.new("RGB", (L, A), UVA)
    d = ImageDraw.Draw(img)
    ic = _icone(460)
    img.paste(ic, ((L - ic.width) // 2, 130), ic)
    y = 690
    for ln in ["Entre no nosso", "grupo gratuito"]:
        d.text((L // 2, y + 62), ln, font=_fredoka(84), fill=BRANCO, anchor="ms")
        y += 96
    for i, ln in enumerate(["Toque no link da bio e escolha", "WhatsApp ou Telegram."]):
        d.text((L // 2, y + 46 + 46 * i), ln, font=_poppins(34, "Regular"), fill=LAVANDA_2, anchor="ms")
    f = _fredoka(52)
    t = "Link na bio"
    w = d.textlength(t, font=f) + 100
    d.rounded_rectangle([(L - w) / 2, 1100, (L + w) / 2, 1200], radius=50, fill=PINK)
    d.text((L // 2, 1150), t, font=f, fill=BRANCO, anchor="mm")
    return img


INSTITUCIONAIS = {
    "como_funciona": {
        "capa": ("Como funciona o Chocalho de Ofertas", "faixas", ["familia", "quarto"]),
        "slides": [
            (1, "A gente garimpa", "Todo dia procuramos promoções de produtos para bebês e crianças: enxoval, "
                                   "brinquedos, passeio, alimentação e mais.\nSó entra o que está com desconto."),
            (2, "Você recebe no grupo", "A oferta chega no nosso grupo gratuito com foto, preço e o link.\n"
                                        "Sem spam: só os administradores postam."),
            (3, "Compra direto na loja", "O link leva para a página oficial do produto, e você paga o mesmo preço.\n"
                                         "Pagamento, entrega e garantia são direto com a loja."),
            (4, "Promoção acaba rápido", "Preço e estoque podem mudar a qualquer momento.\n"
                                         "Sempre confira na loja antes de finalizar a compra."),
        ],
    },
    "o_que_e": {
        "capa": ("Prazer, Chocalho de Ofertas", "grande", ["quarto", "enxoval"]),
        "slides": [
            (None, "Pra famílias que amam economizar", "Somos um canal de ofertas de produtos para bebês e "
                                                       "crianças, do enxoval aos brinquedos."),
            (None, "O que você encontra", "Promoções do dia com desconto de verdade.\nCupons das lojas assim que saem."),
            (None, "Onde acompanhar", "No grupo gratuito do WhatsApp, no canal do Telegram e aqui no perfil.\n"
                                      "Você entra e sai quando quiser."),
        ],
    },
    "perguntas": {
        "capa": ("Perguntas frequentes", "grande", []),
        "slides": [
            (None, "É de graça?", "Sim, entrar no grupo e no canal é gratuito.\n"
                                  "Você só paga pelo produto, se decidir comprar, e direto na loja."),
            (None, "Vocês vendem os produtos?", "Não. A compra é feita direto na loja oficial.\n"
                                                "Entrega, troca e garantia são com a loja."),
            (None, "É seguro comprar pelo link?", "Sim. O link leva para a página oficial do produto na loja, "
                                                  "e o pagamento é feito lá, como numa compra normal."),
            (None, "Como me proteger de golpes?", "A gente nunca pede Pix, senha ou dados pessoais, e não cobra "
                                                  "nada para entrar no grupo.\nDesconfie de perfis parecidos com o "
                                                  "nosso: o oficial é o @chocalhodeofertas.\nE finalize a compra "
                                                  "sempre na página oficial da loja."),
            (None, "Os produtos são originais?", "Quem vende é a loja. Antes de comprar, vale conferir a reputação "
                                                 "do vendedor e as avaliações de quem já comprou."),
            (None, "Por que o preço mudou quando abri o link?", "Algumas promoções duram poucas horas ou acabam "
                                                                "quando o estoque termina.\nPor isso a gente posta "
                                                                "assim que encontra."),
            (None, "Posso pedir um produto específico?", "Pode! Manda no direct o que você está procurando, e a "
                                                         "gente fica de olho nas promoções dele."),
        ],
    },
}


def _balao(d, x, y, w, h, cor, cor_txt, texto="?"):
    d.rounded_rectangle([x, y, x + w, y + h], radius=h // 3, fill=cor)
    d.polygon([(x + w * 0.22, y + h - 2), (x + w * 0.22, y + h + h * 0.32), (x + w * 0.42, y + h - 2)], fill=cor)
    d.text((x + w / 2, y + h / 2), texto, font=_fredoka(int(h * 0.62)), fill=cor_txt, anchor="mm")


def capa_marca(nome, L=1080, A=1350):
    """Capas dos posts da marca: identidade visual, sem foto."""
    if nome == "o_que_e":
        img = _fundo(L, A)
        d = ImageDraw.Draw(img)
        ic = _icone(640)
        img.paste(ic, ((L - ic.width) // 2, 110), ic)
        f = _fredoka(92)
        d.text((L // 2, 900), "Prazer,", font=f, fill=UVA, anchor="ms")
        d.text((L // 2, 1010), "Chocalho de Ofertas", font=f, fill=PINK, anchor="ms")
        _pilula(d, ((L - d.textlength("para famílias que amam economizar", font=_poppins(34, "SemiBold")) - 68) / 2, 1070),
                "para famílias que amam economizar", _poppins(34, "SemiBold"), UVA, BRANCO, pad=(34, 14))
    elif nome == "como_funciona":
        img = Image.new("RGB", (L, A), UVA)
        d = ImageDraw.Draw(img)
        f = _fredoka(140)
        d.text((L // 2, 470), "Como", font=f, fill=BRANCO, anchor="ms")
        w2 = d.textlength("funciona?", font=f)
        ic = _icone(190)
        total = w2 + 30 + ic.width
        x0 = (L - total) / 2
        d.text((x0, 640), "funciona?", font=f, fill=BRANCO, anchor="ls")
        img.paste(ic, (int(x0 + w2 + 30), 640 - ic.height + 20), ic)
        fp = _fredoka(48)
        t = "em 4 passos"
        w = d.textlength(t, font=fp) + 90
        d.rounded_rectangle([(L - w) / 2, 780, (L + w) / 2, 870], radius=45, fill=PINK)
        d.text((L // 2, 825), t, font=fp, fill=BRANCO, anchor="mm")
        for k in range(4):
            cx = L // 2 + (k - 1.5) * 150
            d.ellipse([cx - 52, 960, cx + 52, 1064], outline=LAVANDA_2, width=6)
            d.text((cx, 1012), str(k + 1), font=_fredoka(60), fill=LAVANDA_2, anchor="mm")
    else:  # perguntas — mesmo fundo lilás da primeira capa
        img = _fundo(L, A)
        d = ImageDraw.Draw(img)
        _balao(d, 120, 150, 220, 160, PINK, BRANCO)
        _balao(d, 700, 110, 260, 190, UVA, BRANCO)
        _balao(d, 820, 980, 170, 130, PINK, BRANCO)
        f = _fredoka(130)
        d.text((L // 2, 560), "Perguntas", font=f, fill=UVA, anchor="ms")
        d.text((L // 2, 700), "frequentes", font=f, fill=PINK, anchor="ms")
        d.text((L // 2, 790), "as dúvidas que mais chegam pra gente", font=_poppins(36, "SemiBold"), fill=SUAVE, anchor="ms")
        ic = _icone(340)
        img.paste(ic, ((L - ic.width) // 2 - 80, 900), ic)
    d.text((L // 2, A - 50), ARROBA, font=_poppins(26, "SemiBold"), fill=LAVANDA_2 if nome == "como_funciona" else SUAVE,
           anchor="mm")
    return img


def institucional(nome, rng=random):
    """Slides de um post fixado (capa com foto + explicação + como entrar no grupo)."""
    cfg = INSTITUCIONAIS[nome]
    n = len(cfg["slides"])
    return ([capa_marca(nome)]
            + [slide_texto(num, t, txt, indice=f"{k}/{n}") for k, (num, t, txt) in enumerate(cfg["slides"], 1)]
            + [final_grupo()])


# ---------- 5) carrossel e Reel ----------

def carrossel(ofertas, fotos, titulo, foto_capa, destaque=None, estilo="grande"):
    """Lista de imagens PIL: capa, produtos (n/total) e final."""
    n = len(ofertas)
    return ([capa(foto_capa, titulo, destaque, estilo)]
            + [post(o, f, cta=None, indice=f"{i + 1}/{n}") for i, (o, f) in enumerate(zip(ofertas, fotos))]
            + [final()])


def _em_9x16(quadro, cor):
    c = Image.new("RGB", (1080, 1920), cor)
    c.paste(quadro, (0, (1920 - quadro.height) // 2))
    return c


def reel(ofertas, fotos, titulo, foto_capa, destaque=None, estilo="grande", fps=30):
    """Bytes MP4 (9:16, sem música — a música entra no app na hora de postar)."""
    if not shutil.which("ffmpeg"):
        return None
    capa_916 = capa(foto_capa, titulo, destaque, estilo, L=1080, A=1920)
    cenas = ([(capa_916, 2.8)]
             + [(story(o, f, area_link=False), 3.2) for o, f in zip(ofertas, fotos)]
             + [(final(chamada=None, A=1920, y0=285), 3.0)])
    trans = int(0.4 * fps)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        n = 0

        def zoom(im, t):  # leve aproximação
            z = 1 + 0.035 * t
            w, h = int(1080 / z), int(1920 / z)
            x, y = (1080 - w) // 2, (1920 - h) // 2
            return im.crop((x, y, x + w, y + h)).resize((1080, 1920), Image.BILINEAR)

        for i, (im, dur) in enumerate(cenas):
            tot = int(dur * fps)
            for f in range(tot):
                q = zoom(im, f / tot)
                if i > 0 and f < trans:  # entra deslizando da direita
                    e = 1 - (1 - f / trans) ** 3
                    c = Image.new("RGB", (1080, 1920))
                    off = int(1080 * (1 - e))
                    c.paste(zoom(cenas[i - 1][0], 1.0), (off - 1080, 0))
                    c.paste(q, (off, 0))
                    q = c
                q.save(tmp / f"{n:05d}.jpg", quality=90)
                n += 1
        saida = tmp / "reel.mp4"
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(tmp / "%05d.jpg"),
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
                            "-movflags", "+faststart", str(saida)])
        if r.returncode != 0 or not saida.exists():
            return None
        return saida.read_bytes()


def png(img):
    return _png(img)
