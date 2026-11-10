"""Carrossel do TikTok (modo foto, 9:16): capa com foto, um produto por slide
numa cena realista e um CTA final. Visual editorial, com o mínimo de cara de
anúncio: sem porcentagem, sem @ (só no último slide).

Zonas seguras do TikTok: a interface cobre ~8% no topo, ~22% embaixo
(legenda, música) e ~14% na direita (botões). Todo texto fica fora delas.
"""
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from bot.arte import ARROBA, _icone, _png

RAIZ = Path(__file__).resolve().parent.parent
FONTES = RAIZ / "assets" / "fonts"

L, A = 1080, 1920
MARGEM = 84                     # esquerda
DIREITA = L - 150               # limite direito (botões do TikTok)
TOPO_SEGURO = 170
BASE_SEGURA = int(A * 0.76)     # abaixo disso a legenda cobre

BRANCO = (255, 255, 255)
CREME = (248, 242, 233)
CREME_2 = (238, 228, 214)
TINTA = (52, 40, 44)            # quase preto quente
TINTA_SUAVE = (126, 110, 108)
ROSE = (190, 120, 128)          # acento discreto


def _serif(tam, peso=500, italico=False):
    f = ImageFont.truetype(str(FONTES / ("PlayfairDisplay-Italic.ttf" if italico else "PlayfairDisplay.ttf")), tam)
    try:
        f.set_variation_by_axes([peso])
    except Exception:  # noqa: BLE001
        pass
    return f


