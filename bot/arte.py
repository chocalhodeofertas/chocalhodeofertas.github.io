"""Arte da oferta (imagem 4:5, 1080x1350) para story, feed e WhatsApp.

Só usa informações do anúncio (nome, preço, desconto), como pede a
cláusula 5.4 dos termos de afiliado.
"""
import io
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from .mensagens import brl

FONTES = Path(__file__).resolve().parent.parent / "assets" / "fonts"
L, A = 1080, 1350

CREME = (255, 248, 236)
TEXTO = (43, 38, 32)
SUAVE = (122, 111, 99)
AMARELO = (244, 180, 0)
VERMELHO = (226, 87, 76)
BRANCO = (255, 255, 255)


def _fonte(peso, tamanho):
    return ImageFont.truetype(str(FONTES / f"Poppins-{peso}.ttf"), tamanho)


def _quebrar(draw, texto, fonte, largura, max_linhas):
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        teste = f"{atual} {p}".strip()
        if draw.textlength(teste, font=fonte) <= largura:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = p
        if len(linhas) == max_linhas:
            break
    if atual and len(linhas) < max_linhas:
        linhas.append(atual)
    usadas = sum(len(l.split()) for l in linhas)
    if usadas < len(palavras) and linhas:
        ultima = linhas[-1]
        while ultima and draw.textlength(ultima + "…", font=fonte) > largura:
            ultima = ultima.rsplit(" ", 1)[0] if " " in ultima else ultima[:-1]
        linhas[-1] = ultima + "…"
    return linhas


def _baixar_foto(url, session=None):
    if not url:
        return None
    try:
        r = (session or requests).get(url, timeout=20)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:  # noqa: BLE001
        return None


def _chocalho(draw, cx, cy, r):
    """Desenho simples de um chocalho (sem depender de fonte de emoji)."""
    draw.line([(cx, cy + r * 0.6), (cx + r * 0.9, cy + r * 2.0)], fill=TEXTO, width=max(4, r // 5))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=AMARELO, outline=TEXTO, width=max(3, r // 7))
    for dx, dy in ((-0.35, -0.3), (0.3, -0.1), (-0.05, 0.35)):
        rr = r * 0.13
        draw.ellipse([cx + dx * r - rr, cy + dy * r - rr, cx + dx * r + rr, cy + dy * r + rr], fill=TEXTO)


def gerar(oferta, foto=None, session=None):
    """Retorna os bytes PNG da arte. `foto` (PIL) evita baixar de novo."""
    img = Image.new("RGB", (L, A), CREME)
    d = ImageDraw.Draw(img)

    # Cabeçalho
    _chocalho(d, 92, 92, 34)
    d.text((150, 58), "Chocalho de Ofertas", font=_fonte("Bold", 44), fill=TEXTO)
    d.text((152, 112), "achados de bebê e criança", font=_fonte("Regular", 26), fill=SUAVE)

    # Cartão branco com a foto
    cx0, cy0, cx1, cy1 = 60, 190, L - 60, 860
    d.rounded_rectangle([cx0, cy0, cx1, cy1], radius=36, fill=BRANCO)
    foto = foto if foto is not None else _baixar_foto(oferta.imagem, session)
    if foto is not None:
        area = (cx1 - cx0 - 80, cy1 - cy0 - 80)
        foto.thumbnail(area, Image.LANCZOS)
        px = cx0 + (cx1 - cx0 - foto.width) // 2
        py = cy0 + (cy1 - cy0 - foto.height) // 2
        img.paste(foto, (px, py), foto)
    else:
        _chocalho(d, L // 2 - 30, (cy0 + cy1) // 2 - 40, 110)

    # Selo de desconto
    if oferta.preco_de:
        pct = f"-{round(oferta.desconto * 100)}%"
        f = _fonte("Bold", 58)
        larg = d.textlength(pct, font=f) + 64
        d.rounded_rectangle([cx1 - larg - 24, cy0 + 24, cx1 - 24, cy0 + 124], radius=50, fill=VERMELHO)
        d.text((cx1 - 24 - larg / 2, cy0 + 74), pct, font=f, fill=BRANCO, anchor="mm")

    # Título
    y = 900
    for linha in _quebrar(d, oferta.titulo, _fonte("Medium", 40), L - 140, 2):
        d.text((70, y), linha, font=_fonte("Medium", 40), fill=TEXTO)
        y += 54

    # Preços
    y = max(y + 18, 1030)
    if oferta.preco_de:
        de = f"De {brl(oferta.preco_de)}"
        f_de = _fonte("Regular", 38)
        d.text((70, y), de, font=f_de, fill=SUAVE)
        w = d.textlength(de, font=f_de)
        d.line([(70 + d.textlength("De ", font=f_de), y + 26), (70 + w, y + 26)], fill=SUAVE, width=3)
        y += 52
    d.text((70, y + 26), "por", font=_fonte("Regular", 38), fill=TEXTO)
    d.text((70 + d.textlength("por ", font=_fonte("Regular", 38)), y - 30), brl(oferta.preco),
           font=_fonte("Bold", 96), fill=TEXTO)

    # Rodapé
    d.rounded_rectangle([60, A - 130, L - 60, A - 50], radius=40, fill=AMARELO)
    d.text((L // 2, A - 90), "Link no grupo · preço sujeito a alteração · #publi",
           font=_fonte("Medium", 30), fill=TEXTO, anchor="mm")

    saida = io.BytesIO()
    img.save(saida, "PNG", optimize=True)
    return saida.getvalue()
