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