def _sans(tam, peso=500):
    f = ImageFont.truetype(str(FONTES / "Inter.ttf"), tam)
    try:
        f.set_variation_by_axes([min(32, max(14, tam // 2)), peso])
    except Exception:  # noqa: BLE001
        pass
    return f


def brl(v):
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _cobrir(foto, largura=L, altura=A, foco_y=0.5):
    foto = foto.convert("RGB")
    esc = max(largura / foto.width, altura / foto.height)
    f = foto.resize((round(foto.width * esc), round(foto.height * esc)), Image.LANCZOS)
    x = (f.width - largura) // 2
    y = int((f.height - altura) * foco_y)
    return f.crop((x, y, x + largura, y + altura))


def _degrade(img, y0, y1, alfa_max, de_cima=False):
    """Escurece suavemente uma faixa (para o texto branco respirar)."""
    camada = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(camada)
    for y in range(y0, y1):
        t = (y - y0) / max(1, y1 - y0)
        a = alfa_max * ((1 - t) if de_cima else t)
        d.line([(0, y), (img.width, y)], fill=int(a))
    if not de_cima:
        d.rectangle([0, y1, img.width, img.height], fill=alfa_max)
    preto = Image.new("RGB", img.size, (20, 14, 16))
    return Image.composite(preto, img, camada)


def _quebrar(d, texto, fonte, largura):
    linhas, atual = [], ""
    for p in texto.replace("R$ ", "R$ ").split():
        t = f"{atual} {p}".strip()
        if d.textlength(t, font=fonte) <= largura or not atual:
            atual = t
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def _sombra(img, desenhar, raio=10, opacidade=110):
    """Desenha o texto com uma sombra difusa, quase imperceptível."""
    m = Image.new("L", img.size, 0)
    desenhar(ImageDraw.Draw(m), 255)
    m = m.filter(ImageFilter.GaussianBlur(raio)).point(lambda v: v * opacidade // 255)
    img.paste(Image.new("RGB", img.size, (15, 10, 12)), (0, 0), m)
    desenhar(ImageDraw.Draw(img), None)


# ---------- títulos limpos ----------

_RUIDO = re.compile(
    r"\b(?:[A-Z]{1,4}\d[\w-]*|\d+\s*(?:un|unidades|pe[cç]as|kgs?|cm|m)\b|cor\b.*|"
    r"azul|rosa|cinza|preto|branco|bege|grafite|verde|amarel[oa]|vermelh[oa]|lil[aá]s|"
    r"menin[oa]|unissex|infantil|beb[eê]s?|original|novo|promo[cç][aã]o)\b",
    re.I,
)


_SOLTAS = {"de", "da", "do", "das", "dos", "com", "e", "para", "pra", "em", "a", "o", "turma", "descartável"}


def titulo_limpo(titulo, max_palavras=4):
    """'Berço Portátil Bebê Acoplado Co-Bed Connect Maxi baby - GRAFITE'
    -> 'Berço Portátil Acoplado Co-Bed'. Para o slide, curto e sem código."""
    t = re.split(r"\s*[,(|]\s*|\s[-–]\s", titulo)[0]
    t = _RUIDO.sub(" ", t)
    palavras = [p for p in t.split() if len(p) > 1 or p.isalpha()][:max_palavras]
    while len(palavras) > 1 and palavras[-1].lower() in _SOLTAS:
        palavras.pop()
    return " ".join(palavras) or titulo.split()[0]


# ---------- slides ----------

def capa(foto, titulo, apoio=None, foco_y=0.5):
    """Foto de ambiente + título em serifa branca, centralizado no terço alto."""
    img = _cobrir(foto, foco_y=foco_y)
    img = _degrade(img, 0, 1150, 155, de_cima=True)
    d = ImageDraw.Draw(img)

    largura = DIREITA - MARGEM
    for tam in (104, 96, 88, 80, 72):
        f = _serif(tam, 500)
        linhas = _quebrar(d, titulo, f, largura)
        if len(linhas) <= 4:
            break
    passo = int(tam * 1.14)
    y = 360
    pos = []
    for ln in linhas:
        pos.append((MARGEM, y, ln))
        y += passo
    fa = _serif(int(tam * 0.56), 400, italico=True)
    if apoio:
        y += int(tam * 0.18)
        pos_apoio = (MARGEM, y, apoio)

    def escrever(dd, cor):
        for x, yy, ln in pos:
            dd.text((x, yy), ln, font=f, fill=cor or BRANCO, anchor="ls")
        if apoio:
            dd.text(pos_apoio[:2], apoio, font=fa, fill=cor or (250, 238, 226), anchor="ls")

    _sombra(img, escrever)
    # fiozinho fino acima do título, toque editorial
    d = ImageDraw.Draw(img)
    d.line([(MARGEM, 360 - tam - 26), (MARGEM + 90, 360 - tam - 26)], fill=(250, 238, 226), width=3)
    return img


def _seta(d, x0, x1, y, cor, esp=4):
    d.line([(x0, y), (x1, y)], fill=cor, width=esp)
    d.line([(x1 - 16, y - 12), (x1, y)], fill=cor, width=esp)
    d.line([(x1 - 16, y + 12), (x1, y)], fill=cor, width=esp)


def produto(cena, titulo, preco, preco_de=None, numero=None, total=None, foco_y=0.5,
            nota="imagem ilustrativa"):
    """Produto aplicado numa cena. Título limpo no topo, cartão creme com
    'de R$ X → R$ Y' na base da área segura."""
    img = _cobrir(cena, foco_y=foco_y)
    img = _degrade(img, 0, 520, 120, de_cima=True)
    d = ImageDraw.Draw(img)

    # título no topo
    largura = DIREITA - MARGEM
    for tam in (78, 72, 66, 60):
        f = _serif(tam, 500)
        linhas = _quebrar(d, titulo, f, largura)
        if len(linhas) <= 2:
            break
    y = TOPO_SEGURO + 90
    pos = []
    if numero:
        fnum = _sans(30, 500)
        pos_num = (MARGEM, y - tam - 14, f"{numero:02d}" + (f" / {total:02d}" if total else ""))
    for ln in linhas:
        pos.append((MARGEM, y, ln))
        y += int(tam * 1.12)

    def escrever(dd, cor):
        if numero:
            dd.text(pos_num[:2], pos_num[2], font=fnum, fill=cor or (250, 238, 226), anchor="ls")
        for x, yy, ln in pos:
            dd.text((x, yy), ln, font=f, fill=cor or BRANCO, anchor="ls")

    _sombra(img, escrever)

    # cartão de preço
    fde = _sans(34, 400)
    fpor = _serif(84, 600)
    de_txt = f"de {brl(preco_de)}" if preco_de and preco_de > preco else None
    por_txt = brl(preco)
    d = ImageDraw.Draw(img)
    w_de = d.textlength(de_txt, font=fde) if de_txt else 0
    w_por = d.textlength(por_txt, font=fpor)
    seta = 70 if de_txt else 0
    larg = int(w_de + seta + w_por + (60 if de_txt else 0) + 72)
    alt = 150
    x0, y1 = MARGEM, BASE_SEGURA - 30
    y0 = y1 - alt

    # sombra do cartão
    sh = Image.new("L", img.size, 0)
    ImageDraw.Draw(sh).rounded_rectangle([x0 + 4, y0 + 14, x0 + larg + 4, y1 + 14], 36, fill=90)
    sh = sh.filter(ImageFilter.GaussianBlur(22))
    img.paste(Image.new("RGB", img.size, (30, 20, 22)), (0, 0), sh)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0, y0, x0 + larg, y1], 36, fill=CREME)

    meio = (y0 + y1) // 2
    x = x0 + 36
    if de_txt:
        d.text((x, meio + 12), de_txt, font=fde, fill=TINTA_SUAVE, anchor="ls")
        yy = meio + 12 - 12
        d.line([(x, yy), (x + w_de, yy)], fill=TINTA_SUAVE, width=2)
        x += w_de + 30
        _seta(d, x, x + seta - 10, meio, ROSE, 4)
        x += seta + 30 - 10
    d.text((x, meio + 30), por_txt, font=fpor, fill=TINTA, anchor="ls")

    if nota:
        fn = _sans(24, 500)
        _sombra(img, lambda dd, cor: dd.text((x0 + 8, y1 + 48), nota, font=fn,
                                             fill=cor or (250, 245, 238), anchor="ls"), raio=6, opacidade=170)
    return img


def cta(chamada="Quer o link do produto ou do grupo?",
        apoio="Comenta aqui embaixo\nque eu te mando"):
    img = Image.new("RGB", (L, A), CREME)
    d = ImageDraw.Draw(img)
    # moldura fina
    d.rounded_rectangle([56, 56, L - 56, A - 56], 44, outline=CREME_2, width=3)

    ic = _icone(170)
    img.paste(ic, ((L - ic.width) // 2, 430), ic)
    d = ImageDraw.Draw(img)

    f = _serif(84, 500)
    linhas = _quebrar(d, chamada, f, L - 2 * 150)
    y = 780
    for ln in linhas:
        d.text((L // 2, y), ln, font=f, fill=TINTA, anchor="ms")
        y += 100
    y += 10
    d.line([(L // 2 - 45, y), (L // 2 + 45, y)], fill=ROSE, width=3)
    y += 80
    fa = _serif(50, 400, italico=True)
    for ln in apoio.split("\n"):
        d.text((L // 2, y), ln, font=fa, fill=TINTA_SUAVE, anchor="ms")
        y += 64

    d.text((L // 2, 1300), ARROBA, font=_sans(36, 500), fill=TINTA, anchor="ms")
    d.text((L // 2, 1350), "promoções temporárias  ·  #publi", font=_sans(26, 400), fill=TINTA_SUAVE, anchor="ms")
    return img


def carrossel(foto_capa, titulo, apoio, itens):
    """itens: [(cena, titulo, preco, preco_de)] -> lista de PNG (bytes)."""
    slides = [capa(foto_capa, titulo, apoio)]
    for k, (cena, t, p, de) in enumerate(itens, 1):
        slides.append(produto(cena, t, p, de))
    slides.append(cta())
    return [_png(s) for s in slides]
