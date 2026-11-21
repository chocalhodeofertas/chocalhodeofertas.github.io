"""Reconhecer o mesmo produto pela FOTO (21/11), de graça: "impressão digital" da imagem (dHash).

Vendedores diferentes costumam usar a mesma foto de fábrica com títulos diferentes. A impressão digital é
um número de 64 bits que resume a foto: fotos iguais (mesmo redimensionadas, com outra compressão ou margem)
dão números quase iguais. Distância = quantos dos 64 bits mudam.
"""
import io
import os

import requests
from PIL import Image, ImageChops

IGUAL = 5          # até 5 bits diferentes: a mesma foto
PARECIDA = 10      # até 10: foto muito parecida; só conta se o título também tiver algo em comum
NOTA_TITULO = 0.4  # o que o título precisa ter em comum quando a foto é só "muito parecida"
GUARDAR_DIAS = 45


def ligado():
    return os.environ.get("FOTO_IGUAL", "1") != "0"


def impressao(img):
    """dHash de 64 bits (texto hexadecimal) de uma imagem do Pillow. Corta a margem branca antes."""
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fundo = Image.new("RGBA", img.size, (255, 255, 255, 255))
        fundo.alpha_composite(img)
        img = fundo
    cinza = img.convert("L")
    caixa = ImageChops.invert(cinza).point(lambda v: 255 if v > 12 else 0).getbbox()
    if caixa and (caixa[2] - caixa[0]) > 16 and (caixa[3] - caixa[1]) > 16:
        cinza = cinza.crop(caixa)
    pequena = cinza.resize((9, 8), Image.LANCZOS)
    px = list(pequena.get_flattened_data() if hasattr(pequena, "get_flattened_data") else pequena.getdata())
    bits = 0
    for linha in range(8):
        for col in range(8):
            bits = (bits << 1) | (px[linha * 9 + col] > px[linha * 9 + col + 1])
    return f"{bits:016x}"


def distancia(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def baixar(url, session=None):
    if not url:
        return None
    try:
        r = (session or requests).get(url, timeout=15)
        r.raise_for_status()
        return impressao(Image.open(io.BytesIO(r.content)))
    except Exception:  # noqa: BLE001 — sem foto, a regra de repetição segue só pelo título
        return None


def da_oferta(estado, pid, url, agora, session=None):
    """Impressão digital da foto do produto, guardada em estado["fotos_hash"][pid] para não baixar de novo."""
    guardadas = estado.setdefault("fotos_hash", {})
    if pid in guardadas and guardadas[pid][0]:
        return guardadas[pid][0]
    h = baixar(url, session)
    if h:
        guardadas[pid] = [h, agora.isoformat(timespec="minutes")]
    return h


def limpar(estado, agora):
    from datetime import timedelta

    corte = (agora - timedelta(days=GUARDAR_DIAS)).isoformat()
    g = estado.get("fotos_hash") or {}
    estado["fotos_hash"] = {k: v for k, v in g.items() if isinstance(v, list) and len(v) == 2 and v[1] >= corte}


def mesmo_pela_foto(estado, pid, titulo, url, agora, dias, session=None, log=print):
    """Ids de posts dos últimos `dias` com a mesma foto (ou foto muito parecida e título com algo em comum)."""
    from datetime import datetime, timedelta

    from .estado import _posts_conhecidos
    from .ofertas import _medidas_brigam, comparar_titulos, reposicao

    if not ligado() or not url or reposicao(titulo or ""):
        return []  # fralda, lenço...: a mesma foto serve para vários tamanhos; ali vale marca + tamanho
    h = da_oferta(estado, pid, url, agora, session)
    if not h:
        return []
    corte = agora - timedelta(days=dias)
    guardadas = estado.get("fotos_hash") or {}
    achados = []
    for p_id, quando, _, p_titulo in _posts_conhecidos(estado):
        if p_id == pid or p_id in achados or p_id not in guardadas:
            continue
        try:
            t = datetime.fromisoformat(quando)
        except (TypeError, ValueError):
            continue
        if not corte < t <= agora:
            continue
        if _medidas_brigam(titulo or "", p_titulo or ""):
            continue  # mesma foto, mas tamanho/quantidade/modelo diferente (aro 12 x aro 16)
        d = distancia(h, guardadas[p_id][0])
        if d <= IGUAL or (d <= PARECIDA and comparar_titulos(titulo or "", p_titulo or "")["nota"] >= NOTA_TITULO):
            achados.append(p_id)
            log(f"Mesma foto: {(titulo or '')[:50]} = {(p_titulo or '')[:50]} (diferença {d}/64)")
    return achados


def checar(estado, pid, titulo, preco, url, agora, dias, session=None, log=print):
    """Regra de repetição completa: título (estado.checar_repeticao) e, se ele não achar nada, a foto."""
    from .estado import checar_repeticao

    rep = checar_repeticao(estado, pid, titulo, preco, agora, dias)
    if rep is not None:
        return rep
    mesmos = mesmo_pela_foto(estado, pid, titulo, url, agora, dias, session, log)
    return checar_repeticao(estado, pid, titulo, preco, agora, dias, mesmos=mesmos) if mesmos else None
