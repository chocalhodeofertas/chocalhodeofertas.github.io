"""Peças de Natal (carrossel 4:5 e stories 9:16) em cima do visual em cena do
`tiktok.py`. A palavra NATAL e os enfeites usam as cores do Natal; o resto fica
na paleta do Chocalho (lavanda, uva e roxo).
"""
import math
import random

from PIL import Image, ImageDraw

from bot import tiktok as tk
from bot.arte import _png

VERMELHO = (200, 30, 45)
VERDE = (24, 110, 62)
VERDE_2 = (46, 140, 80)
DOURADO = (236, 190, 80)
BRANCO = (255, 255, 255)


# ---------- enfeites ----------

def _estrela(d, cx, cy, r, cor=DOURADO):
    pts = []
    for k in range(8):
        rr = r if k % 2 == 0 else r * 0.3
        a = k * math.pi / 4 - math.pi / 2
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=cor)


def _floco(d, cx, cy, r, cor=(255, 255, 255, 210), esp=3):
    for k in range(6):
        a = k * math.pi / 3
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        d.line([(cx, cy), (x, y)], fill=cor, width=esp)
        for s in (-1, 1):  # raminhos
            b = a + s * 0.6
            mx, my = cx + r * 0.6 * math.cos(a), cy + r * 0.6 * math.sin(a)
            d.line([(mx, my), (mx + r * 0.3 * math.cos(b), my + r * 0.3 * math.sin(b))], fill=cor, width=esp)


def _ramo(img, x0, y0, comprimento, angulo, espelhar=False, seed=3):
    """Ramo de pinheiro com bolinhas vermelhas e douradas."""
    camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    r = random.Random(seed)
    s = -1 if espelhar else 1
    a = math.radians(angulo)
    x1, y1 = x0 + s * comprimento * math.cos(a), y0 + comprimento * math.sin(a)
    d.line([(x0, y0), (x1, y1)], fill=(92, 58, 40, 255), width=8)
    for i in range(46):
        t = i / 45
        px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        for lado in (-1, 1):
            b = a + lado * 0.9
            n = 46 * (1 - 0.45 * t)
            cor = r.choice([VERDE, VERDE_2, (18, 92, 52)])
            d.line([(px, py), (px + s * n * math.cos(b), py + n * math.sin(b))], fill=cor + (255,), width=6)
    for k in range(5):
        t = 0.25 + 0.15 * k
        px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t + r.randint(10, 30)
        cor = VERMELHO if k % 2 == 0 else DOURADO
        d.ellipse([px - 15, py - 15, px + 15, py + 15], fill=cor + (255,))
        d.ellipse([px - 7, py - 9, px - 1, py - 3], fill=(255, 255, 255, 170))
    img.paste(camada, (0, 0), camada)


def _laco(d, cx, cy, tam=60):
    d.polygon([(cx, cy), (cx - tam * 1.3, cy - tam * 0.7), (cx - tam * 1.3, cy + tam * 0.7)], fill=VERMELHO)
    d.polygon([(cx, cy), (cx + tam * 1.3, cy - tam * 0.7), (cx + tam * 1.3, cy + tam * 0.7)], fill=VERMELHO)
    d.polygon([(cx - 8, cy), (cx - tam * 0.8, cy + tam * 1.6), (cx - tam * 0.3, cy + tam * 1.5)], fill=(170, 20, 36))
    d.polygon([(cx + 8, cy), (cx + tam * 0.8, cy + tam * 1.6), (cx + tam * 0.3, cy + tam * 1.5)], fill=(170, 20, 36))
    d.ellipse([cx - tam * 0.32, cy - tam * 0.32, cx + tam * 0.32, cy + tam * 0.32], fill=(170, 20, 36))


def _brilhos(img, pontos):
    camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    for tipo, x, y, r in pontos:
        if tipo == "e":
            _estrela(d, x, y, r)
        else:
            _floco(d, x, y, r)
    img.paste(camada, (0, 0), camada)


def _etiqueta_idade(img, texto, y=70):
    """Faixa de idade no topo: etiqueta lavanda com letra uva e estrelinha dourada."""
    d = ImageDraw.Draw(img)
    f = tk._poppins(40, "ExtraBold")
    w = d.textlength(texto, font=f)
    x0 = (img.width - w - 120) // 2
    caixa = (x0, y, x0 + w + 120, y + 84)
    tk._sombra_caixa(img, caixa, 42, desfoque=14, forca=70, dy=6)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(caixa, 42, fill=tk.LAVANDA)
    _estrela(d, x0 + 40, y + 42, 18)
    d.text((x0 + 70, y + 44), texto, font=f, fill=tk.UVA, anchor="lm")


# ---------- carrossel ----------

