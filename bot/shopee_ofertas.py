"""Ofertas da Shopee: escolhe, monta e posta (por cima das do Mercado Livre).

Regras combinadas:
- só a API oficial; link de afiliado gerado pela própria Shopee, sem alteração,
  com uma etiqueta por canal (telegram / whatsapp) para medir as vendas;
- só o preço final ("Por R$ X" ou "A partir de R$ X" quando há opções de preço).
  O "de" da Shopee é o vendedor que define, então não é usado. O bot guarda o
  histórico de preços e só mostra "de/por" quando ele mesmo viu o preço cair;
- nota a partir de 4,7, mais de 500 vendidos, comissão a partir de 5%;
- mesmos filtros do Mercado Livre (NBCAL, idade, fora do nicho etc.).
"""
import math
import os
import random
import re
from datetime import datetime, timedelta

from . import estado as est
from . import mensagens, whatsapp
from .filtros import fora_da_faixa, motivo_bloqueio, normalizar
from .ofertas import Oferta, limite_hora, meta_ate_agora, tipo_produto
from .shopee import MAIS_VENDIDOS, Shopee, ShopeeErro
from .telegram import TelegramErro

TERMOS = [
    "bebê", "infantil", "brinquedo educativo", "brinquedo montessori", "body bebê", "roupa infantil",
    "mochila infantil", "lancheira infantil", "banheira bebê", "kit higiene bebê", "fralda",
    "lenço umedecido", "tapete atividades bebê", "mordedor bebê", "babador", "naninha", "enxoval bebê",
    "pijama infantil", "tênis infantil", "sandália infantil", "kit escolar infantil", "livro infantil",
    "fantasia infantil", "quebra cabeça infantil", "blocos de montar", "boneca", "carrinho brinquedo",
    "massinha de modelar", "piscina de bolinhas", "cadeirinha alimentação", "copo transição",
    "pratinho infantil", "toalha de banho infantil", "protetor de berço", "ninho redutor",
]
TERMOS_POR_RODADA = 3
NOTA_MIN, VENDAS_MIN, COMISSAO_MIN = 4.7, 500, 0.05
QUEDA_MIN = 0.10  # "de/por" só se o próprio bot viu o preço 10% mais alto nos últimos 30 dias

_CATEGORIAS = [
    ("fralda", r"\b(fralda|lenco umedecido|lencos umedecidos)"),
    ("higiene", r"\b(banheira|higiene|escova|shampoo|sabonete|toalha|cortador de unha|aparador de unha|fio dental)"),
    ("escola", r"\b(mochila|lancheira|estojo|escolar|caderno|lapis)"),
    ("livro", r"\b(livro|historinhas?)\b"),
    ("festa", r"\b(fantasia|festa|aniversario|lembrancinha)"),
    ("alimentacao", r"\b(prato|pratinho|copo|talher|babador|cadeirinha de alimentacao|cadeira de alimentacao)"),
    ("quarto", r"\b(berco|ninho|naninha|travesseiro|lencol|protetor de berco|abajur|mosquiteiro)"),
    ("passeio", r"\b(carrinho de bebe|canguru|sling|bolsa maternidade|cadeirinha auto)"),
    ("roupa", r"\b(body|bodies|pijama|camiseta|calca|vestido|conjunto|meia|tenis|sandalia|sapato|macacao|roupa)"),
    ("brinquedo", r"\b(brinquedo|boneca|blocos?|quebra.?cabeca|massinha|pelucia|carrinho|jogo|montessori|"
                  r"educativo|chocalho|mordedor|tapete)"),
]
_CATEGORIAS = [(c, re.compile(p)) for c, p in _CATEGORIAS]


def categoria_do_titulo(titulo):
    t = normalizar(titulo)
    for cat, padrao in _CATEGORIAS:
        if padrao.search(t):
            return cat
    return ""


def _estado(estado):
    s = estado.setdefault("shopee", {})
    s.setdefault("postados", {})
    s.setdefault("termo", 0)
    s.setdefault("hora", [])
    return s


def posts_hoje(estado, agora):
    return estado.get("hist_dia", {}).get(agora.date().isoformat(), {}).get("shopee", 0)


def posts_ultima_hora(estado, agora):
    return sum(1 for q in _estado(estado)["hora"] if (agora - datetime.fromisoformat(q)).total_seconds() < 3600)


def preco_de_pelo_historico(estado, pid, preco, agora):
    """Maior preço que o próprio bot viu nos últimos 30 dias, se for bem acima do atual."""
    hist = (estado.get("precos", {}).get(pid) or {}).get("historico") or []
    corte = (agora.date() - timedelta(days=30)).isoformat()
    vistos = [p for d, p in hist if d >= corte]
    if not vistos:
        return None
    maior = max(vistos)
    return maior if preco <= maior * (1 - QUEDA_MIN) else None


