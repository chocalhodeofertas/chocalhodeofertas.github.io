"""Carrossel em cena (TikTok e Instagram), 4:5 — 1080x1350, o mesmo arquivo
serve aos dois. Capa com foto, um produto por slide numa cena realista e um
CTA final. Visual editorial, com o mínimo de cara de anúncio: sem porcentagem,
sem @ (só no último slide).
"""
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

from bot.arte import ARROBA, _icone, _png

RAIZ = Path(__file__).resolve().parent.parent
FONTES = RAIZ / "assets" / "fonts"

L, A = 1080, 1350
MARGEM = 84

BRANCO = (255, 255, 255)
CREME = (248, 242, 233)
CREME_2 = (238, 228, 214)
TINTA = (40, 30, 34)            # quase preto quente
TINTA_SUAVE = (126, 110, 108)
ROSE = (190, 120, 128)          # acento discreto
ROXO = (142, 43, 176)           # roxo da marca


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


def _sombra_caixa(img, caixa, raio_canto, desfoque=22, forca=80, dy=12):
    x0, y0, x1, y1 = caixa
    sh = Image.new("L", img.size, 0)
    ImageDraw.Draw(sh).rounded_rectangle([x0 + 2, y0 + dy, x1 + 2, y1 + dy], raio_canto, fill=forca)
    sh = sh.filter(ImageFilter.GaussianBlur(desfoque))
    img.paste(Image.new("RGB", img.size, (30, 20, 22)), (0, 0), sh)


def _legivel(img, caixa):
    """Texto branco funciona aqui? (fundo escuro o bastante e sem muito ruído)"""
    st = ImageStat.Stat(img.crop(caixa).convert("L"))
    return st.mean[0] < 150 and st.stddev[0] < 60


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

LAVANDA = (241, 225, 251)
UVA = (58, 10, 64)
ESTILOS_CAPA = ("faixas", "grandes")


def _poppins(tam, peso="ExtraBold"):
    return ImageFont.truetype(str(FONTES / f"Poppins-{peso}.ttf"), tam)


def _linhas_caps(d, titulo, tamanhos, largura, peso="ExtraBold", max_linhas=3):
    """Título em maiúsculas: respeita '\n' ou quebra sozinho; devolve (fonte, linhas)."""
    titulo = titulo.upper()
    for tam in tamanhos:
        f = _poppins(tam, peso)
        if "\n" in titulo:
            linhas = [ln.strip() for ln in titulo.split("\n")]
        else:
            linhas = _quebrar(d, titulo, f, largura)
        if len(linhas) <= max_linhas and all(d.textlength(ln, font=f) <= largura for ln in linhas):
            return f, tam, linhas
    return f, tam, linhas