def capa(foto):
    img = tk._cobrir(foto, foco_y=0.55)
    img = tk._degrade(img, 0, 820, 175, de_cima=True)
    d = ImageDraw.Draw(img)
    linhas = [[("PRESENTE DE ", BRANCO), ("NATAL", VERMELHO)], [("ATÉ R$ 100", tk.LAVANDA)]]
    largura = tk.L - 2 * tk.MARGEM
    for tam in (110, 104, 98, 92, 86, 80, 76):
        f = tk._poppins(tam, "ExtraBold")
        if all(d.textlength("".join(t for t, _ in ln), font=f) <= largura for ln in linhas):
            break
    passo = int(tam * 1.08)
    base = 170 + tam

    def escrever(dd, cor):
        for k, ln in enumerate(linhas):
            x = tk.MARGEM
            for t, c in ln:
                if cor is None and c == VERMELHO:  # NATAL vermelho com contorno branco
                    dd.text((x, base + k * passo), t, font=f, fill=c, anchor="ls", stroke_width=5, stroke_fill=BRANCO)
                else:
                    dd.text((x, base + k * passo), t, font=f, fill=cor if cor is not None else c, anchor="ls")
                x += dd.textlength(t, font=f)

    tk._sombra(img, escrever, raio=12, opacidade=140)
    d = ImageDraw.Draw(img)
    y_et = base + passo + 46
    tk._etiqueta(d, tk.MARGEM, y_et, "um para cada idade", tk._poppins(38, "SemiBold"), BRANCO, tk.UVA)
    larg_natal = d.textlength("PRESENTE DE NATAL", font=f)
    _brilhos(img, [("e", tk.MARGEM + larg_natal + 34, base - tam + 4, 26), ("e", tk.MARGEM + larg_natal + 8, base - tam - 34, 14),
                   ("f", tk.L - 120, y_et + 40, 26), ("e", tk.MARGEM - 30, 120, 18)])
    return img


def produto(cena, idade, titulo, preco, foco_y=0.45):
    base = tk._cobrir(cena, foco_y=foco_y)
    base = tk._degrade(base, 760, tk.A, 120)  # escurece a base para o nome ler bem em qualquer cena
    img = tk.produto(base, titulo, preco)
    img = tk._degrade(img, 0, 260, 90, de_cima=True)
    _etiqueta_idade(img, idade)
    _brilhos(img, [("e", 92, 214, 20), ("e", tk.L - 96, 200, 24), ("f", tk.L - 150, 120, 18)])
    return img


def cta():
    img = tk.cta()
    _ramo(img, -20, 40, 430, 18)
    _ramo(img, tk.L + 20, 40, 430, 18, espelhar=True, seed=5)
    d = ImageDraw.Draw(img)
    _laco(d, tk.L // 2, 92, 46)
    _brilhos(img, [("e", 170, 1080, 22), ("e", tk.L - 180, 1040, 28), ("e", tk.L - 120, 1110, 14)])
    return img


def carrossel(foto_capa, itens):
    """itens: [(cena, idade, titulo, preco)] -> lista de PNG (bytes)."""
    slides = [capa(foto_capa)] + [produto(c, i, t, p) for c, i, t, p in itens] + [cta()]
    return [_png(s) for s in slides]


# ---------- story 9:16 ----------

def story(cena, idade, titulo, preco):
    L, A = 1080, 1920
    img = tk._cobrir(cena, L, A, foco_y=0.4)
    img = tk._degrade(img, 0, 420, 110, de_cima=True)
    img = tk._degrade(img, 760, 1380, 200)
    _etiqueta_idade(img, idade, y=230)
    _brilhos(img, [("e", 120, 380, 22), ("e", L - 120, 360, 26), ("f", L - 190, 270, 20)])
    d = ImageDraw.Draw(img)
    # nome do produto e cartão de preço
    for tam in (78, 72, 66, 60, 56):
        f = tk._serif(tam, 500)
        linhas = tk._quebrar(d, titulo, f, L - 2 * tk.MARGEM)
        if len(linhas) <= 2:
            break
    passo = int(tam * 1.12)
    y = 1120
    pos = [(L // 2, y + k * passo, ln) for k, ln in enumerate(linhas)]

    def escrever(dd, cor):
        for x, yy, ln in pos:
            dd.text((x, yy), ln, font=f, fill=cor or BRANCO, anchor="ms")

    tk._sombra(img, escrever)
    d = ImageDraw.Draw(img)
    fpor = tk._serif(82, 600)
    txt = tk.brl(preco)
    w = d.textlength(txt, font=fpor) + 90
    y0 = pos[-1][1] + 50
    caixa = (int((L - w) / 2), y0, int((L + w) / 2), y0 + 140)
    tk._sombra_caixa(img, caixa, 36, forca=90)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(caixa, 36, fill=tk.CREME)
    d.text((L // 2, y0 + 70 + 28), txt, font=fpor, fill=tk.TINTA, anchor="ms")
    # espaço livre para o adesivo de link (1480–1680) e rodapé
    d.text((L // 2, 1478), "toque no link", font=tk._sans(32, 600), fill=BRANCO, anchor="ms")
    d.polygon([(L // 2 - 16, 1494), (L // 2 + 16, 1494), (L // 2, 1514)], fill=BRANCO)
    d.text((L // 2, 1730), "promoção temporária  ·  #publi", font=tk._sans(26, 400), fill=(230, 222, 226), anchor="ms")
    return img
