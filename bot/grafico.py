"""Gráfico de preço pelo histórico do próprio bot (para as ofertas com o selo de menor preço).

- serie_diaria(estado, pid, agora)  → preço de cada dia da janela (até 30 dias), terminando em hoje
- gerar(titulo, serie, loja)        → PNG 1080x1080 (post) ou 1080x1350 (cartão de carrossel, formato="4x5")
- enviar_oferta(tg, ...)            → posta a oferta; com selo e GRAFICO_ATIVO=1, vai num álbum: foto + gráfico

Sem porcentagem na arte (regra das artes): só os preços em reais e as datas.
"""
import os
from PIL import Image, ImageDraw

from . import arte
from . import estado as est
from .mensagens import brl

JANELA = 30
MIN_DIAS = 14  # mesmo mínimo do selo: com menos histórico que isso, não tem gráfico


def serie_diaria(estado, pid, agora, dias=JANELA):
    """[(date, preço)] dia a dia até hoje, pelo mesmo critério do selo (o menor preço visto em cada dia)."""
    return est.serie_diaria(estado, pid, agora, dias, com_hoje=True)


def _passo_bonito(bruto):
    """Arredonda o intervalo entre as linhas do eixo para 1, 2, 2,5 ou 5 x 10^n."""
    if bruto <= 0:
        return 1.0
    exp = 1.0
    while bruto >= 10:
        bruto, exp = bruto / 10, exp * 10
    while bruto < 1:
        bruto, exp = bruto * 10, exp / 10
    for b in (1, 2, 2.5, 5, 10):
        if bruto <= b:
            return b * exp
    return 10 * exp


def _escala(minimo, maximo):
    """(piso, teto, marcas) do eixo de preço, com folga embaixo (rótulo de hoje) e em cima (rótulo do pico)."""
    amplitude = max(maximo - minimo, maximo * 0.04, 0.5)
    passo = _passo_bonito(amplitude / 3)
    piso = max(0.0, (int((minimo - amplitude * 0.35) / passo)) * passo)
    teto = piso
    while teto < maximo + amplitude * 0.25:
        teto += passo
    marcas, v = [], piso
    while v <= teto + 1e-9:
        marcas.append(round(v, 2))
        v += passo
    return piso, teto, marcas


def _rotulo_eixo(v):
    return brl(v)[:-3] if abs(v - round(v)) < 0.005 else brl(v)