def aprovado(p):
    """Motivo para não usar o produto (ou None)."""
    if p.nota < NOTA_MIN:
        return "nota baixa"
    if p.vendas < VENDAS_MIN:
        return "poucas vendas"
    if p.comissao < COMISSAO_MIN:
        return "comissão baixa"
    if not p.preco or not p.link:
        return "sem preço ou link"
    return motivo_bloqueio(p.titulo) or fora_da_faixa(p.titulo, "", "infantil")


def pontos(p, estado=None, agora=None):
    base = math.log10(max(p.vendas, 1)) * p.nota * (1.2 if p.loja_oficial else 1.0) * (1 + p.comissao)
    if estado is not None and agora is not None:
        from .ofertas import DIAS_HIST_MIN
        tipico, dias = est.preco_tipico(estado, p.id, agora)
        if tipico and dias >= DIAS_HIST_MIN:
            queda = 1 - p.preco / tipico
            base *= 1.3 if queda >= 0.10 else 1.0
    return base


ACOMPANHAR_POR_RODADA = 15
DIAS_ACOMPANHAR = 30


def acompanhar(shp, estado, agora, log=print, limite=ACOMPANHAR_POR_RODADA):
    """Confere o preço dos produtos bons já vistos (os que demoram mais sem conferir vão primeiro),
    para o histórico não depender de o produto cair de novo na busca."""
    s = _estado(estado)
    acomp = s.setdefault("acompanhados", {})
    hoje = agora.date().isoformat()
    for pid in [k for k, v in acomp.items() if v.get("ate", "") < hoje]:
        del acomp[pid]
    fila = sorted(acomp, key=lambda k: acomp[k].get("visto", ""))[:limite]
    from .ofertas import DIAS_HIST_MIN
    caiu = []
    for pid in fila:
        try:
            p = shp.item(pid[3:])
        except ShopeeErro as e:
            log(f"Shopee: não consegui conferir {pid}: {e}")
            break
        acomp[pid]["visto"] = agora.isoformat(timespec="minutes")
        if p is None:
            del acomp[pid]
            continue
        est.registrar_preco(estado, p.id, p.preco, agora)
        tipico, dias = est.preco_tipico(estado, p.id, agora)
        if tipico and dias >= DIAS_HIST_MIN and p.preco <= tipico * 0.90 and not aprovado(p):
            caiu.append(p)  # caiu de verdade: vira candidato mesmo fora da busca desta rodada
    return caiu


def _marcar_acompanhado(estado, p, agora):
    acomp = _estado(estado).setdefault("acompanhados", {})
    reg = acomp.setdefault(p.id, {})
    reg["ate"] = (agora + timedelta(days=DIAS_ACOMPANHAR)).date().isoformat()
    reg["visto"] = agora.isoformat(timespec="minutes")


def buscar_candidatos(shp, estado, agora, repost_dias=3, log=print, termos=None):
    s = _estado(estado)
    if termos is None:
        i = s["termo"] % len(TERMOS)
        termos = (TERMOS + TERMOS)[i:i + TERMOS_POR_RODADA]
        s["termo"] = (i + TERMOS_POR_RODADA) % len(TERMOS)
    achados = {}
    for termo in termos:
        try:
            for p in shp.buscar(termo, ordem=MAIS_VENDIDOS, limite=50):
                achados.setdefault(p.id, p)
        except ShopeeErro as e:
            log(f"Shopee: busca '{termo}' falhou: {e}")
    corte = agora - timedelta(days=repost_dias)
    bons = []
    for p in achados.values():
        est.registrar_preco(estado, p.id, p.preco, agora)
        quando = s["postados"].get(p.id)
        if quando and datetime.fromisoformat(quando) > corte:
            continue
        if not aprovado(p):
            _marcar_acompanhado(estado, p, agora)
            bons.append(p)
    bons.sort(key=lambda p: pontos(p, estado, agora), reverse=True)
    log(f"Shopee: {len(achados)} produtos vistos ({', '.join(termos)}), {len(bons)} aprovados.")
    return bons


def para_oferta(p, estado, agora, link_tg=None, link_wa=None):
    preco_de = preco_de_pelo_historico(estado, p.id, p.preco, agora)
    o = Oferta(id=p.id, titulo=p.titulo, preco=p.preco, preco_de=preco_de,
               desconto=(1 - p.preco / preco_de) if preco_de else 0.0, abaixo_do_habitual=None,
               menor_preco_historico=False, link=link_tg or p.link, imagem=p.imagem,
               categoria=categoria_do_titulo(p.titulo))
    o.loja = "shopee"
    o.a_partir = bool(p.preco_max and p.preco_max > p.preco * 1.02)
    o.link_wa = link_wa or link_tg or p.link
    o.nota, o.vendas = p.nota, p.vendas
    o.cupom = None
    return o