def _etiqueta(d, x, y, texto, fonte, fundo, cor, px=28, alt=72, raio=36):
    w = d.textlength(texto, font=fonte)
    d.rounded_rectangle([x, y, x + w + 2 * px, y + alt], raio, fill=fundo)
    d.text((x + px, y + alt // 2), texto, font=fonte, fill=cor, anchor="lm")


def capa_faixas(foto, titulo, apoio=None, foco_y=0.5):
    """Estilo A: título em maiúsculas sem serifa, cada linha numa faixa lavanda
    com letra roxo-escura; apoio numa etiqueta roxa."""
    img = _cobrir(foto, foco_y=foco_y)
    img = _degrade(img, 0, 700, 90, de_cima=True)
    d = ImageDraw.Draw(img)
    f, tam, linhas = _linhas_caps(d, titulo, (88, 84, 78, 72, 66), L - 2 * MARGEM - 36)
    alt = int(tam * 1.29)
    y = 150
    for ln in linhas:
        w = d.textlength(ln, font=f)
        d.rectangle([MARGEM - 18, y, MARGEM + w + 18, y + alt], fill=LAVANDA)
        d.text((MARGEM, y + alt // 2 + 2), ln, font=f, fill=UVA, anchor="lm")
        y += alt + 10
    if apoio:
        _etiqueta(d, MARGEM - 18, y + 22, apoio, _poppins(36, "SemiBold"), ROXO, BRANCO, raio=10, alt=70)
    return img


def capa_grandes(foto, titulo, apoio=None, destaque=(), foco_y=0.5):
    """Estilo B: título enorme em maiúsculas, branco, com a(s) palavra(s) de
    `destaque` em lavanda; apoio numa etiqueta branca arredondada."""
    img = _cobrir(foto, foco_y=foco_y)
    img = _degrade(img, 0, 900, 170, de_cima=True)
    d = ImageDraw.Draw(img)
    f, tam, linhas = _linhas_caps(d, titulo, (122, 112, 104, 96, 88, 80), L - 2 * MARGEM, max_linhas=4)
    destaque = {p.upper() for p in destaque}
    passo = int(tam * 1.03)
    pos = [(MARGEM, 120 + tam + k * passo, ln) for k, ln in enumerate(linhas)]

    def escrever(dd, cor):
        for x, yy, ln in pos:
            for pal in ln.split(" "):
                c = cor if cor is not None else (LAVANDA if pal.strip(".,!?") in destaque else BRANCO)
                dd.text((x, yy), pal, font=f, fill=c, anchor="ls")
                x += dd.textlength(pal + " ", font=f)

    _sombra(img, escrever, raio=12, opacidade=130)
    if apoio:
        d = ImageDraw.Draw(img)
        _etiqueta(d, MARGEM, pos[-1][1] + 40, apoio, _poppins(38, "SemiBold"), BRANCO, UVA)
    return img


def capa(foto, titulo="Se eu estivesse montando um enxoval",
         apoio="eu colocaria isso no carrinho hoje", foco_y=0.5, estilo="classico", destaque=()):
    """Foto de ambiente + título grande em serifa branca e, logo abaixo,
    a frase de apoio numa etiqueta branca de cantos levemente arredondados.
    estilo: 'classico' (serifa), 'faixas' (A) ou 'grandes' (B). Vale variar."""
    if estilo == "faixas":
        return capa_faixas(foto, titulo, apoio, foco_y)
    if estilo == "grandes":
        return capa_grandes(foto, titulo, apoio, destaque, foco_y)
    img = _cobrir(foto, foco_y=foco_y)
    img = _degrade(img, 0, 900, 150, de_cima=True)
    d = ImageDraw.Draw(img)

    largura = L - 2 * MARGEM
    # "\n" no título força a quebra de linha (ex.: 2 linhas exatas)
    for tam in (112, 104, 96, 88, 80, 72):
        f = _serif(tam, 500)
        if "\n" in titulo:
            linhas = titulo.split("\n")
            if all(d.textlength(ln, font=f) <= largura for ln in linhas):
                break
            continue
        linhas = _quebrar(d, titulo, f, largura)
        if len(linhas) <= 3:
            break
    passo = int(tam * 1.12)
    y_base = 150 + tam
    pos = [(MARGEM, y_base + k * passo, ln) for k, ln in enumerate(linhas)]

    def escrever(dd, cor):
        for x, yy, ln in pos:
            dd.text((x, yy), ln, font=f, fill=cor or BRANCO, anchor="ls")

    _sombra(img, escrever)
    d = ImageDraw.Draw(img)
    d.line([(MARGEM, 150 - 34), (MARGEM + 90, 150 - 34)], fill=(250, 238, 226), width=3)

    if apoio:
        fa = _serif(50, 500, italico=True)
        w = d.textlength(apoio, font=fa)
        px, alt = 30, 84
        x0 = MARGEM
        y0 = pos[-1][1] + 44
        caixa = (x0, y0, int(x0 + w + 2 * px), y0 + alt)
        _sombra_caixa(img, caixa, 10, desfoque=16, forca=70, dy=8)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(caixa, 10, fill=BRANCO)
        d.text((x0 + px, y0 + alt // 2 + 2), apoio, font=fa, fill=TINTA, anchor="lm")
    return img


def _seta(d, x0, x1, y, cor, esp=4):
    d.line([(x0, y), (x1, y)], fill=cor, width=esp)
    d.line([(x1 - 16, y - 12), (x1, y)], fill=cor, width=esp)
    d.line([(x1 - 16, y + 12), (x1, y)], fill=cor, width=esp)


def produto(cena, titulo, preco, preco_de=None, foco_y=0.5, titulo_em=None):
    """Produto aplicado numa cena. Cartão creme 'de R$ X → R$ Y' centralizado
    na parte de baixo e o nome do produto, sem fundo, logo acima dele. Se o
    fundo ali não der leitura, o nome sobe para o topo (centralizado).
    titulo_em: 'cartao' (padrão), 'topo' ou 'auto'."""
    img = _cobrir(cena, foco_y=foco_y)
    d = ImageDraw.Draw(img)

    # cartão de preço (medidas)
    fde = _sans(32, 400)
    fpor = _serif(76, 600)
    de_txt = f"de {brl(preco_de)}" if preco_de and preco_de > preco else None
    por_txt = brl(preco)
    w_de = d.textlength(de_txt, font=fde) if de_txt else 0
    w_por = d.textlength(por_txt, font=fpor)
    seta = 64 if de_txt else 0
    larg = int(w_de + seta + w_por + (52 if de_txt else 0) + 72)
    alt = 136
    x0 = (L - larg) // 2
    y1 = A - 96
    y0 = y1 - alt

    # nome do produto
    largura = L - 2 * MARGEM
    for tam in (72, 66, 60, 54):
        f = _serif(tam, 500)
        linhas = _quebrar(d, titulo, f, largura)
        if len(linhas) <= 2:
            break
    passo = int(tam * 1.12)
    alt_txt = passo * (len(linhas) - 1) + tam
    y_cartao = y0 - 34 - passo * (len(linhas) - 1)          # base da 1ª linha
    faixa = (MARGEM, y_cartao - tam - 20, L - MARGEM, y0 - 10)
    # padrão aprovado: nome logo acima do preço; o degradê garante a leitura.
    # 'auto' sobe o nome para o topo quando o fundo ali é claro/agitado demais.
    onde = titulo_em or "cartao"
    if onde == "auto":
        onde = "cartao" if _legivel(img, faixa) else "topo"
    if onde == "topo":
        img = _degrade(img, 0, 420, 125, de_cima=True)
        y_ini = 110 + tam
    else:
        img = _degrade(img, y_cartao - tam - 220, A, 150)
        y_ini = y_cartao
    pos = [(L // 2, y_ini + k * passo, ln) for k, ln in enumerate(linhas)]

    def escrever(dd, cor):
        for x, yy, ln in pos:
            dd.text((x, yy), ln, font=f, fill=cor or BRANCO, anchor="ms")

    _sombra(img, escrever)

    _sombra_caixa(img, (x0, y0, x0 + larg, y1), 34, forca=90)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0, y0, x0 + larg, y1], 34, fill=CREME)
    meio = (y0 + y1) // 2
    x = x0 + 36
    if de_txt:
        d.text((x, meio + 11), de_txt, font=fde, fill=TINTA_SUAVE, anchor="ls")
        yy = meio
        d.line([(x, yy), (x + w_de, yy)], fill=TINTA_SUAVE, width=2)
        x += w_de + 26
        _seta(d, x, x + seta - 10, meio, ROSE, 4)
        x += seta + 26 - 10
    d.text((x, meio + 27), por_txt, font=fpor, fill=TINTA, anchor="ls")
    return img


def _linha_mista(d, cx, y, partes, fonte):
    """Escreve uma linha centralizada com trechos de cores diferentes."""
    total = sum(d.textlength(t, font=fonte) for t, _ in partes)
    x = cx - total / 2
    for t, cor in partes:
        d.text((x, y), t, font=fonte, fill=cor, anchor="ls")
        x += d.textlength(t, font=fonte)


def cta():
    img = Image.new("RGB", (L, A), CREME)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([48, 48, L - 48, A - 48], 40, outline=CREME_2, width=3)

    ic = _icone(150)
    img.paste(ic, ((L - ic.width) // 2, 330), ic)
    d = ImageDraw.Draw(img)

    f = _serif(80, 500)
    _linha_mista(d, L // 2, 640, [("Quer o link do ", TINTA), ("produto", ROXO)], f)
    _linha_mista(d, L // 2, 735, [("ou do ", TINTA), ("grupo", ROXO), ("?", TINTA)], f)

    d.line([(L // 2 - 40, 792), (L // 2 + 40, 792)], fill=ROSE, width=3)
    fa = _serif(50, 500, italico=True)
    d.text((L // 2, 870), "Comenta aqui embaixo", font=fa, fill=TINTA, anchor="ms")
    d.text((L // 2, 932), "que eu te mando", font=fa, fill=TINTA, anchor="ms")

    d.text((L // 2, A - 150), ARROBA, font=_sans(30, 500), fill=TINTA_SUAVE, anchor="ms")
    d.text((L // 2, A - 108), "promoção temporária  ·  #publi", font=_sans(22, 400),
           fill=(165, 150, 146), anchor="ms")
    return img


def carrossel(foto_capa, itens, titulo=None, apoio=None, estilo="classico", destaque=()):
    """itens: [(cena, titulo, preco, preco_de)] -> lista de PNG (bytes)."""
    kw = {k: v for k, v in (("titulo", titulo), ("apoio", apoio)) if v}
    kw.update(estilo=estilo, destaque=destaque)
    slides = [capa(foto_capa, **kw)]
    for cena, t, p, de in itens:
        slides.append(produto(cena, t, p, de))
    slides.append(cta())
    return [_png(s) for s in slides]