def gerar(titulo, serie, loja="ml", formato="1x1"):
    """PNG do gráfico. serie: [(date, preço)] terminando em hoje (ver serie_diaria)."""
    L, A = (1080, 1350) if formato == "4x5" else (1080, 1080)
    img = arte._fundo(L, A)
    arte._cabecalho(img)
    d = ImageDraw.Draw(img)
    dias = max((serie[-1][0] - serie[0][0]).days, 1)
    d.text((60, 178), f"Preço nos últimos {dias} dias", font=arte._fredoka(62), fill=arte.UVA)
    f_nome = arte._poppins(30)
    y = 262
    for linha in arte._quebrar(d, " ".join((titulo or "").split()), f_nome, L - 120, 2):
        d.text((60, y), linha, font=f_nome, fill=arte.SUAVE)
        y += 42

    # Cartão branco com o gráfico
    cx0, cy0, cx1, cy1 = 60, y + 26, L - 60, A - 156
    d.rounded_rectangle([cx0, cy0, cx1, cy1], radius=36, fill=arte.BRANCO)
    f_eixo = arte._poppins(26)
    precos = [p for _, p in serie]
    piso, teto, marcas = _escala(min(precos), max(precos))
    larg_rotulo = max(d.textlength(_rotulo_eixo(m), font=f_eixo) for m in marcas)
    px0, px1 = cx0 + 44 + larg_rotulo + 18, cx1 - 64
    py0, py1 = cy0 + 70, cy1 - 96
    n = len(serie)

    def X(i):
        return px0 + (px1 - px0) * (i / max(n - 1, 1))

    def Y(v):
        return py1 - (py1 - py0) * ((v - piso) / (teto - piso))

    for m in marcas:  # grade discreta + rótulos do eixo
        d.line([(px0, Y(m)), (px1, Y(m))], fill=arte.LAVANDA, width=2)
        d.text((px0 - 18, Y(m)), _rotulo_eixo(m), font=f_eixo, fill=arte.SUAVE, anchor="rm")

    # Linha em degraus (o preço vale até mudar), desenhada no dobro do tamanho para ficar lisa
    E = 2
    camada = Image.new("RGBA", (L * E, A * E), (0, 0, 0, 0))
    dc = ImageDraw.Draw(camada)
    pts = [(X(0), Y(precos[0]))]
    for i in range(1, n):
        pts.append((X(i), Y(precos[i - 1])))
        if precos[i] != precos[i - 1]:
            pts.append((X(i), Y(precos[i])))
    pts2 = [(x * E, y * E) for x, y in pts]
    if len(pts2) > 1:
        dc.line(pts2, fill=arte.ROXO, width=6 * E, joint="curve")
    r = 3 * E
    for x, y in (pts2[0], pts2[-1]):  # pontas arredondadas
        dc.ellipse([x - r, y - r, x + r, y + r], fill=arte.ROXO)
    hx, hy = X(n - 1) * E, Y(precos[-1]) * E
    dc.ellipse([hx - 21 * E, hy - 21 * E, hx + 21 * E, hy + 21 * E], fill=arte.BRANCO)  # anel branco
    dc.ellipse([hx - 15 * E, hy - 15 * E, hx + 15 * E, hy + 15 * E], fill=arte.PINK)    # hoje
    img.paste(Image.alpha_composite(img.convert("RGBA").resize((L * E, A * E), Image.LANCZOS), camada)
              .resize((L, A), Image.LANCZOS).convert("RGB"))
    d = ImageDraw.Draw(img)

    # Rótulo de hoje (pílula) abaixo do ponto, encostada à direita
    f_hoje = arte._poppins(34, "Bold")
    txt = f"Hoje: {brl(precos[-1])}"
    w = d.textlength(txt, font=f_hoje) + 48
    asc, desc = f_hoje.getmetrics()
    h = asc + desc + 16
    bx1 = min(X(n - 1) + 28, cx1 - 24)
    by0 = Y(precos[-1]) + 30
    if by0 + h > py1 + 8:  # não cabe embaixo: vai para cima do ponto
        by0 = Y(precos[-1]) - 30 - h
    d.rounded_rectangle([bx1 - w, by0, bx1, by0 + h], radius=h // 2, fill=arte.UVA)
    d.text((bx1 - w + 24, by0 + 8), txt, font=f_hoje, fill=arte.BRANCO)

    # Rótulo do preço mais alto da janela, no meio do trecho em que ele valeu
    pico = max(precos)
    if pico > precos[-1] * 1.005:
        idx = [i for i, p in enumerate(precos) if p == pico]
        ini = fim = idx[0]
        for i in idx[1:]:  # primeiro trecho contínuo no pico
            if i != fim + 1:
                break
            fim = i
        mx = (X(ini) + X(min(fim + 1, n - 1))) / 2
        f_pico = arte._poppins(28, "SemiBold")
        tw = d.textlength(brl(pico), font=f_pico)
        mx = min(max(mx, px0 + tw / 2), px1 - tw / 2)
        d.text((mx, Y(pico) - 16), brl(pico), font=f_pico, fill=arte.UVA, anchor="mb")

    # Datas: começo, meio (se couber) e hoje
    marcas_x = [(0, f"{serie[0][0]:%d/%m}"), (n - 1, "hoje")]
    if n >= 12:
        meio = (n - 1) // 2
        marcas_x.insert(1, (meio, f"{serie[meio][0]:%d/%m}"))
    for i, t in marcas_x:
        ancora = "la" if i == 0 else "ra" if i == n - 1 else "ma"
        d.text((X(i), py1 + 26), t, font=f_eixo, fill=arte.SUAVE, anchor=ancora)

    onde = "na Shopee" if loja == "shopee" else "no Mercado Livre"
    arte._rodape(img, f"preços que o Chocalho viu {onde}  ·  #publi")
    return arte._png(img)


def da_oferta(oferta, estado, agora, formato="1x1"):
    """PNG do gráfico da oferta, ou None se não tem histórico suficiente."""
    serie = serie_diaria(estado, oferta.id, agora)
    if len(serie) < 2 or (serie[-1][0] - serie[0][0]).days < MIN_DIAS:
        return None
    serie[-1] = (serie[-1][0], float(oferta.preco))  # hoje é o preço do post
    if max(p for _, p in serie) <= oferta.preco:
        return None
    return gerar(oferta.titulo, serie, getattr(oferta, "loja", "ml") or "ml", formato)


def enviar_oferta(tg, chat, legenda_html, oferta, estado, agora, log=print):
    """Posta a oferta no canal. Com selo de menor preço e GRAFICO_ATIVO=1, manda um álbum:
    a foto do produto + o gráfico de preço. Qualquer problema no gráfico, vai o post normal."""
    if os.environ.get("GRAFICO_ATIVO") == "1" and getattr(oferta, "selo_dias", None) and oferta.imagem:
        try:
            png = da_oferta(oferta, estado, agora)
            if png:
                return tg.enviar_oferta_com_grafico(chat, legenda_html, oferta.imagem, png)
        except Exception as e:  # noqa: BLE001 — o gráfico nunca impede o post
            log(f"Aviso: gráfico de {oferta.id} não saiu ({type(e).__name__}); post normal.")
    return tg.enviar_oferta(chat, legenda_html, oferta.imagem)