def links(shp, p, log=print):
    """Link de afiliado da própria Shopee, com etiqueta por canal. Sem a API, usa o offerLink."""
    origem = p.link_produto or p.link
    saida = {}
    for canal in ("telegram", "whatsapp"):
        try:
            saida[canal] = shp.link_curto(origem, [canal]) or p.link
        except ShopeeErro as e:
            log(f"Shopee: link com etiqueta falhou ({e}); usando o link padrão.")
            saida[canal] = p.link
    return saida["telegram"], saida["whatsapp"]


def rodar(cfg, tg, estado, agora, rng=random, esperar=None, log=print, shp=None):
    """Posta ofertas da Shopee no canal (limite próprio) e manda para a fila do WhatsApp."""
    if os.environ.get("SHOPEE_ATIVO") != "1":
        return []
    if not (cfg.hora_inicio <= agora.hour < cfg.hora_fim):
        return []
    try:
        shp = shp or Shopee(os.environ.get("SHOPEE_APP_ID"), os.environ.get("SHOPEE_SECRET"))
    except ShopeeErro as e:
        log(f"Shopee desligada: {e}")
        return []
    max_dia = int(os.environ.get("SHOPEE_MAX_DIA") or 50)
    max_hora = int(os.environ.get("SHOPEE_MAX_HORA") or 4)
    max_rodada = int(os.environ.get("SHOPEE_MAX_RODADA") or 2)
    s = _estado(estado)
    s["hora"] = [q for q in s["hora"] if (agora - datetime.fromisoformat(q)).total_seconds() < 3600]
    vagas = max(0, min(max_rodada, limite_hora(max_hora, agora.hour) - posts_ultima_hora(estado, agora),
                       min(max_dia, meta_ate_agora(max_dia, agora.hour, cfg.hora_inicio, cfg.hora_fim))
                       - posts_hoje(estado, agora)))
    candidatos = buscar_candidatos(shp, estado, agora, cfg.repost_dias, log)
    try:
        corte = agora - timedelta(days=cfg.repost_dias)
        ja = {p.id for p in candidatos}
        for p in acompanhar(shp, estado, agora, log):
            quando = s["postados"].get(p.id)
            if p.id not in ja and not (quando and datetime.fromisoformat(quando) > corte):
                candidatos.append(p)
        candidatos.sort(key=lambda p: pontos(p, estado, agora), reverse=True)
    except Exception as e:  # noqa: BLE001 — acompanhar nunca atrapalha os posts
        log(f"Shopee: acompanhamento falhou: {type(e).__name__}: {e}")
    if not vagas or not candidatos:
        return []
    hoje = agora.date().isoformat()
    tipos = s.setdefault("tipos", {})
    for d in [d for d in tipos if d != hoje]:
        del tipos[d]
    tipos_hoje = set(tipos.setdefault(hoje, []))
    enviadas = []
    for p in candidatos:
        if len(enviadas) >= vagas:
            break
        tp = tipo_produto(p.titulo)
        if tp in tipos_hoje:
            continue
        if est.repetido(estado, p.titulo, agora, cfg.repost_dias, p.preco):
            continue  # mesmo produto (de outro vendedor ou do ML) já saiu nos últimos dias
        if enviadas and esperar:
            esperar(rng.uniform(cfg.intervalo_min, max(cfg.intervalo_max, cfg.intervalo_min)) * 60)
        link_tg, link_wa = links(shp, p, log)
        o = para_oferta(p, estado, agora, link_tg, link_wa)
        try:
            tg.enviar_oferta(cfg.canal, mensagens.montar_telegram(o, rng), o.imagem)
        except TelegramErro as e:
            log(f"Erro ao postar {o.id} (Shopee) no canal: {e}")
            continue
        whatsapp.enfileirar_oferta(o, mensagens.montar_whatsapp(o, rng), agora, loja="shopee")
        s["postados"][o.id] = agora.isoformat(timespec="minutes")
        s.setdefault("titulos", {})[o.id] = {"titulo": o.titulo[:80], "quando": agora.isoformat(timespec="minutes"), "preco": o.preco}
        s["hora"].append(agora.isoformat(timespec="minutes"))
        tipos_hoje.add(tp)
        tipos[hoje] = sorted(tipos_hoje)
        est.contar_dia(estado, agora, "shopee")
        est.contar_dia(estado, agora, "posts")
        enviadas.append(o)
        log(f"Postado (Shopee): {o.id} {mensagens.brl(o.preco)} — {o.titulo[:50]}")
    # Limpa postados antigos
    corte = (agora - timedelta(days=30)).isoformat()
    for pid in [k for k, v in s["postados"].items() if v < corte]:
        del s["postados"][pid]
    for pid in [k for k, v in s.get("titulos", {}).items() if v.get("quando", "") < corte]:
        del s["titulos"][pid]
    return enviadas
